"""FastAPI application factory. Run with: uvicorn deflockmigration.api.app:create_app --factory --no-access-log"""

from __future__ import annotations

import logging
import re
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from deflockmigration import __version__
from deflockmigration.api.routers import cameras, geocode, health, region, routes
from deflockmigration.application.assessment_service import AssessmentService
from deflockmigration.core.config_loader import AppConfig, load_app_config
from deflockmigration.core.errors import INTERNAL_ERROR, VALIDATION_ERROR, AppError
from deflockmigration.core.logging import configure_logging
from deflockmigration.core.metrics import Metrics
from deflockmigration.core.settings import Settings
from deflockmigration.geocoding.nominatim_local import NominatimLocalGeocoder
from deflockmigration.geocoding.provider import Geocoder, NullGeocoder
from deflockmigration.routing.provider import RoutingProvider
from deflockmigration.routing.road_locator import ValhallaRoadLocator
from deflockmigration.routing.valhalla import ValhallaProvider
from deflockmigration.storage.db import SessionFactory, make_engine, make_session_factory

log = logging.getLogger(__name__)
MAX_BODY_BYTES = 64 * 1024


def _route_template(app: FastAPI, scope: dict) -> str:
    """The declared path pattern of the matched route (never the raw URL), for metrics keyed without trip data.
    Templates come from the OpenAPI document, which lists every route with its full path regardless of how routers
    are nested; path parameters match one segment."""
    templates = getattr(app.state, "route_templates", None)
    if templates is None:
        templates = []
        try:
            for template in app.openapi().get("paths", {}):
                pattern = re.sub(r"\\\{[^/]+\\\}", "[^/]+", re.escape(template))
                templates.append((re.compile(f"^{pattern}$"), template))
        except Exception:  # noqa: BLE001 - metrics must never break a request
            templates = []
        app.state.route_templates = templates
    path = scope.get("path") or ""
    for pattern, template in templates:
        if pattern.match(path):
            return template
    return "unmatched"


def _error_response(request: Request, code: str, message: str, status: int, details: dict | None = None) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or uuid.uuid4().hex
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}, "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )


def create_app(
    settings: Settings | None = None,
    *,
    config: AppConfig | None = None,
    routing: RoutingProvider | None = None,
    geocoder: Geocoder | None = None,
    session_factory: SessionFactory | None = None,
    assessor=None,
) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)
    config = config or load_app_config(settings)
    routing = routing or ValhallaProvider(
        settings.valhalla_url,
        connect_timeout=settings.router_connect_timeout_seconds,
        read_timeout=settings.router_read_timeout_seconds,
    )
    if geocoder is None:
        if settings.geocoder_url and config.providers.geocoding.provider == "nominatim_local":
            geocoder = NominatimLocalGeocoder(
                settings.geocoder_url,
                user_agent=settings.user_agent,
                timeout=settings.geocoder_timeout_seconds,
                countrycodes=config.providers.geocoding.countrycodes,
            )
        else:
            geocoder = NullGeocoder()
    if session_factory is None and settings.database_url:
        session_factory = make_session_factory(make_engine(settings.database_url))
    if assessor is None and session_factory is not None:
        locator = ValhallaRoadLocator(settings.valhalla_url, connect_timeout=settings.router_connect_timeout_seconds, read_timeout=settings.router_read_timeout_seconds)
        service = AssessmentService(config, session_factory, routing, locator)
        assessor = lambda route, scope, snapshot_id: service.assess(route, scope=scope, snapshot_id=snapshot_id)  # noqa: E731

    app = FastAPI(title="DeFlockMigration API", version=__version__, docs_url="/api/docs" if settings.app_env != "production" else None, redoc_url=None, openapi_url="/api/openapi.json")
    app.state.settings = settings
    app.state.config = config
    app.state.routing = routing
    app.state.geocoder = geocoder
    app.state.session_factory = session_factory
    app.state.assessor = assessor
    app.state.metrics = Metrics()  # process-local counts and latencies; never trip data

    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"], max_age=600)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return _error_response(request, VALIDATION_ERROR, "Request body too large.", 413)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Counted by its declared route template (never the raw URL), then re-raised for the error handler.
            app.state.metrics.observe_request(_route_template(app, request.scope), 500, (time.perf_counter() - started) * 1000)
            raise
        response.headers["X-Request-ID"] = request_id
        duration_ms = (time.perf_counter() - started) * 1000
        app.state.metrics.observe_request(_route_template(app, request.scope), response.status_code, duration_ms)
        # Path only: query strings and bodies are never logged.
        log.info("%s %s -> %s in %.0f ms", request.method, request.url.path, response.status_code, duration_ms)
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return _error_response(request, exc.code, exc.message, exc.http_status, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        fields = sorted({".".join(str(p) for p in err.get("loc", []) if p != "body") for err in exc.errors()})
        return _error_response(request, VALIDATION_ERROR, "Request validation failed.", 400, {"fields": fields})

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        log.exception("unhandled error type=%s", type(exc).__name__)
        return _error_response(request, INTERNAL_ERROR, "Unexpected server error.", 500)

    app.include_router(region.router, prefix="/api/v1")
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(routes.router, prefix="/api/v1")
    app.include_router(geocode.router, prefix="/api/v1")
    app.include_router(cameras.router, prefix="/api/v1")
    return app
