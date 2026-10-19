"""M4 assessment matrix on a synthetic east-west street with explicit, metric fixtures.

Cases (roadmap M4): parallel frontage road, overpass, camera far from a road, ambiguous orientation,
multiple cameras on one pole, route touches the buffer edge, endpoint next to a camera, loops,
outside-envelope detour, and 25/50/100 m sensitivity. No degrees are ever treated as meters.
"""

from __future__ import annotations

import math

from shapely.geometry import box

from deflockmigration.application.assess_route import assess_route
from deflockmigration.domain.assessment import CameraNearRoute, EncounterStatus, RoadCandidate, RouteEdge
from deflockmigration.domain.routes import CameraScope, EngineRoute, Maneuver
from deflockmigration.geospatial.metric import haversine_m, passes_along_route
from deflockmigration.geospatial.proximity import MemoryProximityIndex

LAT0, LON0 = 39.7400, -104.9900  # downtown Denver scale
M_PER_DEG_LAT = 111320.0
M_PER_DEG_LON = 111320.0 * math.cos(math.radians(LAT0))
MAIN_WAY, FRONTAGE_WAY, BRIDGE_WAY, SIDE_WAY = 1001, 1002, 1003, 1004


def offset(east_m: float, north_m: float) -> tuple[float, float]:
    return (LAT0 + north_m / M_PER_DEG_LAT, LON0 + east_m / M_PER_DEG_LON)


def record(key: str, east_m: float, north_m: float, **kw) -> CameraNearRoute:
    lat, lon = offset(east_m, north_m)
    base = dict(source_key=key, lat=lat, lon=lon, is_alpr=True, is_flock=True, manufacturer="flock_safety", lifecycle_state="mapped",
                direction_raw="90", direction_parsed_deg=90.0, direction_conflict=False, in_envelope=True, operator=None, source_timestamp=None, check_date=None, distance_m=0.0)
    base.update(kw)
    return CameraNearRoute(**base)


def straight_route(length_m: float = 2000.0, step_m: float = 50.0) -> EngineRoute:
    shape = [offset(x, 0.0) for x in range(0, int(length_m) + 1, int(step_m))]
    return EngineRoute("r", shape, length_m / 13.9, length_m, [Maneuver("Start", 1, length_m, 1, 0, len(shape) - 1), Maneuver("Arrive", 4, 0, 0, len(shape) - 1, len(shape) - 1)], False, False)


def edges_for(route: EngineRoute, way_id: int = MAIN_WAY, names=("Main Street",)) -> list[RouteEdge]:
    return [RouteEdge(way_id, list(names), 0, len(route.shape) - 1, "secondary", "road", False, False, 90.0, 90.0, route.length_m)]


def locator_with(roads: dict[str, list[RoadCandidate]]):
    """roads: source_key -> candidates. Keys are matched by nearest record coordinates via a closure built per test."""

    def locate(lat: float, lon: float, radius_m: float) -> list[RoadCandidate]:
        for key, candidates in roads.items():
            rlat, rlon = ANCHORS[key]
            if haversine_m((lat, lon), (rlat, rlon)) < 0.5:
                return [c for c in candidates if c.distance_m <= radius_m]
        return []

    return locate


ANCHORS: dict[str, tuple[float, float]] = {}


def register(records: list[CameraNearRoute]) -> list[CameraNearRoute]:
    for r in records:
        ANCHORS[r.source_key] = (r.lat, r.lon)
    return records


def main_road(distance_m: float, **kw) -> RoadCandidate:
    return RoadCandidate(MAIN_WAY, ["Main Street"], distance_m, "secondary", "road", False, False, **kw)


def run(records, roads, route=None, scope=CameraScope.ALL_ALPR, envelope=None, route_edges=None):
    route = route or straight_route()
    index = MemoryProximityIndex(register(records), envelope)
    return assess_route(route, scope=scope, snapshot_id="snap-1", graph_version="graph-1", proximity=index, route_edges=route_edges or edges_for(route), locate=locator_with(roads))


