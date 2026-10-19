"""Candidate handling that is independent of the engine.

Decision 0001 D6: the Standard route is the fastest baseline candidate by reported time, because
the engine's primary result minimises an internal cost that its reported time does not include.
"""

from __future__ import annotations

import math

from deflockmigration.domain.routes import EngineRoute, LatLon

LENGTH_MISMATCH_TOLERANCE = 0.03  # 3 % between the sum of maneuver lengths and the route length


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371008.8
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def dedupe(candidates: list[EngineRoute]) -> list[EngineRoute]:
    seen: set[str] = set()
    unique: list[EngineRoute] = []
    for candidate in candidates:
        key = candidate.encoded_shape_key()
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def choose_standard(candidates: list[EngineRoute]) -> EngineRoute:
    if not candidates:
        raise ValueError("no candidates")
    return min(candidates, key=lambda r: (r.duration_s, r.length_m, 0 if r.source == "primary" else 1))


def validate_maneuvers(route: EngineRoute) -> list[str]:
    """Return problems that would make directions untrustworthy; empty means valid."""
    problems: list[str] = []
    if not route.maneuvers:
        problems.append("no maneuvers")
        return problems
    last = -1
    shape_len = len(route.shape)
    for index, maneuver in enumerate(route.maneuvers):
        if not maneuver.instruction.strip():
            problems.append(f"maneuver {index} has no instruction")
        if maneuver.begin_shape_index < last:
            problems.append(f"maneuver {index} shape index decreases")
        if maneuver.begin_shape_index < 0 or maneuver.end_shape_index >= shape_len or maneuver.end_shape_index < maneuver.begin_shape_index:
            problems.append(f"maneuver {index} shape indices out of range")
        last = maneuver.begin_shape_index
    if route.maneuvers[0].type not in (1, 2, 3):
        problems.append("first maneuver is not a start")
    if route.maneuvers[-1].type not in (4, 5, 6):
        problems.append("last maneuver is not a destination")
    if shape_len < 2:
        problems.append("shape has fewer than two points")
    if route.maneuvers[0].begin_shape_index != 0 or route.maneuvers[-1].end_shape_index != shape_len - 1:
        problems.append("maneuvers do not span the whole shape")
    return problems


def alignment_warnings(route: EngineRoute) -> list[str]:
    """Non-fatal checks that instructions and geometry describe the same path."""
    warnings: list[str] = []
    total_maneuvers = sum(m.length_m for m in route.maneuvers)
    if route.length_m > 0:
        mismatch = abs(total_maneuvers - route.length_m) / route.length_m
        if mismatch > LENGTH_MISMATCH_TOLERANCE:
            warnings.append(f"Maneuver lengths differ from the route length by {mismatch:.0%}.")
    return warnings


def snap_distances_m(route: EngineRoute, origin: LatLon, destination: LatLon) -> tuple[float, float]:
    """How far the engine's start and end points are from the requested points (endpoint snapping)."""
    if len(route.shape) < 2:
        return 0.0, 0.0
    start = haversine_m((origin.lat, origin.lon), route.shape[0])
    end = haversine_m((destination.lat, destination.lon), route.shape[-1])
    return round(start, 1), round(end, 1)
