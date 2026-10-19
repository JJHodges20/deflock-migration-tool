"""Stage A + Stage B encounter assessment for one route (roadmap section 9). Pure given its inputs.

Rules:
- Count each canonical record once; repeated passes are reported separately.
- A record is *associated* only when the road it most plausibly sits on (nearest drivable road within the
  radius) is a road the route traverses near the pass. Roads are compared by name set when named (one
  street is split into many OpenStreetMap ways) and by way id otherwise. Parallel roads, grade-separated
  crossings, and ambiguous placements stay visible as uncertainties; they are never silently zero and
  never silently counted.
- Direction tags are reported, never used to exclude a record (v1).
- A route that leaves the assessed envelope is only partially assessed.
- "No mapped encounters" is a statement about mapped records, never about physical cameras.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from deflockmigration.domain.assessment import (
    AMBIGUITY_MARGIN_M,
    COUNTING_METHOD_VERSION,
    UNCERTAIN_STATUSES,
    AssessmentResult,
    Association,
    CameraNearRoute,
    Encounter,
    EncounterStatus,
    RoadCandidate,
    RouteEdge,
    SensitivityCount,
    is_ambiguous,
    road_key,
)
from deflockmigration.domain.routes import CameraScope, EngineRoute
from deflockmigration.geospatial.metric import cumulative_lengths_m, haversine_m, heading_difference_deg, passes_along_route
from deflockmigration.geospatial.proximity import ProximityIndex

RoadLocate = Callable[[float, float, float], list[RoadCandidate]]  # (lat, lon, radius_m) -> candidates sorted by distance
SITE_GROUP_RADIUS_M = 10.0
LOCALITY_M = 150.0  # route edges within this distance along the route of the pass count as "where the route is"


def _source_url(source_key: str) -> str:
    _, kind, ident = source_key.split(":")
    return f"https://www.openstreetmap.org/{kind}/{ident}"


def _edge_spans(route: EngineRoute, route_edges: list[RouteEdge]) -> list[tuple[float, float, RouteEdge]]:
    cumulative = cumulative_lengths_m(route.shape)
    last = len(cumulative) - 1
    return [(cumulative[min(max(e.begin_shape_index, 0), last)], cumulative[min(max(e.end_shape_index, 0), last)], e) for e in route_edges]


def _edges_near(spans: list[tuple[float, float, RouteEdge]], position_m: float | None) -> list[RouteEdge]:
    if position_m is None:
        return [e for _, _, e in spans]
    near = [e for begin, end, e in spans if begin - LOCALITY_M <= position_m <= end + LOCALITY_M]
    return near or [e for _, _, e in spans]


def _edge_at(spans: list[tuple[float, float, RouteEdge]], position_m: float | None) -> RouteEdge | None:
    if position_m is None or not spans:
        return None
    for begin, end, e in spans:
        if begin <= position_m <= max(end, begin):
            return e
    return spans[-1][2]


def _site_groups(records: list[CameraNearRoute]) -> dict[str, str]:
    """Records within SITE_GROUP_RADIUS_M of each other share a site id (the smallest key); counted individually."""
    groups: dict[str, str] = {}
    ordered = sorted(records, key=lambda r: r.source_key)
    for record in ordered:
        if record.source_key in groups:
            continue
        members = [other for other in ordered if other.source_key not in groups and haversine_m((record.lat, record.lon), (other.lat, other.lon)) <= SITE_GROUP_RADIUS_M]
        site_id = min(m.source_key for m in members)
        for member in members:
            groups[member.source_key] = site_id
    return groups


def _heading_relation(record: CameraNearRoute, edge: RouteEdge | None) -> str | None:
    if record.direction_conflict:
        return "mapped direction tags conflict; orientation unknown (not used for counting)"
    if record.direction_parsed_deg is None:
        return None if record.direction_raw is None else f"mapped direction '{record.direction_raw}' not parsed (not used for counting)"
    if edge is None or edge.begin_heading is None:
        return f"mapped direction {record.direction_parsed_deg:.0f}° (travel heading unknown; not used for counting)"
    diff = heading_difference_deg(record.direction_parsed_deg, edge.begin_heading)
    return f"mapped direction {record.direction_parsed_deg:.0f}°, travel heading {edge.begin_heading:.0f}° (difference {diff:.0f}°; not used for counting)"


def _label(names: list[str], way_id: int | None) -> str:
    return " / ".join(names) if names else (f"unnamed way {way_id}" if way_id is not None else "an unnamed road")


def _associate(record: CameraNearRoute, candidates: list[RoadCandidate], near_edges: list[RouteEdge], *, radius_m: float, graph_version: str) -> tuple[EncounterStatus, Association]:
    near_keys = {road_key(e.names, e.way_id) for e in near_edges}
    near_way_ids = {e.way_id for e in near_edges}
    names_by_key = {road_key(e.names, e.way_id): e.names for e in near_edges}

    def traversed(c: RoadCandidate) -> bool:
        return c.way_id in near_way_ids or road_key(c.names, c.way_id) in near_keys

    base = dict(method="valhalla_locate_nearest_way", radius_m=radius_m, graph_version=graph_version, candidates_within_radius=len(candidates))
    fallback_edge = near_edges[0] if near_edges else None
    if not candidates:
        return EncounterStatus.NEARBY_UNRESOLVED, Association(
            **base, nearest_way_id=None, nearest_road_names=[], nearest_distance_m=None,
            route_way_id=fallback_edge.way_id if fallback_edge else None, route_road_names=fallback_edge.names if fallback_edge else [], route_way_distance_m=None,
            same_road=False, ambiguous=False, grade_separated=False,
            reason=f"no drivable road found within {radius_m:.0f} m of the record; association unresolved",
        )
    nearest = candidates[0]
    ambiguous = is_ambiguous(candidates)
    route_candidate = next((c for c in candidates if traversed(c)), None)
    route_way_id = route_candidate.way_id if route_candidate else (fallback_edge.way_id if fallback_edge else None)
    route_names = (names_by_key.get(road_key(route_candidate.names, route_candidate.way_id)) or route_candidate.names) if route_candidate else (fallback_edge.names if fallback_edge else [])
    grade_separated = bool(route_candidate and route_candidate is not nearest and (route_candidate.bridge != nearest.bridge or route_candidate.tunnel != nearest.tunnel))
    nearest_label = _label(nearest.names, nearest.way_id)
    route_label = _label(route_names, route_way_id)

    if traversed(nearest) and not ambiguous:
        status, same, reason = EncounterStatus.ASSOCIATED, True, f"nearest drivable road is {nearest_label} ({nearest.distance_m:.0f} m), which the route traverses here"
    elif traversed(nearest) and ambiguous:
        others = sorted({_label(c.names, c.way_id) for c in candidates if c.distance_m <= nearest.distance_m + AMBIGUITY_MARGIN_M and road_key(c.names, c.way_id) != road_key(nearest.names, nearest.way_id)})
        status, same, reason = EncounterStatus.NEARBY_UNRESOLVED, True, f"the route traverses {nearest_label} ({nearest.distance_m:.0f} m) but {', '.join(others)} is about as close; road association ambiguous"
    elif route_candidate is not None:
        kind = "a grade-separated crossing (bridge or tunnel)" if grade_separated else "a different road nearby (possibly a parallel or frontage road)"
        status, same, reason = EncounterStatus.NEARBY_UNRESOLVED, False, f"nearest drivable road is {nearest_label} ({nearest.distance_m:.0f} m); the route uses {route_label} ({route_candidate.distance_m:.0f} m), {kind}"
    else:
        status, same, reason = EncounterStatus.NEARBY_UNRESOLVED, False, f"nearest drivable road is {nearest_label} ({nearest.distance_m:.0f} m), which the route does not traverse here; the route passes within {record.distance_m:.0f} m on {route_label}"
    return status, Association(
        **base,
        nearest_way_id=nearest.way_id,
        nearest_road_names=nearest.names,
        nearest_distance_m=nearest.distance_m,
        route_way_id=route_way_id,
        route_road_names=route_names,
        route_way_distance_m=route_candidate.distance_m if route_candidate else None,
        same_road=same,
        ambiguous=ambiguous,
        grade_separated=grade_separated,
        reason=reason,
    )


def assess_route(
    route: EngineRoute,
    *,
    scope: CameraScope,
    snapshot_id: str | None,
    graph_version: str | None,
    proximity: ProximityIndex,
    route_edges: list[RouteEdge],
    locate: RoadLocate,
    radius_m: float = 50.0,
    sensitivity_radii_m: list[int] | None = None,
) -> AssessmentResult:
    radii = sorted(sensitivity_radii_m or [25, 50, 100])
    max_radius = max(radii + [int(radius_m)])
    if snapshot_id is None:
        return AssessmentResult("not_assessed", COUNTING_METHOD_VERSION, radius_m, scope.value, None, graph_version, None, None, None, warnings=["No validated camera snapshot is available; the route was not assessed."])
    if graph_version is None:
        return AssessmentResult("not_assessed", COUNTING_METHOD_VERSION, radius_m, scope.value, snapshot_id, None, None, None, None, warnings=["The routing graph version is unknown; road association was not attempted."])

    coverage = proximity.envelope_coverage(route.shape)
    records = proximity.records_near(snapshot_id, route.shape, max_radius)
    groups = _site_groups(records)
    spans = _edge_spans(route, route_edges)
    encounters: list[Encounter] = []
    sensitivity = {r: 0 for r in radii}
    warnings: list[str] = []

    for record in records:
        in_scope = scope is CameraScope.ALL_ALPR or record.is_flock
        passes = passes_along_route(route.shape, (record.lat, record.lon), max_radius)
        if passes:
            position_m, _, _ = min(passes, key=lambda p: p[0])
            position_fraction = position_m / route.length_m if route.length_m > 0 else 0.0
        else:
            position_m, position_fraction = None, None
        edge_at_pass = _edge_at(spans, position_m)
        common = dict(
            source_key=record.source_key, lat=record.lat, lon=record.lon, distance_m=round(record.distance_m, 1),
            position_fraction=round(position_fraction, 4) if position_fraction is not None else None,
            position_m=round(position_m, 1) if position_m is not None else None, pass_count=max(1, len(passes)),
            site_group_id=groups[record.source_key], manufacturer=record.manufacturer, is_flock=record.is_flock,
            lifecycle_state=record.lifecycle_state, direction_raw=record.direction_raw, direction_conflict=record.direction_conflict,
            heading_relation=_heading_relation(record, edge_at_pass), in_envelope=record.in_envelope, source_url=_source_url(record.source_key),
            source_timestamp=record.source_timestamp.isoformat().replace("+00:00", "Z") if record.source_timestamp else None, check_date=record.check_date,
        )
        if in_scope and record.lifecycle_state != "no_longer_mapped":
            for r in radii:
                if record.distance_m <= r:
                    sensitivity[r] += 1
        if not in_scope:
            encounters.append(Encounter(**common, status=EncounterStatus.EXCLUDED_SCOPE, association=None, reason="outside the selected camera scope; not counted"))
            continue
        if record.lifecycle_state == "no_longer_mapped":
            encounters.append(Encounter(**common, status=EncounterStatus.NO_LONGER_MAPPED, association=None, reason="no longer present in the latest source query; retained as uncertain, not counted as matched"))
            continue
        if not record.in_envelope:
            encounters.append(Encounter(**common, status=EncounterStatus.OUTSIDE_ENVELOPE, association=None, reason="outside the assessed data area; counted as uncertain"))
            continue
        if record.distance_m > radius_m:
            encounters.append(Encounter(**common, status=EncounterStatus.BEYOND_RADIUS, association=None, reason=f"within {max_radius} m but beyond the {radius_m:.0f} m counting radius; shown for sensitivity only"))
            continue
        candidates = locate(record.lat, record.lon, radius_m)
        status, association = _associate(record, candidates, _edges_near(spans, position_m), radius_m=radius_m, graph_version=graph_version)
        reason = association.reason
        if position_fraction is not None and (position_fraction < 0.01 or position_fraction > 0.99):
            reason += "; at the very start or end of the trip"
        encounters.append(Encounter(**common, status=status, association=association, reason=reason))

    matched = {e.source_key for e in encounters if e.status is EncounterStatus.ASSOCIATED}
    uncertain = {e.source_key for e in encounters if e.status in UNCERTAIN_STATUSES}
    status = "complete" if coverage >= 0.999 else "partial"
    if status == "partial":
        warnings.append(f"Route leaves the assessed data area ({coverage:.0%} of its length is inside); camera counts are not complete.")
    if any(e.pass_count > 1 for e in encounters):
        warnings.append("The route passes some records more than once; each record is counted once.")
    encounters.sort(key=lambda e: (e.position_m if e.position_m is not None else float("inf"), e.source_key))
    return AssessmentResult(
        status=status,
        counting_method_version=COUNTING_METHOD_VERSION,
        radius_m=radius_m,
        scope=scope.value,
        snapshot_id=snapshot_id,
        graph_version=graph_version,
        matched_record_count=len(matched),
        uncertain_record_count=len(uncertain),
        coverage_fraction=round(coverage, 4),
        encounters=encounters,
        sensitivity=[SensitivityCount(r, sensitivity[r]) for r in radii],
        warnings=warnings,
    )


def with_scope(result: AssessmentResult, **changes) -> AssessmentResult:
    return replace(result, **changes)
