from __future__ import annotations

import json

import httpx
import pytest

from deflockmigration.core.errors import GEOCODER_NOT_CONFIGURED, GEOCODER_UNAVAILABLE, NO_DRIVABLE_ROUTE, ROUTER_UNAVAILABLE, AppError
from deflockmigration.domain.routes import LatLon
from deflockmigration.geocoding.nominatim_local import NominatimLocalGeocoder
from deflockmigration.geocoding.provider import NullGeocoder, parse_coordinate_pair
from deflockmigration.routing.valhalla import ValhallaProvider

A, B = LatLon(39.7530, -105.0002), LatLon(39.7503, -104.9500)


def _provider(handler):
    return ValhallaProvider("http://valhalla.test:8002", transport=httpx.MockTransport(handler))


def test_route_parsing_uses_only_documented_parameters(valhalla_fixture_payload):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=valhalla_fixture_payload)

    routes = _provider(handler).baseline_candidates(A, B, alternates=2, request_id="req1")
    assert set(seen) == {"locations", "costing", "units", "alternates", "id"}
    assert seen["costing"] == "auto" and seen["alternates"] == 2 and seen["id"] == "req1"
    assert len(routes) == 3 and routes[0].source == "primary" and routes[1].source == "alternate"
    assert routes[0].length_m == pytest.approx(12414, abs=1) and routes[0].duration_s == pytest.approx(730.7, abs=0.1)
    assert routes[0].maneuvers[0].type == 3 and routes[0].maneuvers[-1].type == 4
    assert routes[0].maneuvers[4].length_m == pytest.approx(1453, abs=1)


def test_no_edges_error_maps_to_no_drivable_route():
    payload = json.loads((__import__("pathlib").Path(__file__).parent.parent / "fixtures" / "fixture_valhalla_no_edges_error.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json=payload)

    with pytest.raises(AppError) as exc:
        _provider(handler).baseline_candidates(A, B, alternates=2, request_id="r")
    assert exc.value.code == NO_DRIVABLE_ROUTE and exc.value.details["engine_error_code"] == 171


def test_connection_error_maps_to_router_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(AppError) as exc:
        _provider(handler).baseline_candidates(A, B, alternates=0, request_id="r")
    assert exc.value.code == ROUTER_UNAVAILABLE
    status = _provider(handler).status()
    assert status.available is False and "unreachable" in status.message


def test_status_parses_verbose_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"version": "3.9.1", "tileset_last_modified": 1792096128, "has_tiles": True, "has_admins": True, "has_timezones": True})

    status = _provider(handler).status()
    assert status.available and status.version == "3.9.1" and status.tileset_last_modified == "2026-10-15T20:28:48Z"


def test_coordinate_pair_parsing():
    assert parse_coordinate_pair("39.7530, -105.0002").lat == 39.753
    assert parse_coordinate_pair(" 39.7530 -105.0002 ").lon == -105.0002
    assert parse_coordinate_pair("95, 100") is None  # invalid in either order
    swapped = parse_coordinate_pair("95, 0")  # longitude first: swapped with a note (M3)
    assert swapped is not None and swapped.lat == 0 and swapped.lon == 95 and swapped.note
    assert parse_coordinate_pair("Union Station") is None
    assert parse_coordinate_pair("1701 Wynkoop St") is None


def test_null_geocoder_reports_not_configured():
    with pytest.raises(AppError) as exc:
        NullGeocoder().search("x", limit=5, viewbox_wsen=None)
    assert exc.value.code == GEOCODER_NOT_CONFIGURED
    assert NullGeocoder().status().configured is False


def test_public_nominatim_is_refused():
    with pytest.raises(ValueError):
        NominatimLocalGeocoder("https://nominatim.openstreetmap.org", user_agent="x")


