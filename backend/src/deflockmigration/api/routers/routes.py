from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from deflockmigration.api.schemas import DISCLAIMER, MANEUVER_TYPE_NAMES, ManeuverOut, PlanRequest, PlanResponse, RouteOptionOut
from deflockmigration.application.plan_trip import PlanTripService
from deflockmigration.core.clock import isoformat_z
from deflockmigration.core.errors import VALIDATION_ERROR, AppError
from deflockmigration.domain.routes import LatLon
from deflockmigration.geospatial.polyline import to_geojson_linestring
from deflockmigration.storage.repositories import SnapshotRepository

router = APIRouter(tags=["routes"])
log = logging.getLogger(__name__)


def _active_snapshot_versions(session_factory, region_id: str) -> tuple[str | None, str | None, str | None]:
    if session_factory is None:
        return None, None, None
    try:
        with session_factory() as session:
            snapshot = SnapshotRepository(session).get_active(region_id)
    except Exception as exc:  # noqa: BLE001 - routing must still work without the inventory
        log.warning("active snapshot lookup failed: %s", type(exc).__name__)
        return None, None, None
    if snapshot is None:
        return None, None, None
    as_of = isoformat_z(snapshot.timestamp_osm_base) if snapshot.timestamp_osm_base else None
    return snapshot.snapshot_id, as_of, isoformat_z(snapshot.downloaded_at_end)


@router.post("/routes/plan", response_model=PlanResponse)
def plan_route(body: PlanRequest, request: Request) -> PlanResponse:
    state = request.app.state
    config = state.config
    if body.region_id != config.region.region_id:
        raise AppError(VALIDATION_ERROR, "Unknown region.", details={"region_id": body.region_id})
    service = PlanTripService(config, state.routing)
    result = service.plan(
        LatLon(body.origin.lat, body.origin.lon),
        LatLon(body.destination.lat, body.destination.lon),
        profiles=body.profiles,
        camera_scope=body.camera_scope,
    )
    snapshot_id, as_of, downloaded_at = _active_snapshot_versions(state.session_factory, config.region.region_id)
    options = []
    for option in result.options:
        route = option.route
        options.append(RouteOptionOut(
            route_id=option.route_id,
            profiles=[p.value for p in option.profiles],
            geometry=to_geojson_linestring(route.shape),
            estimated_duration_seconds=round(route.duration_s, 1),
            length_meters=round(route.length_m, 1),
            extra_duration_seconds=round(option.extra_duration_s, 1),
            extra_distance_meters=round(option.extra_distance_m, 1),
            matched_camera_record_count=None,
            uncertain_nearby_camera_count=None,
            counting_method_version=None,
            camera_scope=body.camera_scope.value,
            camera_snapshot_id=snapshot_id,
            camera_source_as_of=as_of,
            camera_downloaded_at=downloaded_at,
            road_graph_version=config.region.routing_graph.id,
            assessment_coverage_status=result.assessment_coverage_status.value,
            search_status=result.search_status,
            warnings=route.warnings,
            maneuvers=[
                ManeuverOut(
                    instruction=m.instruction,
                    verbal_pre_transition_instruction=m.verbal_pre_transition_instruction,
                    street_names=m.street_names,
                    begin_street_names=m.begin_street_names,
                    length_meters=round(m.length_m, 1),
                    time_seconds=round(m.time_s, 1),
                    type=m.type,
                    type_name=MANEUVER_TYPE_NAMES.get(m.type, "unknown"),
                    begin_shape_index=m.begin_shape_index,
                    end_shape_index=m.end_shape_index,
                    roundabout_exit_count=m.roundabout_exit_count,
                    toll=m.toll,
                    highway=m.highway,
                )
                for m in route.maneuvers
            ],
            has_highway=route.has_highway,
            has_toll=route.has_toll,
            engine_candidate=route.engine_route_id,
        ))
    return PlanResponse(
        request_id=result.request_id,
        region_id=config.region.region_id,
        reference_duration_seconds=round(result.reference_duration_s, 1),
        candidates_evaluated=result.candidates_evaluated,
        search_status=result.search_status,
        assessment_coverage_status=result.assessment_coverage_status.value,
        warnings=result.warnings,
        options=options,
        disclaimer=DISCLAIMER,
    )
