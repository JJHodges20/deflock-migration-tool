from __future__ import annotations

from fastapi import APIRouter, Request

from deflockmigration.api.schemas import GeocodeCandidateOut, GeocodeRequest, GeocodeResponse, ReverseGeocodeRequest, ReverseGeocodeResponse
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
    # The geocoder's own ranking is kept (the envelope viewbox already biases it); each candidate carries an
    # inside/outside flag and the user confirms. Reordering silently would change what "first match" means.
    candidates = geocoder.search(body.query, limit=body.limit, viewbox_wsen=state.config.envelope.bbox_wsen)
    return GeocodeResponse(
        query_kind="search",
        provider=geocoder.name,
        candidates=[GeocodeCandidateOut(**c.__dict__, inside_service_boundary=boundary.contains(c.lat, c.lon)) for c in candidates],
    )


@router.post("/geocode/reverse", response_model=ReverseGeocodeResponse)
def reverse_geocode(body: ReverseGeocodeRequest, request: Request) -> ReverseGeocodeResponse:
    """Label a map pin with the nearest mapped address or place. The pin's own coordinates are kept by the client."""
    state = request.app.state
    boundary = state.config.service_boundary
    result = state.geocoder.reverse(body.lat, body.lon)
    return ReverseGeocodeResponse(
        provider=state.geocoder.name,
        found=result is not None,
        label=result.label if result else None,
        category=result.category if result else None,
        matched_lat=result.matched_lat if result else None,
        matched_lon=result.matched_lon if result else None,
        inside_service_boundary=boundary.contains(body.lat, body.lon),
    )
