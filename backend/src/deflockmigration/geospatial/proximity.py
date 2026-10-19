"""Stage A interface: which camera records lie within a radius of a route, in meters.

The production implementation (PostGIS geography) lives in `storage.proximity_postgis`; the in-memory
index here serves tests and fixtures. Both return the same shape so the assessment logic is identical.
"""

from __future__ import annotations

from typing import Protocol

from shapely.geometry import LineString, shape as shapely_shape
from shapely.geometry.base import BaseGeometry

from deflockmigration.domain.assessment import CameraNearRoute
from deflockmigration.geospatial.metric import min_distance_to_route_m


class ProximityIndex(Protocol):
    def records_near(self, snapshot_id: str, shape: list[tuple[float, float]], max_radius_m: float) -> list[CameraNearRoute]: ...

    def envelope_coverage(self, shape: list[tuple[float, float]]) -> float:
        """Fraction (0..1) of the route length inside the camera-data envelope."""


def route_wkt(shape: list[tuple[float, float]]) -> str:
    return "LINESTRING(" + ", ".join(f"{lon:.7f} {lat:.7f}" for lat, lon in shape) + ")"


class MemoryProximityIndex:
    """Pure-Python index over explicit records; for tests and fixtures."""

    def __init__(self, records: list[CameraNearRoute], envelope: BaseGeometry | dict | None = None):
        self._records = records
        self._envelope = shapely_shape(envelope) if isinstance(envelope, dict) else envelope

    def records_near(self, snapshot_id: str, shape: list[tuple[float, float]], max_radius_m: float) -> list[CameraNearRoute]:
        out = []
        for record in self._records:
            if not record.is_alpr:
                continue
            distance = min_distance_to_route_m(shape, (record.lat, record.lon))
            if distance <= max_radius_m:
                out.append(CameraNearRoute(**{**record.__dict__, "distance_m": round(distance, 1)}))
        return sorted(out, key=lambda r: r.distance_m)

    def envelope_coverage(self, shape: list[tuple[float, float]]) -> float:
        if self._envelope is None or len(shape) < 2:
            return 1.0
        line = LineString([(lon, lat) for lat, lon in shape])
        if line.length == 0:
            return 0.0
        # A length ratio in degrees is acceptable here only because numerator and denominator share one tiny extent; production uses geography.
        return line.intersection(self._envelope).length / line.length
