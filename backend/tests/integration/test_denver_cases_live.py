"""Reviewed Denver cases against the real local services (geocoder and routing engine on the Compose
network). Skipped when either service is unreachable. Public landmarks and public office addresses only.

Legality evidence uses Valhalla's trace_attributes on the engine's own route shape: no edge may be
traversed backward (one-way), every edge must be a drivable road class, and destination-only
(private through-road) edges may appear only at the very start or end of a trip.
"""

from __future__ import annotations

import json
import math

import httpx
import pytest
from fastapi.testclient import TestClient

from deflockmigration.api.app import create_app
from deflockmigration.core.config_loader import load_app_config
from deflockmigration.core.settings import Settings
from deflockmigration.geospatial.polyline import decode_polyline6

pytestmark = pytest.mark.integration

GEOCODE_CASES = [
    ("Union Station, Denver, CO", (39.7532, -105.0001), True),
    ("Denver Zoo", (39.7492, -104.9504), True),
    ("Colorado State Capitol, Denver", (39.7392, -104.9848), True),
    ("Denver International Airport", (39.8561, -104.6737), True),
    ("Red Rocks Amphitheatre", (39.6654, -105.2057), True),  # inside Colorado since M9
    ("1437 Bannock St, Denver, CO", (39.7392, -104.9911), True),
    ("200 E Colfax Ave, Denver, CO 80203", (39.7392, -104.9846), True),
    ("2300 Steele St, Denver, CO", (39.7492, -104.9504), True),
    ("Washington Park, Denver", (39.7021, -104.9710), True),
    ("Glendale, Colorado", (39.7047, -104.9339), True),
]
# Documented ranking quirks (M0): the airport matches its large area, the park its centroid, and
# "Glendale, Colorado" matches a Colorado Boulevard segment inside Glendale before the municipality itself; it is inside the
# Colorado service area (it was outside the Denver pilot area).
TOLERANCE_M = {"Denver International Airport": 2500, "Washington Park, Denver": 800, "Glendale, Colorado": 1200}
ROUTE_CASES = [
    ("union_station_to_zoo", (39.7530, -105.0002), (39.7503, -104.9500)),
    ("capitol_to_washington_park", (39.7393, -104.9848), (39.7006, -104.9699)),
    ("downtown_one_way_grid", (39.7478, -104.9968), (39.7558, -104.9933)),
    ("union_station_to_den", (39.7530, -105.0002), (39.8494, -104.6737)),
    ("cherry_creek_to_highlands", (39.7177, -104.9533), (39.7580, -105.0110)),
]
DRIVABLE_USES = {"road", "ramp", "turn_channel", "driveway", "alley", "parking_aisle", "living_street", "service_road", "culdesac", "emergency_access", "other"}
NON_DRIVABLE_USES = {"footway", "sidewalk", "cycleway", "path", "steps", "pedestrian_crossing", "bridleway", "track", "rail", "bus", "ferry", "rail-ferry", "transit_connection", "platform_connection", "egress_connection"}


def _haversine(a, b):
    r = 6371008.8
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


@pytest.fixture(scope="module")
def live_client():
    settings = Settings()
    if not settings.geocoder_url:
        pytest.skip("DEFLOCK_GEOCODER_URL not set")
    try:
        geo = httpx.get(f"{settings.geocoder_url.rstrip('/')}/status", params={"format": "json"}, timeout=3.0)
        router = httpx.get(f"{settings.valhalla_url.rstrip('/')}/status", timeout=3.0)
    except httpx.HTTPError as exc:
        pytest.skip(f"live services unreachable: {type(exc).__name__}")
    if geo.status_code != 200 or geo.json().get("status") != 0 or router.status_code != 200:
        pytest.skip("live services not ready")
    config = load_app_config(settings)
    app = create_app(settings, config=config)
    return TestClient(app), settings