def test_local_nominatim_search_and_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": 0, "message": "OK", "data_updated": "2026-10-14T20:20:43+00:00"})
        assert request.url.params["q"] == "Union Station, Denver" and request.url.params["countrycodes"] == "us" and "viewbox" in request.url.params
        return httpx.Response(200, json=[{"display_name": "Union Station, Denver", "lat": "39.7532", "lon": "-105.0001", "addresstype": "railway", "importance": 0.6}, {"bad": "row"}])

    g = NominatimLocalGeocoder("http://geocoder.test:8080", user_agent="DeFlockMigration-test", transport=httpx.MockTransport(handler))
    status = g.status()
    assert status.configured and status.available and status.data_updated.startswith("2026-10-14")
    results = g.search("Union Station, Denver", limit=5, viewbox_wsen=(-105.3, 39.4, -104.3, 40.1))
    assert len(results) == 1 and results[0].source == "nominatim_local" and results[0].lat == 39.7532

    def failing(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(AppError) as exc:
        NominatimLocalGeocoder("http://geocoder.test:8080", user_agent="t", transport=httpx.MockTransport(failing)).search("x", limit=1, viewbox_wsen=None)
    assert exc.value.code == GEOCODER_UNAVAILABLE


def test_avoidance_request_uses_documented_penalties_and_exclusions(valhalla_fixture_payload):
    from deflockmigration.domain.routes import AvoidanceRequest, PenaltySegment
    from deflockmigration.geospatial.polyline import decode_polyline6

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={**valhalla_fixture_payload, "warnings": [{"code": 208, "text": "Hard exclusions are not allowed on this server, ignoring hard excludes"}]})

    segment = PenaltySegment([(39.7530, -105.0002), (39.7531, -105.0001), (39.7532, -105.0000)], 40.0, ("osm:node:1",))
    routes = _provider(handler).avoiding_candidates(A, B, alternates=2, request_id="req2", avoidance=AvoidanceRequest("penalized", penalties=[segment], exclusions=[LatLon(39.76, -104.99)]))
    assert set(seen) == {"locations", "costing", "units", "alternates", "id", "linear_cost_factors", "exclude_locations"}
    assert seen["linear_cost_factors"][0]["factor"] == 40.0
    assert decode_polyline6(seen["linear_cost_factors"][0]["shape"]) == [(39.753, -105.0002), (39.7531, -105.0001), (39.7532, -105.0)]
    assert seen["exclude_locations"] == [{"lat": 39.76, "lon": -104.99}]
    assert routes[0].source == "penalized" and routes[1].source == "penalized" and routes[0].engine_route_id == "penalized-0"
    assert routes[0].warnings == ["Hard exclusions are not allowed on this server, ignoring hard excludes"]  # engine warnings are surfaced, never dropped


def test_avoidance_request_refuses_undocumented_inputs(valhalla_fixture_payload):
    from deflockmigration.domain.routes import AvoidanceRequest, PenaltySegment

    provider = _provider(lambda request: httpx.Response(200, json=valhalla_fixture_payload))
    with pytest.raises(ValueError):
        provider.avoiding_candidates(A, B, alternates=0, request_id="r", avoidance=AvoidanceRequest("excluded", exclusions=[LatLon(39.7, -105.0)] * 51))
    with pytest.raises(ValueError):
        provider.avoiding_candidates(A, B, alternates=0, request_id="r", avoidance=AvoidanceRequest("penalized", penalties=[PenaltySegment([(39.7, -105.0), (39.71, -105.0)], 0.5)]))
    with pytest.raises(ValueError):
        provider.avoiding_candidates(A, B, alternates=0, request_id="r", avoidance=AvoidanceRequest("penalized"))


def test_exclusion_limit_error_maps_to_router_unavailable_and_no_path_to_no_route():
    from deflockmigration.domain.routes import AvoidanceRequest

    def limit_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error_code": 157, "error": "Exceeded max avoid locations: 50", "status_code": 400})

    with pytest.raises(AppError) as exc:
        _provider(limit_handler).avoiding_candidates(A, B, alternates=0, request_id="r", avoidance=AvoidanceRequest("excluded", exclusions=[LatLon(39.7, -105.0)]))
    assert exc.value.code == ROUTER_UNAVAILABLE and exc.value.details["engine_error_code"] == 157

    def no_path_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error_code": 170, "error": "No path could be found for input", "status_code": 400})

    with pytest.raises(AppError) as exc2:
        _provider(no_path_handler).avoiding_candidates(A, B, alternates=0, request_id="r", avoidance=AvoidanceRequest("excluded", exclusions=[LatLon(39.7, -105.0)]))
    assert exc2.value.code == NO_DRIVABLE_ROUTE
