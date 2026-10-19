"""Sanitized Data Health view: source, snapshot, sync, inventory, graph, geocoder, and boundary versions."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

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
    snapshot: dict | None = None
    inventory: dict = field(default_factory=dict)
    last_sync: dict | None = None
    last_failure: dict | None = None
    recent_syncs: list = field(default_factory=list)
    staleness: dict = field(default_factory=dict)
    router: dict = field(default_factory=dict)
    geocoder: dict = field(default_factory=dict)
    basemap: dict = field(default_factory=dict)
    database: dict = field(default_factory=dict)


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
        camera_source={
            "adapter": region.camera_source.adapter,
            "refresh_interval_hours": region.camera_source.refresh_interval_hours,
            "query_bbox_swne": region.camera_source.query_bbox_swne,
            "license": "ODbL 1.0 (OpenStreetMap contributors)",
        },
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
    if session_factory is None:
        health.database = {"available": False, "message": "database not configured"}
    else:
        try:
            with session_factory() as session:
                snapshots = SnapshotRepository(session)
                snapshot = snapshots.get_active(region.region_id)
                jobs = SyncJobRepository(session)
                health.last_sync = _job_view(jobs.latest(region.region_id))
                health.last_failure = _job_view(jobs.latest_failure(region.region_id))
                health.recent_syncs = [_job_view(j) for j in jobs.recent(region.region_id, limit=5)]
                health.inventory["pending_review"] = [
                    {"snapshot_id": s.snapshot_id, "created_at": isoformat_z(s.created_at), "reason": (s.quality or {}).get("quarantine_reason"), "alpr_count": s.alpr_count}
                    for s in snapshots.pending_review(region.region_id)
                ]
                health.inventory["retained_snapshots"] = len(snapshots.list(region.region_id, limit=1000))
                health.database = {"available": True}
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
        "snapshot": health.snapshot,
        "inventory": health.inventory,
        "last_sync": health.last_sync,
        "last_failure": health.last_failure,
        "recent_syncs": health.recent_syncs,
        "staleness": health.staleness,
        "router": health.router,
        "geocoder": health.geocoder,
        "basemap": health.basemap,
        "database": health.database,
        "generated_at": isoformat_z(dt.datetime.now(dt.UTC)),
    }