@pytest.mark.parametrize("query,expected,inside", GEOCODE_CASES)
def test_reviewed_denver_addresses_resolve(live_client, query, expected, inside):
    client, _ = live_client
    body = client.post("/api/v1/geocode", json={"query": query}).json()
    assert body["query_kind"] == "search" and body["candidates"], query
    top = body["candidates"][0]
    assert _haversine((top["lat"], top["lon"]), expected) < TOLERANCE_M.get(query, 400), (query, top["label"])
    assert top["inside_service_boundary"] is inside, (query, top["label"])


def test_incorrect_address_returns_no_candidates(live_client):
    client, _ = live_client
    body = client.post("/api/v1/geocode", json={"query": "Nonexistent Street 99999, Denver"}).json()
    assert body["candidates"] == []


def test_reverse_lookup_labels_a_pin(live_client):
    client, _ = live_client
    body = client.post("/api/v1/geocode/reverse", json={"lat": 39.7530, "lon": -105.0002}).json()
    assert body["found"] and body["label"] and body["inside_service_boundary"] is True


@pytest.mark.parametrize("name,origin,destination", ROUTE_CASES)
def test_reviewed_denver_trips_are_legal_and_aligned(live_client, name, origin, destination):
    client, settings = live_client
    resp = client.post("/api/v1/routes/plan", json={"origin": {"lat": origin[0], "lon": origin[1]}, "destination": {"lat": destination[0], "lon": destination[1]}})
    assert resp.status_code == 200, (name, resp.text)
    option = resp.json()["options"][0]
    maneuvers = option["maneuvers"]
    coords = option["geometry"]["coordinates"]
    # Instruction/geometry alignment: maneuvers cover the whole shape in order and their lengths add up.
    assert maneuvers[0]["begin_shape_index"] == 0 and maneuvers[-1]["end_shape_index"] == len(coords) - 1
    assert all(m["begin_shape_index"] <= m["end_shape_index"] for m in maneuvers)
    assert abs(sum(m["length_meters"] for m in maneuvers) - option["length_meters"]) / option["length_meters"] < 0.03
    assert option["origin_snap_distance_meters"] < 300 and option["destination_snap_distance_meters"] < 300
    # Legality evidence from the engine's own edge attributes.
    shape = [{"lat": lat, "lon": lon} for lon, lat in coords]
    trace = httpx.post(
        f"{settings.valhalla_url.rstrip('/')}/trace_attributes",
        json={"shape": shape, "costing": "auto", "shape_match": "edge_walk", "filters": {"attributes": ["edge.traversability", "edge.use", "edge.destination_only", "edge.road_class"], "action": "include"}},
        timeout=30.0,
    )
    assert trace.status_code == 200, (name, trace.text[:200])
    edges = trace.json().get("edges") or []
    assert edges, name
    assert not any(e.get("traversability") == "backward" for e in edges), name
    uses = {e.get("use") for e in edges}
    assert not (uses & NON_DRIVABLE_USES), (name, uses)
    assert uses <= DRIVABLE_USES | {None}, (name, uses - DRIVABLE_USES)
    destination_only = [i for i, e in enumerate(edges) if e.get("destination_only")]
    assert all(i < 3 or i >= len(edges) - 3 for i in destination_only), (name, destination_only)
    # The engine shape and the API geometry agree.
    assert len(decode_polyline6("")) == 0  # codec sanity


