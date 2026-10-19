"""Stage A production implementation: PostGIS geography (meters) over the active snapshot's records."""

from __future__ import annotations

import json

from sqlalchemy import text

from deflockmigration.domain.assessment import CameraNearRoute
from deflockmigration.geospatial.proximity import route_wkt
from deflockmigration.storage.db import SessionFactory


class PostgisProximityIndex:
    def __init__(self, session_factory: SessionFactory, envelope_geojson: dict):
        self._sf = session_factory
        self._envelope = json.dumps(envelope_geojson)

    def records_near(self, snapshot_id: str, shape: list[tuple[float, float]], max_radius_m: float) -> list[CameraNearRoute]:
        if len(shape) < 2:
            return []
        sql = text(
            """
            WITH route AS (SELECT ST_GeogFromText(:wkt) AS g)
            SELECT r.source_key, ST_Y(r.geom::geometry) AS lat, ST_X(r.geom::geometry) AS lon, r.is_alpr, r.is_flock,
                   r.manufacturer_normalized, r.lifecycle_state, r.direction_raw, r.direction_parsed_deg, r.direction_conflict,
                   r.in_envelope, r.operator, r.source_timestamp, r.check_date,
                   ST_Distance(r.geom, route.g) AS distance_m
            FROM camera_records r, route
            WHERE r.snapshot_id = :snapshot_id AND r.is_alpr = TRUE AND ST_DWithin(r.geom, route.g, :radius)
            ORDER BY distance_m
            """
        )
        with self._sf() as session:
            rows = session.execute(sql, {"wkt": route_wkt(shape), "snapshot_id": snapshot_id, "radius": max_radius_m}).mappings().all()
        return [
            CameraNearRoute(
                source_key=row["source_key"], lat=row["lat"], lon=row["lon"], is_alpr=row["is_alpr"], is_flock=row["is_flock"],
                manufacturer=row["manufacturer_normalized"], lifecycle_state=row["lifecycle_state"], direction_raw=row["direction_raw"],
                direction_parsed_deg=row["direction_parsed_deg"], direction_conflict=row["direction_conflict"], in_envelope=row["in_envelope"],
                operator=row["operator"], source_timestamp=row["source_timestamp"], check_date=row["check_date"], distance_m=float(row["distance_m"]),
            )
            for row in rows
        ]

    def envelope_coverage(self, shape: list[tuple[float, float]]) -> float:
        if len(shape) < 2:
            return 0.0
        sql = text(
            """
            SELECT ST_Length(ST_Intersection(ST_GeomFromText(:wkt, 4326), ST_SetSRID(ST_GeomFromGeoJSON(:env), 4326))::geography)
                   / NULLIF(ST_Length(ST_GeomFromText(:wkt, 4326)::geography), 0) AS fraction
            """
        )
        with self._sf() as session:
            value = session.execute(sql, {"wkt": route_wkt(shape), "env": self._envelope}).scalar()
        return float(value) if value is not None else 0.0
