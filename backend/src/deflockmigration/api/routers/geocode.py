from __future__ import annotations

from fastapi import APIRouter, Request

from deflockmigration.api.schemas import GeocodeCandidateOut, GeocodeRequest, GeocodeResponse
from deflockmigration.geocoding.provider import parse_coordinate_pair

router = APIRouter(tags=["geocode"])


@router.post("/geocode", response_model=GeocodeResponse)
def geocode(body: GeocodeRequest, request: Request) -> GeocodeResponse:
    """Submit-only address lookup. Coordinate pairs never reach a provider."""
    state = request.app.state
    boundary = state.config.service_boundary
    direct = parse_coordinate_pair(body.query)
    if direct is not None:
        return GeocodeResponse(
            query_kind="coordinates",
            provider="coordinates",
            candidates=[GeocodeCandidateOut(**direct.__dict__, inside_service_boundary=boundary.contains(direct.lat, direct.lon))],
        )
    geocoder = state.geocoder
    candidates = geocoder.search(body.query, limit=body.limit, viewbox_wsen=state.config.envelope.bbox_wsen)
    return GeocodeResponse(
        query_kind="search",
        provider=geocoder.name,
        candidates=[GeocodeCandidateOut(**c.__dict__, inside_service_boundary=boundary.contains(c.lat, c.lon)) for c in candidates],
    )
