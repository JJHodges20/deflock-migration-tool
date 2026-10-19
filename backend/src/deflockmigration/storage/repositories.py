"""Repositories over the public camera inventory. All metric distance work happens in PostGIS geography."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session

from deflockmigration.domain.cameras import NormalizedCamera
from deflockmigration.storage.models import CameraRecord, CameraSnapshot, SnapshotDiff, SyncJob

RECORD_COLUMNS = (
    "snapshot_id, source_key, source_type, source_id, source_version, source_timestamp, "
    "ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lon, geometry_quality, raw_tags, is_alpr, alpr_evidence, "
    "manufacturer_raw, manufacturer_normalized, is_flock, operator, direction_raw, camera_direction_raw, "
    "direction_parsed_deg, direction_conflict, lifecycle_state, lifecycle_evidence, check_date, parse_warnings, "
    "in_envelope, missing_since, last_seen_snapshot_id"
)


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

    def list(self, region_id: str, states: list[str] | None = None, limit: int = 20) -> list[CameraSnapshot]:
        stmt = select(CameraSnapshot).where(CameraSnapshot.region_id == region_id)
        if states:
            stmt = stmt.where(CameraSnapshot.promotion_state.in_(states))
        stmt = stmt.order_by(CameraSnapshot.created_at.desc()).limit(limit)
        return list(self.s.execute(stmt).scalars().all())

    def pending_review(self, region_id: str) -> list[CameraSnapshot]:
        return self.list(region_id, states=["quarantined"], limit=50)

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

    def set_review(self, snapshot_id: str, note: str, now: dt.datetime) -> None:
        self.s.execute(update(CameraSnapshot).where(CameraSnapshot.snapshot_id == snapshot_id).values(review_note=note[:2000], reviewed_at=now))

    def add_diff(self, diff: SnapshotDiff) -> None:
        self.s.add(diff)

    def diff_for(self, snapshot_id: str) -> SnapshotDiff | None:
        return self.s.execute(select(SnapshotDiff).where(SnapshotDiff.snapshot_id == snapshot_id)).scalars().first()

    def prune(self, region_id: str, *, keep_superseded: int, keep_quarantined: int) -> list[tuple[str, str | None]]:
        """Delete old superseded and old quarantined/rejected snapshots (records cascade). Returns (id, raw_path) of deletions."""
        removed: list[tuple[str, str | None]] = []
        superseded = self.s.execute(
            select(CameraSnapshot)
            .where(CameraSnapshot.region_id == region_id, CameraSnapshot.promotion_state == "superseded")
            .order_by(CameraSnapshot.promoted_at.desc().nullslast(), CameraSnapshot.created_at.desc())
        ).scalars().all()
        reviewed = self.s.execute(
            select(CameraSnapshot)
            .where(CameraSnapshot.region_id == region_id, CameraSnapshot.promotion_state.in_(["quarantined", "rejected"]))
            .order_by(CameraSnapshot.created_at.desc())
        ).scalars().all()
        for snapshot in list(superseded[keep_superseded:]) + list(reviewed[keep_quarantined:]):
            removed.append((snapshot.snapshot_id, snapshot.raw_path))
            self.s.execute(delete(CameraSnapshot).where(CameraSnapshot.snapshot_id == snapshot.snapshot_id))
        return removed


class CameraRepository:
    def __init__(self, session: Session):
        self.s = session

    @staticmethod
    def _row_from_record(snapshot_id: str, r: NormalizedCamera, in_envelope: bool) -> dict:
        return {
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
            "in_envelope": in_envelope,
            "missing_since": None,
            "last_seen_snapshot_id": None,
        }

    def bulk_insert(self, snapshot_id: str, records: list[NormalizedCamera], *, in_envelope: dict[str, bool] | None = None) -> int:
        rows = [self._row_from_record(snapshot_id, r, (in_envelope or {}).get(r.source_key, True)) for r in records]
        return self.bulk_insert_rows(rows)

    def bulk_insert_rows(self, rows: list[dict]) -> int:
        if rows:
            self.s.execute(CameraRecord.__table__.insert(), rows)
        return len(rows)

    def rows_by_key(self, snapshot_id: str) -> dict[str, dict]:
        sql = text(f"SELECT {RECORD_COLUMNS} FROM camera_records WHERE snapshot_id = :sid")
        return {row["source_key"]: dict(row) for row in self.s.execute(sql, {"sid": snapshot_id}).mappings().all()}

    def source_keys(self, snapshot_id: str) -> dict[str, int | None]:
        stmt = select(CameraRecord.source_key, CameraRecord.source_version).where(CameraRecord.snapshot_id == snapshot_id)
        return {key: version for key, version in self.s.execute(stmt).all()}

    def count(self, snapshot_id: str, *, alpr_only: bool = False, flock_only: bool = False, present_only: bool = True) -> int:
        stmt = select(func.count()).select_from(CameraRecord).where(CameraRecord.snapshot_id == snapshot_id)
        if alpr_only:
            stmt = stmt.where(CameraRecord.is_alpr.is_(True))
        if flock_only:
            stmt = stmt.where(CameraRecord.is_flock.is_(True))
        if present_only:
            stmt = stmt.where(CameraRecord.lifecycle_state != "no_longer_mapped")
        return int(self.s.execute(stmt).scalar_one())

    def in_bbox(self, snapshot_id: str, west: float, south: float, east: float, north: float, *, flock_only: bool, limit: int = 5000) -> list[dict]:
        sql = text(
            f"""
            SELECT id, {RECORD_COLUMNS}
            FROM camera_records
            WHERE snapshot_id = :snapshot_id AND is_alpr = TRUE
              AND (:flock_only = FALSE OR is_flock = TRUE)
              AND ST_Intersects(geom::geometry, ST_MakeEnvelope(:west, :south, :east, :north, 4326))
            LIMIT :limit
            """
        )
        rows = self.s.execute(sql, {"snapshot_id": snapshot_id, "flock_only": flock_only, "west": west, "south": south, "east": east, "north": north, "limit": limit}).mappings().all()
        return [dict(row) for row in rows]

    def get_current(self, snapshot_id: str, source_key: str) -> dict | None:
        sql = text(f"SELECT id, {RECORD_COLUMNS} FROM camera_records WHERE snapshot_id = :sid AND source_key = :key")
        row = self.s.execute(sql, {"sid": snapshot_id, "key": source_key}).mappings().first()
        return dict(row) if row else None

    def history(self, source_key: str, limit: int = 50) -> list[dict]:
        """Versions of one source key across retained snapshots, newest snapshot first."""
        sql = text(
            """
            SELECT r.snapshot_id, s.promotion_state, s.timestamp_osm_base, s.created_at AS snapshot_created_at,
                   r.source_version, r.source_timestamp, ST_Y(r.geom::geometry) AS lat, ST_X(r.geom::geometry) AS lon,
                   r.is_alpr, r.manufacturer_normalized, r.is_flock, r.operator, r.direction_raw, r.lifecycle_state,
                   r.lifecycle_evidence, r.check_date, r.in_envelope, r.missing_since, r.last_seen_snapshot_id
            FROM camera_records r JOIN camera_snapshots s ON s.snapshot_id = r.snapshot_id
            WHERE r.source_key = :key
            ORDER BY s.created_at DESC
            LIMIT :limit
            """
        )
        return [dict(row) for row in self.s.execute(sql, {"key": source_key, "limit": limit}).mappings().all()]


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

    def recent(self, region_id: str, limit: int = 5) -> list[SyncJob]:
        stmt = select(SyncJob).where(SyncJob.region_id == region_id).order_by(SyncJob.started_at.desc()).limit(limit)
        return list(self.s.execute(stmt).scalars().all())