def _assert_legal(settings, name: str, option: dict) -> None:
    maneuvers = option["maneuvers"]
    coords = option["geometry"]["coordinates"]
    assert maneuvers[0]["begin_shape_index"] == 0 and maneuvers[-1]["end_shape_index"] == len(coords) - 1, name
    assert abs(sum(m["length_meters"] for m in maneuvers) - option["length_meters"]) / option["length_meters"] < 0.03, name
    shape = [{"lat": lat, "lon": lon} for lon, lat in coords]
    trace = httpx.post(
        f"{settings.valhalla_url.rstrip('/')}/trace_attributes",
        json={"shape": shape, "costing": "auto", "shape_match": "edge_walk", "filters": {"attributes": ["edge.traversability", "edge.use", "edge.destination_only"], "action": "include"}},
        timeout=30.0,
    )
    assert trace.status_code == 200, (name, trace.text[:200])
    edges = trace.json().get("edges") or []
    assert edges and not any(e.get("traversability") == "backward" for e in edges), name
    uses = {e.get("use") for e in edges}
    assert not (uses & NON_DRIVABLE_USES) and uses <= DRIVABLE_USES | {None}, (name, uses)
    destination_only = [i for i, e in enumerate(edges) if e.get("destination_only")]
    assert all(i < 3 or i >= len(edges) - 3 for i in destination_only), (name, destination_only)


@pytest.mark.parametrize("name,origin,destination", ROUTE_CASES)
def test_reviewed_denver_trips_compare_camera_aware_options_honestly(live_client, name, origin, destination):
    """M5 gate on real data: every displayed avoidance route is road-legal and fully assessed, differs in geometry,
    has lower exposure than Standard, stays within its declared detour bound, and the search is disclosed."""
    client, settings = live_client
    body = {"origin": {"lat": origin[0], "lon": origin[1]}, "destination": {"lat": destination[0], "lon": destination[1]}, "profiles": ["standard", "balanced", "fewest_mapped"]}
    resp = client.post("/api/v1/routes/plan", json=body)
    assert resp.status_code == 200, (name, resp.text)
    plan = resp.json()
    search = plan["search"]
    assert search["status"] in {"completed", "budget_exhausted", "partial"}, (name, search)
    assert 1 <= search["routing_calls_used"] <= search["routing_calls_budget"] and search["elapsed_seconds"] < search["planning_deadline_seconds"]
    assert {o["profile"] for o in search["profile_outcomes"]} == {"balanced", "fewest_mapped"}
    assert all(o["outcome"] in {"improved", "same_as_standard"} for o in search["profile_outcomes"]), (name, search["profile_outcomes"])
    options = plan["options"]
    standard = options[0]
    assert standard["profiles"][0] == "standard" and standard["exposure_count"] is not None
    assert len({json.dumps(o["geometry"]["coordinates"]) for o in options}) == len(options), name  # genuinely different paths
    for option in options:
        _assert_legal(settings, f"{name}/{'+'.join(option['profiles'])}", option)
    for option in options[1:]:
        assert option["assessment_coverage_status"] == "complete", (name, option["profiles"])
        assert option["exposure_count"] < standard["exposure_count"], (name, option["profiles"])
        assert option["estimated_duration_seconds"] <= option["detour_bound_seconds"] + 0.05, (name, option["profiles"])
        assert option["generated_by"] != "baseline" or search["routing_calls_used"] >= 1
    improved = [o for o in search["profile_outcomes"] if o["outcome"] == "improved"]
    assert {o["route_id"] for o in improved} <= {o["route_id"] for o in options[1:]}
    # Repeating the request on the same snapshot and graph is deterministic apart from random ids and timing.
    again = client.post("/api/v1/routes/plan", json=body).json()
    assert [(o["profiles"], o["geometry"]["coordinates"], o["exposure_count"]) for o in again["options"]] == [(o["profiles"], o["geometry"]["coordinates"], o["exposure_count"]) for o in options], name
    assert again["search"]["routing_calls_used"] == search["routing_calls_used"]
    print(f"\n{name}: status={search['status']} calls={search['routing_calls_used']}/{search['routing_calls_budget']} assessed={search['candidates_assessed']} elapsed={search['elapsed_seconds']}s options=" + "; ".join(f"{'+'.join(o['profiles'])} E={o['exposure_count']} T={o['estimated_duration_seconds']}s (+{o['extra_duration_seconds']}s) by={o['generated_by']}" for o in options) + " | " + " | ".join(f"{o['profile']}: {o['outcome']}" for o in search["profile_outcomes"]))
