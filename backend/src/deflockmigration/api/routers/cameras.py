from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request

from deflockmigration.core.clock import isoformat_z
from deflockmigration.core.errors import CAMERA_DATA_UNAVAILABLE, VALIDATION_ERROR, AppError
from deflockmigration.domain.routes import CameraScope
from deflockmigration.storage.repositories import CameraRepository, SnapshotRepository

router = APIRouter(tags=["cameras"])
log = logging.getLogger(__name__)


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


@router.get("/cameras")
def cameras(request: Request, bbox: str = Query(..., max_length=120), scope: CameraScope = CameraScope.ALL_ALPR) -> dict:
    state = request.app.state
    settings = state.settings
    west, south, east, north = _parse_bbox(bbox, settings.cameras_max_bbox_degrees)
    if state.session_factory is None:
        raise AppError(CAMERA_DATA_UNAVAILABLE, "The camera inventory database is not configured.")
    region_id = state.config.region.region_id
    try:
        with state.session_factory() as session:
            snapshot = SnapshotRepository(session).get_active(region_id)
            if snapshot is None:
                raise AppError(CAMERA_DATA_UNAVAILABLE, "No validated camera snapshot has been published yet.")
            rows = CameraRepository(session).in_bbox(snapshot.snapshot_id, west, south, east, north, flock_only=scope is CameraScope.FLOCK_ONLY)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("camera query failed: %s", type(exc).__name__)
        raise AppError(CAMERA_DATA_UNAVAILABLE, "The camera inventory is temporarily unavailable.") from exc
    features = [
        {
            "type": "Feature",
            "id": row["id"],
            "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
            "properties": {
                "source_key": row["source_key"],
                "source_version": row["source_version"],
                "source_timestamp": isoformat_z(row["source_timestamp"]) if row["source_timestamp"] else None,
                "manufacturer": row["manufacturer_normalized"],
                "is_flock": row["is_flock"],
                "operator": row["operator"],
                "direction_raw": row["direction_raw"],
                "camera_direction_raw": row["camera_direction_raw"],
                "direction_conflict": row["direction_conflict"],
                "lifecycle_state": row["lifecycle_state"],
                "check_date": row["check_date"],
                "geometry_quality": row["geometry_quality"],
            },
        }
        for row in rows
    ]
    return {
        "type": "FeatureCollection",
        "features": features,
        "snapshot": {
            "snapshot_id": snapshot.snapshot_id,
            "timestamp_osm_base": isoformat_z(snapshot.timestamp_osm_base) if snapshot.timestamp_osm_base else None,
            "downloaded_at": isoformat_z(snapshot.downloaded_at_end),
            "scope": scope.value,
            "truncated": len(rows) >= 5000,
            "counts_meaning": "mapped OpenStreetMap records, not physical devices",
        },
    }
