from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from deflockmigration.api.schemas import (
    DISCLAIMER,
    MANEUVER_TYPE_NAMES,
    AssessmentOut,
    AssociationOut,
    EncounterOut,
    ManeuverOut,
    PlanRequest,
    PlanResponse,
    ProfileOutcomeOut,
    RouteOptionOut,
    SearchOut,
    SensitivityOut,
)
from deflockmigration.application.plan_trip import PlanResult, PlanTripService
from deflockmigration.core.clock import isoformat_z
from deflockmigration.core.errors import VALIDATION_ERROR, AppError
from deflockmigration.domain.assessment import AssessmentResult
from deflockmigration.domain.routes import DetourLimit, LatLon
from deflockmigration.geospatial.polyline import to_geojson_linestring
from deflockmigration.storage.repositories import SnapshotRepository

router = APIRouter(tags=["routes"])
log = logging.getLogger(__name__)
ASSESSMENT_MEANING = (
    "Counts are mapped OpenStreetMap records associated with roads the route traverses, within the counting radius; "
    "they are not observed recordings, people, or plates, and unmapped or mislocated cameras may still be present."
)
SEARCH_MEANING = (
    "Best among the candidates this bounded search evaluated, not a proof of a globally optimal camera-minimum path. "
    "Exposure counts mapped records associated with or unresolved near a route (matched plus uncertain), each record once. "
    "Artificial search penalties never change reported travel times."
)


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


def _assessment_out(a: AssessmentResult) -> AssessmentOut:
    return AssessmentOut(
        status=a.status,
        counting_method_version=a.counting_method_version,
        radius_m=a.radius_m,
        scope=a.scope,
        snapshot_id=a.snapshot_id,
        graph_version=a.graph_version,
        coverage_fraction=a.coverage_fraction,
        matched_record_count=a.matched_record_count,
        uncertain_record_count=a.uncertain_record_count,
        sensitivity=[SensitivityOut(radius_m=s.radius_m, records_within=s.records_within) for s in a.sensitivity],
        encounters=[
            EncounterOut(
                source_key=e.source_key, lat=e.lat, lon=e.lon, status=e.status.value, reason=e.reason, distance_m=e.distance_m,
                position_m=e.position_m, position_fraction=e.position_fraction, pass_count=e.pass_count, site_group_id=e.site_group_id,
                manufacturer=e.manufacturer, is_flock=e.is_flock, lifecycle_state=e.lifecycle_state, direction_raw=e.direction_raw,
                direction_conflict=e.direction_conflict, heading_relation=e.heading_relation, in_envelope=e.in_envelope, source_url=e.source_url,
                source_timestamp=e.source_timestamp, check_date=e.check_date,
                association=AssociationOut(**{k: v for k, v in e.association.__dict__.items() if k != "reason"}) if e.association else None,
            )
            for e in a.encounters
        ],
        warnings=a.warnings,
        meaning=ASSESSMENT_MEANING,
    )


def _search_out(result: PlanResult) -> SearchOut:
    s = result.search
    route_ids = {option.route.encoded_shape_key(): option.route_id for option in result.options}
    return SearchOut(
        status=s.status.value,
        method_version=s.method_version,
        routing_calls_used=s.routing_calls_used,
        routing_calls_budget=s.routing_calls_budget,
        planning_deadline_seconds=s.planning_deadline_s,
        elapsed_seconds=s.elapsed_s,
        candidates_generated=s.candidates_generated,
        candidates_assessed=s.candidates_assessed,
        iterations=s.iterations,
        notes=s.notes,
        profile_outcomes=[
            ProfileOutcomeOut(
                profile=o.profile, outcome=o.outcome.value, message=o.message, max_extra_seconds=o.max_extra_s, max_relative_factor=o.max_relative_factor,
                bound_seconds=round(o.bound_s, 1) if o.bound_s is not None else None, best_exposure_count=o.best_exposure,
                route_id=route_ids.get(o.route_key) if o.route_key else None,
            )
            for o in s.profile_outcomes
        ],
        meaning=SEARCH_MEANING,
    )


@router.post("/routes/plan", response_model=PlanResponse)
def plan_route(body: PlanRequest, request: Request) -> PlanResponse:
    state = request.app.state
    config = state.config
    if body.region_id is not None and body.region_id != config.region.region_id:
        raise AppError(VALIDATION_ERROR, "Unknown region.", details={"region_id": body.region_id})
    snapshot_id, as_of, downloaded_at = _active_snapshot_versions(state.session_factory, config.region.region_id)
    assessor = getattr(state, "assessor", None)
    service = PlanTripService(config, state.routing, assessor)
    detour = DetourLimit(float(body.detour_limits.max_extra_seconds), float(body.detour_limits.max_relative_factor)) if body.detour_limits else None
    metrics = getattr(state, "metrics", None)
    try:
        result = service.plan(
            LatLon(body.origin.lat, body.origin.lon),
            LatLon(body.destination.lat, body.destination.lon),
            profiles=body.profiles,
            camera_scope=body.camera_scope,
            snapshot_id=snapshot_id,
            detour_limits=detour,
        )
    except AppError as exc:
        if metrics is not None:
            metrics.observe_plan_error(exc.code)  # the code only, never the trip
        raise
    if metrics is not None:
        metrics.observe_plan(search_status=result.search_status, option_count=len(result.options), routing_calls=result.search.routing_calls_used, elapsed_s=result.search.elapsed_s)
    options = []
    for option in result.options:
        route = option.route
        assessment = option.assessment
        options.append(RouteOptionOut(
            route_id=option.route_id,
            profiles=[p.value for p in option.profiles],
            geometry=to_geojson_linestring(route.shape),
            estimated_duration_seconds=round(route.duration_s, 1),
            length_meters=round(route.length_m, 1),
            extra_duration_seconds=round(option.extra_duration_s, 1),
            extra_distance_meters=round(option.extra_distance_m, 1),
            origin_snap_distance_meters=option.origin_snap_m,
            destination_snap_distance_meters=option.destination_snap_m,
            matched_camera_record_count=assessment.matched_record_count if assessment else None,
            uncertain_nearby_camera_count=assessment.uncertain_record_count if assessment else None,
            exposure_count=option.exposure,
            generated_by=option.generated_by,
            detour_bound_seconds=round(option.detour_bound_s, 1) if option.detour_bound_s is not None else None,
            counting_method_version=assessment.counting_method_version if assessment and assessment.status != "not_assessed" else None,
            camera_scope=body.camera_scope.value,
            camera_snapshot_id=snapshot_id,
            camera_source_as_of=as_of,
            camera_downloaded_at=downloaded_at,
            road_graph_version=assessment.graph_version if assessment and assessment.graph_version else config.region.routing_graph.id,
            assessment_coverage_status=assessment.status if assessment else "not_assessed",
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
            assessment=_assessment_out(assessment) if assessment else None,
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
        search=_search_out(result),
        disclaimer=DISCLAIMER,
    )
