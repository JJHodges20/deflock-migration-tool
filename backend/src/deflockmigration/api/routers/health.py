from __future__ import annotations

from fastapi import APIRouter, Request

from deflockmigration import __version__
from deflockmigration.application.data_health import as_dict, build_data_health

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict:
    return {"status": "ok", "service": "deflockmigration-api", "version": __version__}


@router.get("/health/data")
def data_health(request: Request) -> dict:
    state = request.app.state
    health = build_data_health(state.config, session_factory=state.session_factory, routing=state.routing, geocoder=state.geocoder)
    return as_dict(health)
