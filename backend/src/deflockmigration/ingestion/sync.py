"""Camera inventory refresh (roadmap section 8, M1 scope: fetch, validate, stage, promote, diff).

Fixed region, never a trip. Failures keep the last known good snapshot. Suspicious drops are
quarantined instead of published. M2 extends quarantine review, lifecycle handling, and the
map overlay; the data contract here is already the final one.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

from deflockmigration.core.clock import Clock, isoformat_z, utc_now
from deflockmigration.core.config_loader import AppConfig
from deflockmigration.data_sources.overpass import OverpassClient
from deflockmigration.ingestion.normalize import normalize_elements
from deflockmigration.storage.db import SessionFactory
from deflockmigration.storage.models import CameraSnapshot
from deflockmigration.storage.repositories import CameraRepository, SnapshotRepository, SyncJobRepository

log = logging.getLogger(__name__)
PARSER_VERSION = "normalize-1.0"


@dataclass(frozen=True)
class SyncOutcome:
    status: str  # succeeded | failed | quarantined | skipped
    snapshot_id: str | None
    message: str
    added: int | None = None
    changed: int | None = None
    no_longer_present: int | None = None


def _lock_key(region_id: str) -> int:
    return int(hashlib.sha256(f"camera-sync:{region_id}".encode()).hexdigest()[:15], 16)


def run_sync(
    config: AppConfig,
    session_factory: SessionFactory,
    client: OverpassClient,
    *,
    snapshot_dir: Path,
    trigger: str = "scheduled",
    clock: Clock = utc_now,
) -> SyncOutcome:
    region = config.region
    region_id = region.region_id
    quality = config.data_quality.snapshot_validation
    now = clock()

    with session_factory() as session:
        locked = session.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": _lock_key(region_id)}).scalar()
        if not locked:
            return SyncOutcome("skipped", None, "another sync holds the region lock")
        try:
            jobs = SyncJobRepository(session)
            job = jobs.start(region_id, trigger, now)
            session.commit()

            result = client.fetch(config.camera_query_text)
            job.attempts = result.attempts
            job.http_status = result.http_status
            if not result.ok or result.payload is None:
                job.status, job.finished_at, job.message = "failed", clock(), f"fetch failed: {result.error}"
                session.commit()
                log.warning("camera sync failed; last known good snapshot retained (%s)", result.error)
                return SyncOutcome("failed", None, job.message)

            payload = result.payload
            elements = payload.get("elements") or []
            base_ts = (payload.get("osm3s") or {}).get("timestamp_osm_base")
            base_dt = dt.datetime.fromisoformat(base_ts.replace("Z", "+00:00")) if base_ts else None
            snapshot_id = f"ovp-{region_id}-{(base_dt or now).strftime('%Y%m%dT%H%M%SZ')}-{result.sha256[:8]}"

            snapshots = SnapshotRepository(session)
            if snapshots.get(snapshot_id) is not None:
                job.status, job.finished_at, job.snapshot_id, job.message = "succeeded", clock(), snapshot_id, "identical snapshot already stored"
                session.commit()
                return SyncOutcome("succeeded", snapshot_id, job.message, 0, 0, 0)

            snapshot_dir.mkdir(parents=True, exist_ok=True)
            raw_path = snapshot_dir / f"{snapshot_id}.json"
            raw_path.write_bytes(result.body or b"")

            records = normalize_elements(elements)
            alpr = sum(1 for r in records if r.is_alpr)
            flock = sum(1 for r in records if r.is_alpr and r.is_flock)
            unknown = sum(1 for r in records if r.is_alpr and r.manufacturer_normalized is None)

            previous = snapshots.get_active(region_id)
            quality_report: dict = {"element_count": len(elements), "record_count": len(records), "alpr_count": alpr}
            quarantine_reason = None
            if len(elements) < quality.min_element_count:
                quarantine_reason = f"element count {len(elements)} below minimum {quality.min_element_count}"
            elif previous is not None and previous.alpr_count > 0:
                drop = 1.0 - (alpr / previous.alpr_count)
                quality_report["alpr_drop_fraction_vs_previous"] = round(drop, 4)
                if drop > quality.max_count_drop_fraction:
                    quarantine_reason = f"ALPR count dropped by {drop:.0%} versus the active snapshot"

            snapshot = CameraSnapshot(
                snapshot_id=snapshot_id,
                region_id=region_id,
                source="OpenStreetMap via Overpass API",
                endpoint=client._endpoint,  # noqa: SLF001 - recorded for provenance
                query_sha256=hashlib.sha256(config.camera_query_text.encode("utf-8")).hexdigest(),
                query_bbox=",".join(str(v) for v in region.camera_source.query_bbox_swne),
                generator=payload.get("generator"),
                timestamp_osm_base=base_dt,
                downloaded_at_start=result.started_at,
                downloaded_at_end=result.finished_at,
                element_count=len(elements),
                record_count=len(records),
                alpr_count=alpr,
                flock_count=flock,
                unknown_manufacturer_count=unknown,
                raw_sha256=result.sha256 or "",
                raw_bytes=len(result.body or b""),
                raw_path=str(raw_path),
                parser_version=PARSER_VERSION,
                quality=quality_report,
                promotion_state="staged",
                created_at=now,
            )
            snapshots.add(snapshot)
            session.flush()
            cameras = CameraRepository(session)
            cameras.bulk_insert(snapshot_id, records)

            added = changed = gone = None
            if previous is not None:
                old = cameras.source_keys(previous.snapshot_id)
                new = {r.source_key: r.source_version for r in records}
                added = sum(1 for k in new if k not in old)
                changed = sum(1 for k, v in new.items() if k in old and old[k] != v)
                gone = sum(1 for k in old if k not in new)
            else:
                added = len(records)

            if quarantine_reason:
                snapshots.mark(snapshot_id, "quarantined")
                job.status, job.finished_at, job.snapshot_id = "quarantined", clock(), snapshot_id
                job.message = f"snapshot quarantined: {quarantine_reason}; active snapshot retained"
                job.added_count, job.changed_count, job.no_longer_present_count = added, changed, gone
                session.commit()
                log.warning("camera snapshot quarantined: %s", quarantine_reason)
                return SyncOutcome("quarantined", snapshot_id, job.message, added, changed, gone)

            snapshots.promote(snapshot_id, region_id, clock())
            job.status, job.finished_at, job.snapshot_id = "succeeded", clock(), snapshot_id
            job.added_count, job.changed_count, job.no_longer_present_count = added, changed, gone
            job.message = f"promoted snapshot with {alpr} ALPR records (source base {isoformat_z(base_dt) if base_dt else 'unknown'})"
            session.commit()
            log.info("camera sync succeeded: %s", job.message)
            return SyncOutcome("succeeded", snapshot_id, job.message, added, changed, gone)
        except Exception as exc:  # noqa: BLE001 - the job row must record the failure
            session.rollback()
            with session_factory() as failure_session:
                failure_session.execute(
                    text("UPDATE sync_jobs SET status='failed', finished_at=:now, message=:msg WHERE id=:id"),
                    {"now": clock(), "msg": f"sync error: {type(exc).__name__}", "id": job.id if "job" in locals() else -1},
                )
                failure_session.commit()
            log.exception("camera sync crashed; last known good snapshot retained")
            return SyncOutcome("failed", None, f"sync error: {type(exc).__name__}")
        finally:
            session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _lock_key(region_id)})
            session.commit()
