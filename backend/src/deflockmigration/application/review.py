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
from deflockmigration.storage.repositories import CameraRepository, SnapshotRepository


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


def rollback_snapshot(session_factory: SessionFactory, region_id: str, snapshot_id: str | None, note: str, *, clock: Clock = utc_now) -> str:
    """Make a previously active (superseded, still retained) snapshot active again. No deletion: the replaced snapshot
    becomes superseded and stays retained, so the rollback itself can be undone the same way."""
    if not note.strip():
        raise ReviewError("a note explaining the rollback is required")
    now = clock()
    with session_factory() as session:
        repo = SnapshotRepository(session)
        active = repo.get_active(region_id)
        if active is None:
            raise ReviewError("no active snapshot to roll back from")
        target_id = snapshot_id or active.previous_active_snapshot_id
        if not target_id:
            raise ReviewError("the active snapshot has no recorded previous active snapshot; give a snapshot id")
        target = repo.get(target_id)
        if target is None or target.region_id != region_id:
            raise ReviewError(f"snapshot {target_id} not found for region {region_id} (it may have been pruned)")
        if target.snapshot_id == active.snapshot_id:
            raise ReviewError(f"snapshot {target_id} is already active")
        if target.promotion_state != "superseded":
            raise ReviewError(f"snapshot {target_id} is {target.promotion_state}; only a previously active (superseded) snapshot can be rolled back to")
        if CameraRepository(session).count(target_id, present_only=False) == 0:
            raise ReviewError(f"snapshot {target_id} has no retained records")
        repo.promote(target_id, region_id, now)
        repo.set_review(target_id, f"rolled back to: {note}", now)
        session.add(SyncJob(region_id=region_id, trigger="rollback", started_at=now, finished_at=now, status="succeeded", snapshot_id=target_id, attempts=0,
                            message=f"rolled back from {active.snapshot_id} to {target_id} by operator: {note[:150]}"))
        session.commit()
    return f"snapshot {target_id} is active again (replaced {active.snapshot_id}, which stays retained as superseded)"
