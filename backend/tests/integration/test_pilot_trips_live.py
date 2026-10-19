"""M8 pilot fixture set: the reviewed public-landmark trips in `data/fixtures/pilot_trips.json`, planned live with all
three preferences through the API against the local engine and camera snapshot. Skipped when the live services are
unreachable. Checks the expected outcome, endpoint snapping, legality of every displayed option via the engine's own
edge attributes, complete assessment and lower exposure for every avoidance option, and distinct geometries.
Camera counts are printed, never asserted: they change with every published snapshot.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from tests.integration.test_denver_cases_live import DRIVABLE_USES, NON_DRIVABLE_USES, live_client  # noqa: F401 - fixture import

pytestmark = pytest.mark.integration
FIXTURE = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "pilot_trips.json"
TRIPS = json.loads(FIXTURE.read_text(encoding="utf-8"))["trips"]


def _assert_legal(settings, name: str, option: dict) -> None:
    """Every displayed option must be drivable by the engine's own account.

    The auto-costed ``edge_walk`` match only follows edges the costing allows in the direction of travel (the engine
    answers HTTP 400 for a shape walked against a one-way), so a successful walk is the legality check itself.
    ``edge.traversability`` is relative to the OpenStreetMap way's drawn direction, not to the direction of travel: a
    way tagged ``oneway=-1`` reports ``backward`` while being driven legally (found on the Colorado Springs case in M9).
    For those edges the directed edge the route uses is confirmed through ``/locate``: it must carry car access and run
    against the drawn direction.
    """
    maneuvers = option["maneuvers"]
    coords = option["geometry"]["coordinates"]
    assert maneuvers[0]["begin_shape_index"] == 0 and maneuvers[-1]["end_shape_index"] == len(coords) - 1, name
    assert abs(sum(m["length_meters"] for m in maneuvers) - option["length_meters"]) / option["length_meters"] < 0.03, name
    shape = [{"lat": lat, "lon": lon} for lon, lat in coords]
    base = settings.valhalla_url.rstrip("/")
    attributes = ["edge.traversability", "edge.use", "edge.destination_only", "edge.id", "edge.begin_shape_index", "edge.end_shape_index"]
    trace = httpx.post(
        f"{base}/trace_attributes",
        json={"shape": shape, "costing": "auto", "shape_match": "edge_walk", "filters": {"attributes": attributes, "action": "include"}},
        timeout=30.0,
    )
    assert trace.status_code == 200, (name, trace.text[:200])
    edges = trace.json().get("edges") or []
    assert edges, name
    assert all(e.get("traversability") in {"forward", "backward", "both"} for e in edges), (name, {e.get("traversability") for e in edges})
    for i, e in enumerate(edges):
        if e.get("traversability") != "backward":
            continue
        b, en = e["begin_shape_index"], e["end_shape_index"]
        lon, lat = coords[(b + en) // 2] if en - b >= 2 else ((coords[b][0] + coords[en][0]) / 2, (coords[b][1] + coords[en][1]) / 2)
        located = httpx.post(f"{base}/locate", json={"locations": [{"lat": lat, "lon": lon}], "costing": "auto", "verbose": True}, timeout=30.0)
        assert located.status_code == 200, (name, i, located.text[:200])
        same = [c for loc in located.json() for c in loc.get("edges", []) if c.get("edge_id", {}).get("value") == e.get("id")]
        assert same, (name, i, e.get("id"))
        edge = same[0]["edge"]
        assert edge.get("access", {}).get("car") is True and edge.get("forward") is False, (name, i, edge.get("access"), edge.get("forward"))
    uses = {e.get("use") for e in edges}
    assert not (uses & NON_DRIVABLE_USES) and uses <= DRIVABLE_USES | {None}, (name, uses)
    destination_only = [i for i, e in enumerate(edges) if e.get("destination_only")]
    assert all(i < 3 or i >= len(edges) - 3 for i in destination_only), (name, destination_only)


@pytest.mark.parametrize("trip", TRIPS, ids=[t["name"] for t in TRIPS])
def test_pilot_trip(live_client, trip):
    client, settings = live_client
    origin, destination = trip["origin"], trip["destination"]
    body = {"origin": {"lat": origin[0], "lon": origin[1]}, "destination": {"lat": destination[0], "lon": destination[1]}, "profiles": ["standard", "balanced", "fewest_mapped"]}
    resp = client.post("/api/v1/routes/plan", json=body)
    expected = trip["expect"]["outcome"]
    if expected != "planned":
        assert resp.status_code in (400, 422), (trip["name"], resp.text[:200])
        assert resp.json()["error"]["code"] == expected, (trip["name"], resp.json())
        print(f"\n{trip['name']}: {expected} as expected ({trip['covers']})")
        return
    assert resp.status_code == 200, (trip["name"], resp.text[:300])
    plan = resp.json()
    options = plan["options"]
    standard = options[0]
    assert standard["profiles"][0] == "standard"
    assert standard["origin_snap_distance_meters"] <= trip["expect"]["max_snap_m"] and standard["destination_snap_distance_meters"] <= trip["expect"]["max_snap_m"], trip["name"]
    assert len({json.dumps(o["geometry"]["coordinates"]) for o in options}) == len(options), trip["name"]
    for option in options:
        _assert_legal(settings, f"{trip['name']}/{'+'.join(option['profiles'])}", option)
    for option in options[1:]:
        assert option["assessment_coverage_status"] == "complete", (trip["name"], option["profiles"])
        assert standard["exposure_count"] is not None and option["exposure_count"] < standard["exposure_count"], (trip["name"], option["profiles"])
        assert option["estimated_duration_seconds"] <= option["detour_bound_seconds"] + 0.05, (trip["name"], option["profiles"])
    search = plan["search"]
    assert search["status"] in {"completed", "budget_exhausted", "partial", "not_run"}
    summary = "; ".join(f"{'+'.join(o['profiles'])} E={o['exposure_count']} T={o['estimated_duration_seconds']}s (+{o['extra_duration_seconds']}s) {o['assessment_coverage_status']}" for o in options)
    print(f"\n{trip['name']}: {search['status']} calls={search['routing_calls_used']} elapsed={search['elapsed_seconds']}s snap={standard['origin_snap_distance_meters']}/{standard['destination_snap_distance_meters']}m | {summary} ({trip['covers']})")