def test_camera_on_the_traversed_road_is_associated_and_explained():
    cam = record("osm:node:1", 500, 8)
    result = run([cam], {"osm:node:1": [main_road(8.0)]})
    assert result.status == "complete" and result.matched_record_count == 1 and result.uncertain_record_count == 0
    enc = result.encounters[0]
    assert enc.status is EncounterStatus.ASSOCIATED and enc.association.same_road and "Main Street" in enc.reason
    assert 490 < enc.position_m < 510 and enc.pass_count == 1 and enc.source_url.endswith("/node/1")
    assert "not used for counting" in enc.heading_relation


def test_parallel_frontage_road_is_uncertain_not_matched():
    cam = record("osm:node:2", 500, 30)  # 30 m north of the main road, sitting on a frontage road 5 m away from it
    roads = {"osm:node:2": [RoadCandidate(FRONTAGE_WAY, ["Frontage Road"], 5.0, "residential", "road", False, False), main_road(30.0)]}
    result = run([cam], roads)
    assert result.matched_record_count == 0 and result.uncertain_record_count == 1
    enc = result.encounters[0]
    assert enc.status is EncounterStatus.NEARBY_UNRESOLVED and not enc.association.same_road and "parallel or frontage" in enc.reason
    assert enc.association.nearest_road_names == ["Frontage Road"] and enc.association.route_road_names == ["Main Street"]


def test_overpass_crossing_is_uncertain_with_grade_separation_flag():
    cam = record("osm:node:3", 800, 4)  # on a bridge that crosses over the route
    roads = {"osm:node:3": [RoadCandidate(BRIDGE_WAY, ["Overpass Avenue"], 3.0, "primary", "road", True, False), main_road(4.0)]}
    result = run([cam], roads)
    enc = result.encounters[0]
    assert enc.status is EncounterStatus.NEARBY_UNRESOLVED and enc.association.grade_separated and "bridge or tunnel" in enc.reason
    assert result.matched_record_count == 0 and result.uncertain_record_count == 1


def test_ambiguous_equally_close_roads_stay_uncertain():
    cam = record("osm:node:4", 300, 6)
    roads = {"osm:node:4": [main_road(6.0), RoadCandidate(SIDE_WAY, ["Side Street"], 9.0, "residential", "road", False, False)]}
    result = run([cam], roads)
    enc = result.encounters[0]
    assert enc.status is EncounterStatus.NEARBY_UNRESOLVED and enc.association.ambiguous and "ambiguous" in enc.reason


def test_split_segments_of_the_same_street_count_as_the_same_road():
    # The route traverses way 1001 "Main Street"; the camera's nearest candidate is way 1006, another
    # OpenStreetMap segment of the same street (split ways are the norm, not a different road).
    cam = record("osm:node:40", 500, 6)
    roads = {"osm:node:40": [RoadCandidate(1006, ["Main Street"], 6.0, "secondary", "road", False, False), RoadCandidate(1001, ["Main Street"], 7.0, "secondary", "road", False, False)]}
    result = run([cam], roads)
    enc = result.encounters[0]
    assert enc.status is EncounterStatus.ASSOCIATED and not enc.association.ambiguous and enc.association.same_road
    assert result.matched_record_count == 1


def test_name_match_is_local_to_the_pass_not_the_whole_route():
    # First 1 km of the route is "Main Street", the rest "Other Street". A camera at 1.8 km sits on a
    # "Main Street" segment (a different street of the same name elsewhere) and must not be associated.
    route = straight_route(2000)
    n = len(route.shape) - 1
    edges = [RouteEdge(MAIN_WAY, ["Main Street"], 0, 20, "secondary", "road", False, False, 90.0, 90.0, 1000.0), RouteEdge(SIDE_WAY, ["Other Street"], 20, n, "secondary", "road", False, False, 90.0, 90.0, 1000.0)]
    cam = record("osm:node:41", 1800, 6)
    roads = {"osm:node:41": [RoadCandidate(1007, ["Main Street"], 6.0, "secondary", "road", False, False), RoadCandidate(SIDE_WAY, ["Other Street"], 20.0, "secondary", "road", False, False)]}
    result = run([cam], roads, route=route, route_edges=edges)
    enc = result.encounters[0]
    assert enc.status is EncounterStatus.NEARBY_UNRESOLVED and enc.association.route_road_names == ["Other Street"]


