"""Small metric helpers for route geometry (meters, never degrees).

The in-memory implementation projects each segment into a local tangent plane with the cosine of the
latitude; errors are far below a metre at Denver's scale. Production proximity queries use PostGIS
geography; these helpers refine positions along a route for the few records that query returns.
"""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6371008.8
METERS_PER_DEGREE = 111320.0


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def point_segment_m(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    """Distance (m) from p to segment ab and the fraction along ab of the closest point."""
    k = math.cos(math.radians(p[0]))
    ax, ay = (a[1] - p[1]) * k, a[0] - p[0]
    bx, by = (b[1] - p[1]) * k, b[0] - p[0]
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        t = 0.0
    else:
        t = max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return math.sqrt(cx * cx + cy * cy) * METERS_PER_DEGREE, t


def cumulative_lengths_m(shape: list[tuple[float, float]]) -> list[float]:
    out = [0.0]
    for i in range(1, len(shape)):
        out.append(out[-1] + haversine_m(shape[i - 1], shape[i]))
    return out


def passes_along_route(shape: list[tuple[float, float]], point: tuple[float, float], radius_m: float, *, gap_m: float = 150.0) -> list[tuple[float, float, int]]:
    """Each distinct pass of the route within `radius_m` of `point`: (position_m, min_distance_m, segment_index).

    Consecutive near segments form one pass; a gap longer than `gap_m` along the route starts a new pass
    (a loop that returns past the same camera counts as a second pass).
    """
    if len(shape) < 2:
        return []
    cumulative = cumulative_lengths_m(shape)
    passes: list[tuple[float, float, int]] = []
    current: tuple[float, float, int] | None = None
    last_near_pos = None
    for i in range(len(shape) - 1):
        dist, t = point_segment_m(point, shape[i], shape[i + 1])
        if dist <= radius_m:
            pos = cumulative[i] + t * (cumulative[i + 1] - cumulative[i])
            if current is None or (last_near_pos is not None and pos - last_near_pos > gap_m):
                if current is not None:
                    passes.append(current)
                current = (pos, dist, i)
            elif dist < current[1]:
                current = (pos, dist, i)
            last_near_pos = pos
    if current is not None:
        passes.append(current)
    return passes


def min_distance_to_route_m(shape: list[tuple[float, float]], point: tuple[float, float]) -> float:
    return min(point_segment_m(point, shape[i], shape[i + 1])[0] for i in range(len(shape) - 1)) if len(shape) >= 2 else float("inf")


def heading_difference_deg(a: float, b: float) -> float:
    diff = abs((a - b) % 360.0)
    return min(diff, 360.0 - diff)
