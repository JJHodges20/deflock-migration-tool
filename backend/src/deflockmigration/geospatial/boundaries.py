"""Service boundary and camera-data envelope geometry (EPSG:4326, point-in-polygon only).

Metric operations (buffers, distances) belong in PostGIS geography queries or a projected CRS;
this module never measures meters in degrees.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.prepared import PreparedGeometry, prep


@dataclass(frozen=True)
class Boundary:
    boundary_id: str
    geometry: BaseGeometry
    properties: dict
    _prepared: PreparedGeometry

    @property
    def bbox_wsen(self) -> tuple[float, float, float, float]:
        west, south, east, north = self.geometry.bounds
        return (west, south, east, north)

    def contains(self, lat: float, lon: float) -> bool:
        return bool(self._prepared.contains(Point(lon, lat)))

    def geojson_geometry(self) -> dict:
        return json.loads(json.dumps(self.geometry.__geo_interface__))


def load_boundary(path: Path, *, expected_id: str | None = None) -> Boundary:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("type") != "FeatureCollection" or not data.get("features"):
        raise ValueError(f"{path} is not a FeatureCollection with features")
    feature = data["features"][0]
    props = feature.get("properties") or {}
    boundary_id = props.get("boundary_id") or props.get("envelope_id")
    if expected_id and boundary_id != expected_id:
        raise ValueError(f"{path} carries id {boundary_id!r}, expected {expected_id!r}")
    geometry = shape(feature["geometry"])
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    if geometry.is_empty:
        raise ValueError(f"{path} has an empty geometry")
    return Boundary(boundary_id=boundary_id or path.stem, geometry=geometry, properties=props, _prepared=prep(geometry))
