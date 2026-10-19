from __future__ import annotations

from fastapi import APIRouter, Request

from deflockmigration import __version__
from deflockmigration.application.data_health import as_dict, build_data_health, storage_stats
from deflockmigration.core.metrics import process_memory_mb

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict:
    return {"status": "ok", "service": "deflockmigration-api", "version": __version__}


@router.get("/health/data")
def data_health(request: Request) -> dict:
    state = request.app.state
    health = build_data_health(state.config, session_factory=state.session_factory, routing=state.routing, geocoder=state.geocoder)
    return as_dict(health)


@router.get("/health/metrics")
def metrics(request: Request) -> dict:
    """Resource and service metrics without trip data (roadmap sections 13 and 16): request counts and latency summaries
    per route template, plan outcomes, process memory, and public-data storage sizes."""
    state = request.app.state
    data = state.metrics.snapshot() if getattr(state, "metrics", None) is not None else {"meaning": "metrics not enabled"}
    data["process"] = {"version": __version__, "rss_mb": process_memory_mb()}
    data["storage"] = storage_stats(state.session_factory)
    return data
