"""Camera inventory refresh (roadmap section 8).

Fixed region, never a trip. Steps: lock, fetch with the policy-aware client, validate, normalize,
check the envelope, carry over records that vanished from the source as "no longer mapped" (uncertain,
for a bounded time), store the raw snapshot and a diff, quarantine suspicious results, promote
atomically, prune old snapshots. Failures keep the last known good snapshot.
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
from deflockmigration.domain.cameras import LifecycleState
from deflockmigration.ingestion.diff import compute_diff
from deflockmigration.ingestion.normalize import normalize_elements
from deflockmigration.ingestion.quality import evaluate_snapshot
from deflockmigration.storage.db import SessionFactory
from deflockmigration.storage.models import CameraSnapshot, SnapshotDiff, SyncJob
from deflockmigration.storage.repositories import CameraRepository, SnapshotRepository, SyncJobRepository

log = logging.getLogger(__name__)
PARSER_VERSION = "normalize-1.1"
CARRY_WARNING = "no longer mapped in this source snapshot; retained as uncertain"
LOCK_SKIP_MESSAGE = "another sync holds the region lock; its result applies to this request as well"


@dataclass(frozen=True)
class SyncOutcome:
    status: str  # succeeded | failed | quarantined | skipped
    snapshot_id: str | None
    message: str
    added: int | None = None
    changed: int | None = None
    no_longer_present: int | None = None
    carried: int | None = None
    pruned: int | None = None


def _lock_key(region_id: str) -> int:
    return int(hashlib.sha256(f"camera-sync:{region_id}".encode()).hexdigest()[:15], 16)


def _carry_row(previous_row: dict, new_snapshot_id: str, missing_since: dt.datetime, last_seen: str) -> dict:
    row = {k: v for k, v in previous_row.items() if k not in ("id", "lat", "lon")}
    row["snapshot_id"] = new_snapshot_id
    row["geom"] = f"SRID=4326;POINT({previous_row['lon']} {previous_row['lat']})"
    row["lifecycle_state"] = str(LifecycleState.NO_LONGER_MAPPED)
    row["lifecycle_evidence"] = f"absent from the source query since {isoformat_z(missing_since)}; last seen in {last_seen}"
    warnings = [w for w in (previous_row.get("parse_warnings") or []) if w != CARRY_WARNING]
    row["parse_warnings"] = [*warnings, CARRY_WARNING]
    row["missing_since"] = missing_since
    row["last_seen_snapshot_id"] = last_seen
    return row


def run_sync(
    config: AppConfig,
    session_factory: SessionFactory,
    client: OverpassClient,
    *,
    snapshot_dir: Path,
    trigger: str = "scheduled",
    clock: Clock = utc_now,
    force: bool = False,
) -> SyncOutcome:
    """One refresh of the fixed region. Concurrent runs coalesce on the region lock (the second one is skipped and
    the running sync's result applies); manual refreshes share a cooldown unless `force` is set."""
    region = config.region
    region_id = region.region_id
    quality_cfg = config.data_quality.snapshot_validation
    retention = config.data_quality.retention
    now = clock()

    with session_factory() as session:
        locked = session.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": _lock_key(region_id)}).scalar()
        if not locked:
            return SyncOutcome("skipped", None, LOCK_SKIP_MESSAGE)
        job = None
        try:
            jobs = SyncJobRepository(session)
            snapshots = SnapshotRepository(session)
            if trigger == "manual" and not force:
                active = snapshots.get_active(region_id)
                cooldown_s = quality_cfg.manual_refresh_cooldown_minutes * 60
                if active is not None and (now - active.downloaded_at_end).total_seconds() < cooldown_s:
                    age_min = (now - active.downloaded_at_end).total_seconds() / 60
                    message = (f"manual refresh skipped: the active snapshot was downloaded {age_min:.0f} min ago and operator refreshes share a "
                               f"{quality_cfg.manual_refresh_cooldown_minutes} min cooldown (use --force to query the public instance anyway)")
                    session.add(SyncJob(region_id=region_id, trigger=trigger, started_at=now, finished_at=clock(), status="skipped", snapshot_id=active.snapshot_id, attempts=0, message=message[:400]))
                    session.commit()
                    log.info("%s", message)
                    return SyncOutcome("skipped", active.snapshot_id, message)
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

            if snapshots.get(snapshot_id) is not None:
                job.status, job.finished_at, job.snapshot_id, job.message = "succeeded", clock(), snapshot_id, "identical snapshot already stored"
                session.commit()
                return SyncOutcome("succeeded", snapshot_id, job.message, 0, 0, 0, 0, 0)

            snapshot_dir.mkdir(parents=True, exist_ok=True)
            raw_path = snapshot_dir / f"{snapshot_id}.json"
            raw_path.write_bytes(result.body or b"")

            records = normalize_elements(elements)
            envelope = config.envelope
            in_envelope = {r.source_key: envelope.contains(r.lat, r.lon) for r in records}
            alpr = sum(1 for r in records if r.is_alpr)
            flock = sum(1 for r in records if r.is_alpr and r.is_flock)
            unknown = sum(1 for r in records if r.is_alpr and r.manufacturer_normalized is None)
            in_env_alpr = sum(1 for r in records if r.is_alpr and in_envelope[r.source_key])

            previous = snapshots.get_active(region_id)
            verdict = evaluate_snapshot(len(elements), alpr, previous.alpr_count if previous else None, quality_cfg)

            cameras = CameraRepository(session)
            previous_rows = cameras.rows_by_key(previous.snapshot_id) if previous else {}
            previous_present = {k: row["source_version"] for k, row in previous_rows.items() if row["lifecycle_state"] != str(LifecycleState.NO_LONGER_MAPPED)}
            previous_carried = {k for k, row in previous_rows.items() if row["lifecycle_state"] == str(LifecycleState.NO_LONGER_MAPPED)}
            current = {r.source_key: r.source_version for r in records}
            diff = compute_diff(previous_present, previous_carried, current)

            carried_rows: list[dict] = []
            expired = 0
            retain_seconds = quality_cfg.retain_missing_hours * 3600
            for key in [*diff.missing_keys, *diff.still_missing_keys]:
                row = previous_rows[key]
                missing_since = row.get("missing_since") or now
                last_seen = row.get("last_seen_snapshot_id") or (previous.snapshot_id if previous else snapshot_id)
                age = (now - missing_since).total_seconds()
                if quality_cfg.unresolved_disappearance == "retain_as_uncertain" and age < retain_seconds:
                    carried_rows.append(_carry_row(row, snapshot_id, missing_since, last_seen))
                else:
                    expired += 1

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
                in_envelope_alpr_count=in_env_alpr,
                no_longer_mapped_count=len(carried_rows),
                raw_sha256=result.sha256 or "",
                raw_bytes=len(result.body or b""),
                raw_path=str(raw_path),
                parser_version=PARSER_VERSION,
                quality=verdict.report,
                promotion_state="staged",
                created_at=now,
            )
            snapshots.add(snapshot)
            session.flush()
            cameras.bulk_insert(snapshot_id, records, in_envelope=in_envelope)
            cameras.bulk_insert_rows(carried_rows)
            limit = retention.max_diff_keys_stored
            snapshots.add_diff(SnapshotDiff(
                snapshot_id=snapshot_id,
                previous_snapshot_id=previous.snapshot_id if previous else None,
                added_count=len(diff.added_keys),
                changed_count=len(diff.changed),
                missing_count=len(diff.missing_keys),
                reappeared_count=len(diff.reappeared_keys),
                carried_count=len(carried_rows),
                expired_count=expired,
                added_keys=diff.added_keys[:limit],
                changed=diff.changed[:limit],
                missing_keys=diff.missing_keys[:limit],
                created_at=now,
            ))
            job.added_count, job.changed_count, job.no_longer_present_count = len(diff.added_keys), len(diff.changed), len(diff.missing_keys)
            job.snapshot_id = snapshot_id

            if not verdict.publishable:
                snapshots.mark(snapshot_id, "quarantined")
                job.status, job.finished_at = "quarantined", clock()
                job.message = f"snapshot quarantined: {verdict.quarantine_reason}; active snapshot retained; review with deflock-snapshot-review"
                session.commit()
                log.warning("camera snapshot quarantined: %s", verdict.quarantine_reason)
                return SyncOutcome("quarantined", snapshot_id, job.message, len(diff.added_keys), len(diff.changed), len(diff.missing_keys), len(carried_rows), 0)

            snapshots.promote(snapshot_id, region_id, clock())
            pruned = snapshots.prune(region_id, keep_superseded=retention.keep_superseded_snapshots, keep_quarantined=retention.keep_quarantined_snapshots)
            for _, old_raw in pruned:
                if old_raw:
                    Path(old_raw).unlink(missing_ok=True)
            job.status, job.finished_at = "succeeded", clock()
            job.message = (
                f"promoted snapshot with {alpr} ALPR records ({in_env_alpr} inside the envelope, {len(carried_rows)} retained as no longer mapped; "
                f"source base {isoformat_z(base_dt) if base_dt else 'unknown'})"
            )
            session.commit()
            log.info("camera sync succeeded: %s; diff %s; pruned %s snapshot(s)", job.message, diff.counts, len(pruned))
            return SyncOutcome("succeeded", snapshot_id, job.message, len(diff.added_keys), len(diff.changed), len(diff.missing_keys), len(carried_rows), len(pruned))
        except Exception as exc:  # noqa: BLE001 - the job row must record the failure
            session.rollback()
            if job is not None:
                with session_factory() as failure_session:
                    failure_session.execute(
                        text("UPDATE sync_jobs SET status='failed', finished_at=:now, message=:msg WHERE id=:id"),
                        {"now": clock(), "msg": f"sync error: {type(exc).__name__}", "id": job.id},
                    )
                    failure_session.commit()
            log.exception("camera sync crashed; last known good snapshot retained")
            return SyncOutcome("failed", None, f"sync error: {type(exc).__name__}")
        finally:
            session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _lock_key(region_id)})
            session.commit()
