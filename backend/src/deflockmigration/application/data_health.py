"""Sanitized Data Health view: source, snapshot, sync, scheduler, provider policy, inventory, graph, geocoder, and
boundary versions. Never any trip data."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import text

from deflockmigration.core.clock import Clock, isoformat_z, utc_now
from deflockmigration.core.config_loader import AppConfig
from deflockmigration.geocoding.provider import Geocoder
from deflockmigration.routing.provider import RoutingProvider
from deflockmigration.storage.db import SessionFactory
from deflockmigration.storage.repositories import SnapshotRepository, SyncJobRepository


@dataclass
class DataHealth:
    region_id: str
    service_boundary_id: str
    envelope_id: str
    config_version: int
    camera_source: dict = field(default_factory=dict)
    provider_policy: dict = field(default_factory=dict)
    snapshot: dict | None = None
    inventory: dict = field(default_factory=dict)
    last_sync: dict | None = None
    last_failure: dict | None = None
    recent_syncs: list = field(default_factory=list)
    staleness: dict = field(default_factory=dict)
    scheduler: dict = field(default_factory=dict)
    router: dict = field(default_factory=dict)
    geocoder: dict = field(default_factory=dict)
    basemap: dict = field(default_factory=dict)
    database: dict = field(default_factory=dict)


def _camera_source_view(region) -> dict:
    source = region.camera_source
    view = {
        "adapter": source.adapter,
        "refresh_interval_hours": source.refresh_interval_hours,
        "query_bbox_swne": source.query_bbox_swne,
        "license": "ODbL 1.0 (OpenStreetMap contributors)",
    }
    if source.adapter == "geofabrik_extract" and source.extract is not None:
        view["extract"] = {
            "url": source.extract.url,
            "file": source.extract.file,
            "replication_url": source.extract.replication_url,
            "outline_file": str(source.extract.outline_file) if source.extract.outline_file else None,
            "coverage_note": source.extract.coverage_note,
            "cadence": "the publisher issues one change file per day; the worker checks once per interval and applies what is new",
        }
    return view


def _provider_policy_view(config) -> dict:
    source = config.region.camera_source
    if source.adapter == "geofabrik_extract" and source.extract is not None:
        limits = config.providers.camera_extract
        return {
            "endpoint": source.extract.replication_url,
            "query": "the publisher's regional extract kept current with its daily change files; one fixed region, never derived from a trip",
            "one_request_at_a_time": True,
            "refresh_interval_hours": source.refresh_interval_hours,
            "identifies_application": True,
            "timeout_seconds": limits.timeout_seconds,
            "pause_after_rate_limit_seconds": max(limits.pause_after_rate_limit_seconds, source.min_pause_after_429_seconds),
            "max_attempts": limits.max_attempts,
            "backoff_seconds": limits.backoff_seconds,
            "no_endpoint_rotation": True,
            "full_download_policy": ("one full extract download only when no seed can be copied or the needed change files are no longer published"
                                     if limits.allow_full_download else "full downloads disabled"),
        }
    limits = config.providers.camera_source
    return {
        "endpoint": source.endpoint,
        "query": "one fixed query over the camera-data envelope; never derived from a trip",
        "one_request_at_a_time": True,
        "refresh_interval_hours": source.refresh_interval_hours,
        "identifies_application": True,
        "timeout_seconds": limits.timeout_seconds,
        "pause_after_rate_limit_seconds": max(limits.pause_after_rate_limit_seconds, source.min_pause_after_429_seconds),
        "max_attempts": limits.max_attempts,
        "backoff_seconds": limits.backoff_seconds,
        "no_endpoint_rotation": True,
    }


def _job_view(job) -> dict | None:
    if job is None:
        return None
    return {
        "status": job.status,
        "trigger": job.trigger,
        "started_at": isoformat_z(job.started_at),
        "finished_at": isoformat_z(job.finished_at) if job.finished_at else None,
        "snapshot_id": job.snapshot_id,
        "http_status": job.http_status,
        "attempts": job.attempts,
        "added": job.added_count,
        "changed": job.changed_count,
        "no_longer_present": job.no_longer_present_count,
        "message": job.message,
    }


def schedule_view(
    active_downloaded_at: dt.datetime | None,
    interval_hours: float,
    now: dt.datetime,
    *,
    overdue_grace_hours: float,
    cooldown_minutes: int,
    last_trigger: str | None,
) -> dict:
    """What the single scheduler will do next, derived the same way the worker derives it (roadmap 3.2 and M7 gate):
    scheduled syncs run only while the camera-sync container runs, and a restart waits for the remainder of the interval."""
    interval_s = interval_hours * 3600.0
    base = {
        "interval_hours": interval_hours,
        "manual_refresh_cooldown_minutes": cooldown_minutes,
        "last_trigger": last_trigger,
        "runs_only_while_stack_is_up": True,
        "note": "One scheduler for the fixed region. A restart waits for the remainder of the interval instead of querying again; manual refreshes share the cooldown and concurrent runs coalesce into one.",
    }
    if active_downloaded_at is None:
        return {**base, "next_due_at": None, "due_in_seconds": 0, "overdue": True, "cooldown_remaining_seconds": 0, "state": "no snapshot yet; the worker syncs as soon as it runs"}
    due_at = active_downloaded_at + dt.timedelta(seconds=interval_s)
    due_in = (due_at - now).total_seconds()
    overdue = due_in < -overdue_grace_hours * 3600.0
    cooldown_remaining = max(0.0, cooldown_minutes * 60.0 - (now - active_downloaded_at).total_seconds())
    if overdue:
        state = "overdue: the scheduled sync has not run; is the camera-sync container running?"
    elif due_in <= 0:
        state = "due now (within the grace period)"
    else:
        state = "on schedule"
    return {
        **base,
        "next_due_at": isoformat_z(due_at),
        "due_in_seconds": round(max(0.0, due_in)),
        "overdue": overdue,
        "cooldown_remaining_seconds": round(cooldown_remaining),
        "state": state,
    }


def storage_stats(session_factory: SessionFactory | None) -> dict:
    """Database and snapshot store sizes: counts and bytes of public data, no trip data (roadmap 16)."""
    if session_factory is None:
        return {"available": False, "message": "database not configured"}
    try:
        with session_factory() as session:
            by_state = {row.state: row.n for row in session.execute(text("SELECT promotion_state AS state, count(*) AS n FROM camera_snapshots GROUP BY promotion_state"))}
            records = session.execute(text("SELECT count(*) FROM camera_records")).scalar() or 0
            diffs = session.execute(text("SELECT count(*) FROM snapshot_diffs")).scalar() or 0
            associations = session.execute(text("SELECT count(*) FROM camera_road_associations")).scalar() or 0
            jobs = session.execute(text("SELECT count(*) FROM sync_jobs")).scalar() or 0
            raw_bytes = session.execute(text("SELECT coalesce(sum(raw_bytes), 0) FROM camera_snapshots")).scalar() or 0
            db_bytes = session.execute(text("SELECT pg_database_size(current_database())")).scalar() or 0
        return {
            "available": True,
            "snapshots_by_state": by_state,
            "camera_record_rows": int(records),
            "snapshot_diff_rows": int(diffs),
            "association_cache_rows": int(associations),
            "sync_job_rows": int(jobs),
            "raw_snapshot_bytes": int(raw_bytes),
            "database_bytes": int(db_bytes),
        }
    except Exception as exc:  # noqa: BLE001 - metrics must degrade, never crash
        return {"available": False, "message": f"database error: {type(exc).__name__}"}


def build_data_health(
    config: AppConfig,
    *,
    session_factory: SessionFactory | None,
    routing: RoutingProvider,
    geocoder: Geocoder,
    clock: Clock = utc_now,
) -> DataHealth:
    region = config.region
    quality = config.data_quality
    health = DataHealth(
        region_id=region.region_id,
        service_boundary_id=region.service_boundary.id,
        envelope_id=region.camera_data_envelope.id,
        config_version=region.config_version,
        camera_source=_camera_source_view(region),
        provider_policy=_provider_policy_view(config),
        inventory={
            "retain_missing_hours": quality.snapshot_validation.retain_missing_hours,
            "unresolved_disappearance": quality.snapshot_validation.unresolved_disappearance,
            "keep_superseded_snapshots": quality.retention.keep_superseded_snapshots,
            "keep_quarantined_snapshots": quality.retention.keep_quarantined_snapshots,
            "pending_review": [],
        },
        basemap={"id": region.basemap.id, "attribution": region.basemap.attribution, "max_zoom": region.basemap.max_zoom},
    )
    now = clock()
    stale_after = quality.snapshot_validation.stale_after_hours
    schedule_kwargs = dict(
        overdue_grace_hours=quality.snapshot_validation.overdue_grace_hours,
        cooldown_minutes=quality.snapshot_validation.manual_refresh_cooldown_minutes,
    )
    if session_factory is None:
        health.database = {"available": False, "message": "database not configured"}
        health.scheduler = schedule_view(None, region.camera_source.refresh_interval_hours, now, last_trigger=None, **schedule_kwargs)
    else:
        try:
            with session_factory() as session:
                snapshots = SnapshotRepository(session)
                snapshot = snapshots.get_active(region.region_id)
                jobs = SyncJobRepository(session)
                latest = jobs.latest(region.region_id)
                health.last_sync = _job_view(latest)
                health.last_failure = _job_view(jobs.latest_failure(region.region_id))
                health.recent_syncs = [_job_view(j) for j in jobs.recent(region.region_id, limit=5)]
                health.inventory["pending_review"] = [
                    {"snapshot_id": s.snapshot_id, "created_at": isoformat_z(s.created_at), "reason": (s.quality or {}).get("quarantine_reason"), "alpr_count": s.alpr_count}
                    for s in snapshots.pending_review(region.region_id)
                ]
                health.inventory["retained_snapshots"] = len(snapshots.list(region.region_id, limit=1000))
                health.database = {"available": True}
                health.scheduler = schedule_view(snapshot.downloaded_at_end if snapshot else None, region.camera_source.refresh_interval_hours, now, last_trigger=latest.trigger if latest else None, **schedule_kwargs)
                if snapshot is not None:
                    age_hours = (now - snapshot.timestamp_osm_base).total_seconds() / 3600 if snapshot.timestamp_osm_base else None
                    diff = snapshots.diff_for(snapshot.snapshot_id)
                    health.snapshot = {
                        "snapshot_id": snapshot.snapshot_id,
                        "timestamp_osm_base": isoformat_z(snapshot.timestamp_osm_base) if snapshot.timestamp_osm_base else None,
                        "downloaded_at": isoformat_z(snapshot.downloaded_at_end),
                        "promoted_at": isoformat_z(snapshot.promoted_at) if snapshot.promoted_at else None,
                        "element_count": snapshot.element_count,
                        "record_count": snapshot.record_count,
                        "alpr_count": snapshot.alpr_count,
                        "flock_count": snapshot.flock_count,
                        "unknown_manufacturer_count": snapshot.unknown_manufacturer_count,
                        "in_envelope_alpr_count": snapshot.in_envelope_alpr_count,
                        "no_longer_mapped_count": snapshot.no_longer_mapped_count,
                        "previous_active_snapshot_id": snapshot.previous_active_snapshot_id,
                        "parser_version": snapshot.parser_version,
                        "quality": snapshot.quality,
                        "review_note": snapshot.review_note,
                        "source": snapshot.source,
                        "source_details": snapshot.source_details,
                        "diff": {
                            "added": diff.added_count,
                            "changed": diff.changed_count,
                            "missing": diff.missing_count,
                            "reappeared": diff.reappeared_count,
                            "carried": diff.carried_count,
                            "expired": diff.expired_count,
                        } if diff else None,
                        "counts_meaning": "mapped OpenStreetMap records in the snapshot, not physical devices",
                    }
                    health.staleness = {
                        "age_hours": round(age_hours, 1) if age_hours is not None else None,
                        "stale_after_hours": stale_after,
                        "is_stale": bool(age_hours is not None and age_hours > stale_after),
                    }
                else:
                    health.staleness = {"age_hours": None, "stale_after_hours": stale_after, "is_stale": True, "message": "no camera snapshot yet"}
        except Exception as exc:  # noqa: BLE001 - health must degrade, never crash
            health.database = {"available": False, "message": f"database error: {type(exc).__name__}"}
            health.scheduler = schedule_view(None, region.camera_source.refresh_interval_hours, now, last_trigger=None, **schedule_kwargs)
    status = routing.status()
    health.router = {
        "available": status.available,
        "version": status.version,
        "tileset_last_modified": status.tileset_last_modified,
        "has_tiles": status.has_tiles,
        "has_admins": status.has_admins,
        "has_timezones": status.has_timezones,
        "graph_id": region.routing_graph.id,
        "extract_data_timestamp": region.routing_graph.extract_data_timestamp,
        "rebuild_cadence": region.routing_graph.rebuild_cadence,
        "message": status.message,
    }
    gstatus = geocoder.status()
    health.geocoder = {
        "configured": gstatus.configured,
        "available": gstatus.available,
        "provider": gstatus.provider,
        "data_updated": gstatus.data_updated,
        "message": gstatus.message,
    }
    return health


def as_dict(health: DataHealth) -> dict:
    return {
        "region_id": health.region_id,
        "service_boundary_id": health.service_boundary_id,
        "envelope_id": health.envelope_id,
        "config_version": health.config_version,
        "camera_source": health.camera_source,
        "provider_policy": health.provider_policy,
        "snapshot": health.snapshot,
        "inventory": health.inventory,
        "last_sync": health.last_sync,
        "last_failure": health.last_failure,
        "recent_syncs": health.recent_syncs,
        "staleness": health.staleness,
        "scheduler": health.scheduler,
        "router": health.router,
        "geocoder": health.geocoder,
        "basemap": health.basemap,
        "database": health.database,
        "generated_at": isoformat_z(dt.datetime.now(dt.UTC)),
    }
