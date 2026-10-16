"""Repositories over the public camera inventory. All metric distance work happens in PostGIS geography."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from deflockmigration.domain.cameras import NormalizedCamera
from deflockmigration.storage.models import CameraRecord, CameraSnapshot, SyncJob


class SnapshotRepository:
    def __init__(self, session: Session):
        self.s = session

    def get_active(self, region_id: str) -> CameraSnapshot | None:
        stmt = select(CameraSnapshot).where(CameraSnapshot.region_id == region_id, CameraSnapshot.promotion_state == "active")
        return self.s.execute(stmt).scalars().first()

    def get(self, snapshot_id: str) -> CameraSnapshot | None:
        return self.s.get(CameraSnapshot, snapshot_id)

    def add(self, snapshot: CameraSnapshot) -> None:
        self.s.add(snapshot)

    def promote(self, snapshot_id: str, region_id: str, now: dt.datetime) -> str | None:
        """Atomically make `snapshot_id` the only active snapshot of the region. Returns the previous active id."""
        previous = self.get_active(region_id)
        previous_id = previous.snapshot_id if previous else None
        if previous is not None and previous.snapshot_id != snapshot_id:
            self.s.execute(update(CameraSnapshot).where(CameraSnapshot.snapshot_id == previous.snapshot_id).values(promotion_state="superseded"))
        self.s.execute(
            update(CameraSnapshot)
            .where(CameraSnapshot.snapshot_id == snapshot_id)
            .values(promotion_state="active", promoted_at=now, previous_active_snapshot_id=previous_id if previous_id != snapshot_id else None)
        )
        return previous_id

    def mark(self, snapshot_id: str, state: str) -> None:
        self.s.execute(update(CameraSnapshot).where(CameraSnapshot.snapshot_id == snapshot_id).values(promotion_state=state))


class CameraRepository:
    def __init__(self, session: Session):
        self.s = session

    def bulk_insert(self, snapshot_id: str, records: list[NormalizedCamera]) -> int:
        rows = []
        for r in records:
            rows.append({
                "snapshot_id": snapshot_id,
                "source_key": r.source_key,
                "source_type": r.source_type,
                "source_id": r.source_id,
                "source_version": r.source_version,
                "source_timestamp": r.source_timestamp,
                "geom": f"SRID=4326;POINT({r.lon} {r.lat})",
                "geometry_quality": r.geometry_quality,
                "raw_tags": r.raw_tags,
                "is_alpr": r.is_alpr,
                "alpr_evidence": r.alpr_evidence,
                "manufacturer_raw": r.manufacturer_raw,
                "manufacturer_normalized": r.manufacturer_normalized,
                "is_flock": r.is_flock,
                "operator": r.operator,
                "direction_raw": r.direction_raw,
                "camera_direction_raw": r.camera_direction_raw,
                "direction_parsed_deg": r.direction_parsed_deg,
                "direction_conflict": r.direction_conflict,
                "lifecycle_state": str(r.lifecycle_state),
                "lifecycle_evidence": r.lifecycle_evidence,
                "check_date": r.check_date,
                "parse_warnings": r.parse_warnings,
            })
        if rows:
            self.s.execute(CameraRecord.__table__.insert(), rows)
        return len(rows)

    def source_keys(self, snapshot_id: str) -> dict[str, int | None]:
        stmt = select(CameraRecord.source_key, CameraRecord.source_version).where(CameraRecord.snapshot_id == snapshot_id)
        return {key: version for key, version in self.s.execute(stmt).all()}

    def count(self, snapshot_id: str, *, alpr_only: bool = False, flock_only: bool = False) -> int:
        stmt = select(func.count()).select_from(CameraRecord).where(CameraRecord.snapshot_id == snapshot_id)
        if alpr_only:
            stmt = stmt.where(CameraRecord.is_alpr.is_(True))
        if flock_only:
            stmt = stmt.where(CameraRecord.is_flock.is_(True))
        return int(self.s.execute(stmt).scalar_one())

    def in_bbox(self, snapshot_id: str, west: float, south: float, east: float, north: float, *, flock_only: bool, limit: int = 5000) -> list[dict]:
        sql = text(
            """
            SELECT id, source_key, source_version, source_timestamp, ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lon,
                   is_alpr, manufacturer_normalized, is_flock, operator, direction_raw, camera_direction_raw,
                   direction_conflict, lifecycle_state, check_date, geometry_quality
            FROM camera_records
            WHERE snapshot_id = :snapshot_id AND is_alpr = TRUE
              AND (:flock_only = FALSE OR is_flock = TRUE)
              AND ST_Intersects(geom::geometry, ST_MakeEnvelope(:west, :south, :east, :north, 4326))
            LIMIT :limit
            """
        )
        rows = self.s.execute(sql, {"snapshot_id": snapshot_id, "flock_only": flock_only, "west": west, "south": south, "east": east, "north": north, "limit": limit}).mappings().all()
        return [dict(row) for row in rows]


class SyncJobRepository:
    def __init__(self, session: Session):
        self.s = session

    def start(self, region_id: str, trigger: str, now: dt.datetime) -> SyncJob:
        job = SyncJob(region_id=region_id, trigger=trigger, started_at=now, status="running", attempts=0)
        self.s.add(job)
        self.s.flush()
        return job

    def latest(self, region_id: str) -> SyncJob | None:
        stmt = select(SyncJob).where(SyncJob.region_id == region_id).order_by(SyncJob.started_at.desc()).limit(1)
        return self.s.execute(stmt).scalars().first()

    def latest_failure(self, region_id: str) -> SyncJob | None:
        stmt = (
            select(SyncJob)
            .where(SyncJob.region_id == region_id, SyncJob.status.in_(["failed", "quarantined"]))
            .order_by(SyncJob.started_at.desc())
            .limit(1)
        )
        return self.s.execute(stmt).scalars().first()