def test_unnamed_different_way_as_close_as_the_street_is_ambiguous():
    cam = record("osm:node:42", 500, 6)
    roads = {"osm:node:42": [main_road(6.0), RoadCandidate(2000, [], 8.0, "service", "road", False, False)]}
    result = run([cam], roads)
    enc = result.encounters[0]
    assert enc.status is EncounterStatus.NEARBY_UNRESOLVED and enc.association.ambiguous and "unnamed way 2000" in enc.reason


def test_camera_far_from_any_road_is_not_an_encounter_at_all():
    cam = record("osm:node:5", 500, 200)
    result = run([cam], {"osm:node:5": []})
    assert result.encounters == [] and result.matched_record_count == 0 and all(s.records_within == 0 for s in result.sensitivity)


def test_conflicting_orientation_is_reported_but_never_excludes():
    cam = record("osm:node:6", 500, 5, direction_raw="90", direction_parsed_deg=None, direction_conflict=True)
    result = run([cam], {"osm:node:6": [main_road(5.0)]})
    enc = result.encounters[0]
    assert enc.status is EncounterStatus.ASSOCIATED and "conflict" in enc.heading_relation


def test_multiple_cameras_on_one_pole_count_individually_and_share_a_site():
    cams = [record("osm:node:7", 600, 5, direction_raw="0", direction_parsed_deg=0.0), record("osm:node:8", 600.5, 5.2, direction_raw="185", direction_parsed_deg=185.0), record("osm:node:9", 600.2, 4.8, direction_raw="99", direction_parsed_deg=99.0)]
    roads = {k: [main_road(5.0)] for k in ("osm:node:7", "osm:node:8", "osm:node:9")}
    result = run(cams, roads)
    assert result.matched_record_count == 3
    assert len({e.site_group_id for e in result.encounters}) == 1 and result.encounters[0].site_group_id == "osm:node:7"


def test_buffer_edge_and_sensitivity_radii():
    cams = [record("osm:node:10", 200, 20), record("osm:node:11", 400, 45), record("osm:node:12", 700, 80)]
    roads = {"osm:node:10": [main_road(20.0)], "osm:node:11": [main_road(45.0)], "osm:node:12": [main_road(80.0)]}
    result = run(cams, roads)
    by_key = {e.source_key: e for e in result.encounters}
    assert by_key["osm:node:10"].status is EncounterStatus.ASSOCIATED
    assert by_key["osm:node:11"].status is EncounterStatus.ASSOCIATED  # inside the 50 m counting radius
    assert by_key["osm:node:12"].status is EncounterStatus.BEYOND_RADIUS  # only the 100 m sensitivity radius
    assert [(s.radius_m, s.records_within) for s in result.sensitivity] == [(25, 1), (50, 2), (100, 3)]
    assert result.matched_record_count == 2


def test_endpoint_next_to_a_camera_is_counted_and_flagged():
    cam = record("osm:node:13", 3, 4)
    result = run([cam], {"osm:node:13": [main_road(4.0)]})
    enc = result.encounters[0]
    assert enc.status is EncounterStatus.ASSOCIATED and enc.position_fraction < 0.01 and "start or end" in enc.reason


