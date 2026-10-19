"""Operator review of quarantined snapshots (roadmap section 8, step 7).

A quarantined snapshot is never published automatically. An operator who has corroborated the
change (for example a real mass retirement in OpenStreetMap) can accept it; otherwise it is rejected
and the last good snapshot stays active either way.
"""

from __future__ import annotations

from dataclasses import dataclass

from deflockmigration.core.clock import Clock, isoformat_z, utc_now
from deflockmigration.storage.db import SessionFactory
from deflockmigration.storage.models import SyncJob
from deflockmigration.storage.repositories import SnapshotRepository


@dataclass(frozen=True)
class ReviewItem:
    snapshot_id: str
    created_at: str
    promotion_state: str
    element_count: int
    alpr_count: int
    quarantine_reason: str | None
    review_note: str | None


class ReviewError(ValueError):
    pass


def list_snapshots(session_factory: SessionFactory, region_id: str, states: list[str] | None = None, limit: int = 20) -> list[ReviewItem]:
    with session_factory() as session:
        rows = SnapshotRepository(session).list(region_id, states=states, limit=limit)
        return [
            ReviewItem(
                snapshot_id=s.snapshot_id,
                created_at=isoformat_z(s.created_at),
                promotion_state=s.promotion_state,
                element_count=s.element_count,
                alpr_count=s.alpr_count,
                quarantine_reason=(s.quality or {}).get("quarantine_reason"),
                review_note=s.review_note,
            )
            for s in rows
        ]


def accept_snapshot(session_factory: SessionFactory, region_id: str, snapshot_id: str, note: str, *, clock: Clock = utc_now) -> str:
    if not note.strip():
        raise ReviewError("a review note explaining the corroboration is required")
    now = clock()
    with session_factory() as session:
        repo = SnapshotRepository(session)
        snapshot = repo.get(snapshot_id)
        if snapshot is None or snapshot.region_id != region_id:
            raise ReviewError(f"snapshot {snapshot_id} not found for region {region_id}")
        if snapshot.promotion_state != "quarantined":
            raise ReviewError(f"snapshot {snapshot_id} is {snapshot.promotion_state}, not quarantined")
        previous = repo.promote(snapshot_id, region_id, now)
        repo.set_review(snapshot_id, f"accepted: {note}", now)
        session.add(SyncJob(region_id=region_id, trigger="review", started_at=now, finished_at=now, status="succeeded", snapshot_id=snapshot_id, attempts=0, message=f"quarantined snapshot accepted by operator: {note[:200]}"))
        session.commit()
    return f"snapshot {snapshot_id} promoted (previous active: {previous})"


def reject_snapshot(session_factory: SessionFactory, region_id: str, snapshot_id: str, note: str, *, clock: Clock = utc_now) -> str:
    if not note.strip():
        raise ReviewError("a review note is required")
    now = clock()
    with session_factory() as session:
        repo = SnapshotRepository(session)
        snapshot = repo.get(snapshot_id)
        if snapshot is None or snapshot.region_id != region_id:
            raise ReviewError(f"snapshot {snapshot_id} not found for region {region_id}")
        if snapshot.promotion_state != "quarantined":
            raise ReviewError(f"snapshot {snapshot_id} is {snapshot.promotion_state}, not quarantined")
        repo.mark(snapshot_id, "rejected")
        repo.set_review(snapshot_id, f"rejected: {note}", now)
        session.add(SyncJob(region_id=region_id, trigger="review", started_at=now, finished_at=now, status="succeeded", snapshot_id=snapshot_id, attempts=0, message=f"quarantined snapshot rejected by operator: {note[:200]}"))
        session.commit()
    return f"snapshot {snapshot_id} rejected; the active snapshot is unchanged"
