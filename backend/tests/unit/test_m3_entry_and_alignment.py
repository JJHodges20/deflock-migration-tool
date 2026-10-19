from __future__ import annotations

import httpx
import pytest

from deflockmigration.core.errors import GEOCODER_NOT_CONFIGURED, AppError
from deflockmigration.domain.routes import EngineRoute, LatLon, Maneuver
from deflockmigration.geocoding.nominatim_local import NominatimLocalGeocoder
from deflockmigration.geocoding.provider import GeocodeCandidate, NullGeocoder, dedupe_candidates, parse_coordinate_pair
from deflockmigration.routing.candidates import alignment_warnings, snap_distances_m, validate_maneuvers
from deflockmigration.routing.valhalla import ValhallaProvider
from tests.conftest import route_from_trip

A, B = LatLon(39.7530, -105.0002), LatLon(39.7503, -104.9500)


def test_swapped_coordinates_are_recognised_and_explained():
    swapped = parse_coordinate_pair("-105.0002, 39.7530")
    assert swapped is not None and swapped.lat == 39.753 and swapped.lon == -105.0002
    assert swapped.note and "swapped" in swapped.note and "longitude, latitude" in swapped.label
    normal = parse_coordinate_pair("39.7530, -105.0002")
    assert normal is not None and normal.note is None
    assert parse_coordinate_pair("-105.0002, 100") is None  # neither order is valid


def test_candidate_dedupe_keeps_first_of_identical_points():
    a = GeocodeCandidate("Union Station", 39.7532277, -105.0000944, "nominatim_local")
    b = GeocodeCandidate("Union Station (duplicate)", 39.7532279, -105.0000941, "nominatim_local")
    c = GeocodeCandidate("Elsewhere", 39.76, -105.0, "nominatim_local")
    assert [x.label for x in dedupe_candidates([a, b, c])] == ["Union Station", "Elsewhere"]


def test_reverse_lookup_adapter_and_null_geocoder():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/reverse") and request.url.params["zoom"] == "18"
        if request.url.params["lat"] == "0.0":
            return httpx.Response(200, json={"error": "Unable to geocode"})
        return httpx.Response(200, json={"display_name": "1701 Wynkoop Street, Denver", "lat": "39.7533", "lon": "-105.0001", "addresstype": "building"})

    geocoder = NominatimLocalGeocoder("http://geocoder.test:8080", user_agent="t", transport=httpx.MockTransport(handler))
    result = geocoder.reverse(39.753, -105.0002)
    assert result is not None and result.label.startswith("1701 Wynkoop") and result.matched_lat == 39.7533
    assert geocoder.reverse(0.0, 0.0) is None
    with pytest.raises(AppError) as exc:
        NullGeocoder().reverse(39.75, -105.0)
    assert exc.value.code == GEOCODER_NOT_CONFIGURED


def test_snap_distances_from_fixture_route(valhalla_fixture_payload):
    route = route_from_trip(valhalla_fixture_payload["trip"], "primary", 0)
    origin_snap, destination_snap = snap_distances_m(route, A, B)
    assert 0 <= origin_snap < 100 and 0 <= destination_snap < 200
    far = LatLon(39.70, -104.90)
    assert snap_distances_m(route, far, B)[0] > 5000


def test_alignment_checks_on_fixture_and_synthetic_routes(valhalla_fixture_payload):
    route = route_from_trip(valhalla_fixture_payload["trip"], "primary", 0)
    assert validate_maneuvers(route) == []
    assert alignment_warnings(route) == []
    # A route whose maneuvers stop short of the shape end is rejected; one whose lengths disagree gets a warning.
    short = EngineRoute("x", route.shape, route.duration_s, route.length_m, route.maneuvers[:-1] + [Maneuver("Arrive", 4, 0, 0, route.maneuvers[-1].begin_shape_index, len(route.shape) - 5)], False, False)
    assert any("span the whole shape" in p for p in validate_maneuvers(short))
    inflated = EngineRoute("y", route.shape, route.duration_s, route.length_m * 2, route.maneuvers, False, False)
    assert alignment_warnings(inflated) and "differ" in alignment_warnings(inflated)[0]


def test_valhalla_adapter_converts_miles(valhalla_fixture_payload):
    payload = {"trip": dict(valhalla_fixture_payload["trip"], units="miles")}
    payload["trip"]["summary"] = dict(payload["trip"]["summary"], length=7.714)  # 12.414 km expressed in miles

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    routes = ValhallaProvider("http://valhalla.test:8002", transport=httpx.MockTransport(handler)).baseline_candidates(A, B, alternates=0, request_id="u")
    assert routes[0].length_m == pytest.approx(12414, rel=0.001)