def test_loop_passes_the_same_camera_twice_but_counts_once():
    out = [offset(x, 0.0) for x in range(0, 1001, 50)]
    back = [offset(x, 0.0) for x in range(1000, -1, -50)]
    route = EngineRoute("loop", out + back[1:], 200, 2000, [Maneuver("Start", 1, 2000, 1, 0, 40), Maneuver("Arrive", 4, 0, 0, 40, 40)], False, False)
    cam = record("osm:node:14", 500, 5)
    result = run([cam], {"osm:node:14": [main_road(5.0)]}, route=route)
    enc = result.encounters[0]
    assert enc.pass_count == 2 and result.matched_record_count == 1
    assert any("more than once" in w for w in result.warnings)


def test_outside_envelope_detour_is_partial_and_records_outside_are_uncertain():
    route = straight_route(2000)
    envelope = box(LON0 - 0.01, LAT0 - 0.01, offset(1000, 0)[1], LAT0 + 0.01)  # envelope ends halfway along the route
    cams = [record("osm:node:15", 300, 5), record("osm:node:16", 1500, 5, in_envelope=False)]
    roads = {"osm:node:15": [main_road(5.0)], "osm:node:16": [main_road(5.0)]}
    result = run(cams, roads, route=route, envelope=envelope)
    assert result.status == "partial" and 0.45 < result.coverage_fraction < 0.55
    assert any("not complete" in w for w in result.warnings)
    by_key = {e.source_key: e for e in result.encounters}
    assert by_key["osm:node:15"].status is EncounterStatus.ASSOCIATED
    assert by_key["osm:node:16"].status is EncounterStatus.OUTSIDE_ENVELOPE
    assert result.matched_record_count == 1 and result.uncertain_record_count == 1


def test_scope_flock_only_excludes_other_manufacturers_from_counts_but_lists_them():
    cams = [record("osm:node:17", 300, 5), record("osm:node:18", 600, 5, is_flock=False, manufacturer="axon")]
    roads = {"osm:node:17": [main_road(5.0)], "osm:node:18": [main_road(5.0)]}
    result = run(cams, roads, scope=CameraScope.FLOCK_ONLY)
    by_key = {e.source_key: e for e in result.encounters}
    assert by_key["osm:node:18"].status is EncounterStatus.EXCLUDED_SCOPE and result.matched_record_count == 1
    assert [(s.radius_m, s.records_within) for s in result.sensitivity] == [(25, 1), (50, 1), (100, 1)]


def test_no_longer_mapped_record_is_uncertain_never_matched():
    cam = record("osm:node:19", 500, 5, lifecycle_state="no_longer_mapped")
    result = run([cam], {"osm:node:19": [main_road(5.0)]})
    assert result.encounters[0].status is EncounterStatus.NO_LONGER_MAPPED and result.matched_record_count == 0 and result.uncertain_record_count == 1


def test_missing_snapshot_or_graph_is_not_assessed_never_zero():
    route = straight_route()
    index = MemoryProximityIndex([])
    result = assess_route(route, scope=CameraScope.ALL_ALPR, snapshot_id=None, graph_version="g", proximity=index, route_edges=edges_for(route), locate=lambda *_: [])
    assert result.status == "not_assessed" and result.matched_record_count is None and result.uncertain_record_count is None
    result = assess_route(route, scope=CameraScope.ALL_ALPR, snapshot_id="s", graph_version=None, proximity=index, route_edges=edges_for(route), locate=lambda *_: [])
    assert result.status == "not_assessed" and result.matched_record_count is None


def test_metric_helpers_use_meters_not_degrees():
    shape = [offset(0, 0), offset(1000, 0)]
    point = offset(500, 30)
    passes = passes_along_route(shape, point, 50)
    assert len(passes) == 1 and abs(passes[0][1] - 30) < 0.5 and abs(passes[0][0] - 500) < 1
    assert passes_along_route(shape, offset(500, 60), 50) == []
    # The same offsets in degrees would be wildly different numbers; the helper must answer in meters
    # (the fixture's 111,320 m per degree of latitude is a spherical mean, about 0.1 % off at Denver).
    assert abs(haversine_m(offset(0, 0), offset(0, 1000)) - 1000) < 3
