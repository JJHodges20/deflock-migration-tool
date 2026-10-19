from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Query, Request

from deflockmigration.core.clock import isoformat_z
from deflockmigration.core.errors import CAMERA_DATA_UNAVAILABLE, VALIDATION_ERROR, AppError
from deflockmigration.domain.routes import CameraScope
from deflockmigration.storage.repositories import CameraRepository, SnapshotRepository

router = APIRouter(tags=["cameras"])
log = logging.getLogger(__name__)
SOURCE_KEY = re.compile(r"^osm:(node|way|relation):(\d{1,19})$")


def _parse_bbox(bbox: str, max_degrees: float) -> tuple[float, float, float, float]:
    parts = bbox.split(",")
    if len(parts) != 4:
        raise AppError(VALIDATION_ERROR, "bbox must be west,south,east,north.")
    try:
        west, south, east, north = (float(p) for p in parts)
    except ValueError as exc:
        raise AppError(VALIDATION_ERROR, "bbox must contain four numbers.") from exc
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise AppError(VALIDATION_ERROR, "bbox is not ordered west<east and south<north within valid ranges.")
    if (east - west) > max_degrees or (north - south) > max_degrees:
        raise AppError(VALIDATION_ERROR, "bbox is too large for a camera viewport query; zoom in.", details={"max_degrees": max_degrees})
    return west, south, east, north


def _iso(value):
    return isoformat_z(value) if value else None


def _source_url(source_key: str) -> str:
    _, kind, ident = source_key.split(":")
    return f"https://www.openstreetmap.org/{kind}/{ident}"


def _feature(row: dict) -> dict:
    return {
        "type": "Feature",
        "id": row["id"],
        "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
        "properties": {
            "source_key": row["source_key"],
            "source_version": row["source_version"],
            "source_timestamp": _iso(row["source_timestamp"]),
            "manufacturer": row["manufacturer_normalized"],
            "is_flock": row["is_flock"],
            "operator": row["operator"],
            "direction_raw": row["direction_raw"],
            "camera_direction_raw": row["camera_direction_raw"],
            "direction_conflict": row["direction_conflict"],
            "lifecycle_state": row["lifecycle_state"],
            "lifecycle_evidence": row["lifecycle_evidence"],
            "uncertain": row["lifecycle_state"] == "no_longer_mapped",
            "check_date": row["check_date"],
            "geometry_quality": row["geometry_quality"],
            "in_envelope": row["in_envelope"],
            "missing_since": _iso(row["missing_since"]),
            "source_url": _source_url(row["source_key"]),
        },
    }


def _active_snapshot(state):
    if state.session_factory is None:
        raise AppError(CAMERA_DATA_UNAVAILABLE, "The camera inventory database is not configured.")
    region_id = state.config.region.region_id
    with state.session_factory() as session:
        snapshot = SnapshotRepository(session).get_active(region_id)
        if snapshot is None:
            raise AppError(CAMERA_DATA_UNAVAILABLE, "No validated camera snapshot has been published yet.")
        session.expunge(snapshot)
        return snapshot


@router.get("/cameras")
def cameras(request: Request, bbox: str = Query(..., max_length=120), scope: CameraScope = CameraScope.ALL_ALPR) -> dict:
    state = request.app.state
    west, south, east, north = _parse_bbox(bbox, state.settings.cameras_max_bbox_degrees)
    try:
        snapshot = _active_snapshot(state)
        with state.session_factory() as session:
            rows = CameraRepository(session).in_bbox(snapshot.snapshot_id, west, south, east, north, flock_only=scope is CameraScope.FLOCK_ONLY)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("camera query failed: %s", type(exc).__name__)
        raise AppError(CAMERA_DATA_UNAVAILABLE, "The camera inventory is temporarily unavailable.") from exc
    features = [_feature(row) for row in rows]
    return {
        "type": "FeatureCollection",
        "features": features,
        "snapshot": {
            "snapshot_id": snapshot.snapshot_id,
            "timestamp_osm_base": _iso(snapshot.timestamp_osm_base),
            "downloaded_at": _iso(snapshot.downloaded_at_end),
            "scope": scope.value,
            "truncated": len(rows) >= 5000,
            "counts_meaning": "mapped OpenStreetMap records, not physical devices; 'uncertain' records are no longer present in the source",
        },
    }


@router.get("/cameras/record")
def camera_record(request: Request, source_key: str = Query(..., max_length=60)) -> dict:
    """One record in the active snapshot plus its history across retained snapshots (explains changed recommendations)."""
    state = request.app.state
    if not SOURCE_KEY.match(source_key):
        raise AppError(VALIDATION_ERROR, "source_key must look like osm:node:123.")
    try:
        snapshot = _active_snapshot(state)
        with state.session_factory() as session:
            repo = CameraRepository(session)
            current = repo.get_current(snapshot.snapshot_id, source_key)
            history = repo.history(source_key, limit=50)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("camera record query failed: %s", type(exc).__name__)
        raise AppError(CAMERA_DATA_UNAVAILABLE, "The camera inventory is temporarily unavailable.") from exc
    return {
        "source_key": source_key,
        "source_url": _source_url(source_key),
        "active_snapshot_id": snapshot.snapshot_id,
        "current": _feature(current) if current else None,
        "history": [
            {
                "snapshot_id": h["snapshot_id"],
                "snapshot_state": h["promotion_state"],
                "snapshot_source_as_of": _iso(h["timestamp_osm_base"]),
                "source_version": h["source_version"],
                "source_timestamp": _iso(h["source_timestamp"]),
                "lat": h["lat"],
                "lon": h["lon"],
                "is_alpr": h["is_alpr"],
                "manufacturer": h["manufacturer_normalized"],
                "is_flock": h["is_flock"],
                "operator": h["operator"],
                "direction_raw": h["direction_raw"],
                "lifecycle_state": h["lifecycle_state"],
                "lifecycle_evidence": h["lifecycle_evidence"],
                "check_date": h["check_date"],
                "in_envelope": h["in_envelope"],
                "missing_since": _iso(h["missing_since"]),
            }
            for h in history
        ],
        "meaning": "Versions are OpenStreetMap edits seen by this project's snapshots; they are not field inspections.",
    }
