"""Plan-trip use case, M4 scope: validate, obtain baseline candidates, return the Standard route with
endpoint-snapping and alignment disclosures and its encounter assessment.

Camera-aware candidate generation and comparison arrive in M5. When the assessment cannot run, the
result says `not_assessed` with null counts, never zero.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from deflockmigration.core.config_loader import AppConfig
from deflockmigration.core.errors import OUTSIDE_SERVICE_AREA, ROUTER_UNAVAILABLE, VALIDATION_ERROR, AppError
from deflockmigration.domain.assessment import AssessmentResult
from deflockmigration.domain.routes import AssessmentCoverage, CameraScope, EngineRoute, LatLon, RouteProfile
from deflockmigration.routing.candidates import alignment_warnings, choose_standard, dedupe, haversine_m, snap_distances_m, validate_maneuvers
from deflockmigration.routing.provider import RoutingProvider

log = logging.getLogger(__name__)
MIN_TRIP_DISTANCE_M = 25.0
Assessor = Callable[[EngineRoute, CameraScope, str | None], AssessmentResult]


@dataclass(frozen=True)
class PlannedOption:
    route_id: str
    profiles: list[RouteProfile]
    route: EngineRoute
    extra_duration_s: float
    extra_distance_m: float
    origin_snap_m: float
    destination_snap_m: float
    assessment: AssessmentResult | None


@dataclass(frozen=True)
class PlanResult:
    request_id: str
    options: list[PlannedOption]
    reference_duration_s: float
    candidates_evaluated: int
    search_status: str
    warnings: list[str]
    assessment_coverage_status: AssessmentCoverage


class PlanTripService:
    def __init__(self, config: AppConfig, routing: RoutingProvider, assessor: Assessor | None = None):
        self._config = config
        self._routing = routing
        self._assessor = assessor

    def plan(self, origin: LatLon, destination: LatLon, *, profiles: list[RouteProfile], camera_scope: CameraScope, snapshot_id: str | None = None) -> PlanResult:
        request_id = uuid.uuid4().hex
        boundary = self._config.service_boundary
        outside = [name for name, point in (("origin", origin), ("destination", destination)) if not boundary.contains(point.lat, point.lon)]
        if outside:
            raise AppError(
                OUTSIDE_SERVICE_AREA,
                "Trips must start and end inside the Denver pilot area.",
                details={"outside": outside, "service_boundary_id": boundary.boundary_id},
            )
        if haversine_m((origin.lat, origin.lon), (destination.lat, destination.lon)) < MIN_TRIP_DISTANCE_M:
            raise AppError(VALIDATION_ERROR, "Start and destination are the same place. Choose two different points.", details={"min_distance_m": MIN_TRIP_DISTANCE_M})
        alternates = self._config.providers.routing.alternates
        candidates = dedupe(self._routing.baseline_candidates(origin, destination, alternates=alternates, request_id=request_id))
        if not candidates:
            raise AppError(ROUTER_UNAVAILABLE, "The routing engine returned no candidates.")
        valid = [c for c in candidates if not validate_maneuvers(c)]
        if not valid:
            log.warning("all %s candidates failed maneuver validation", len(candidates))
            raise AppError(ROUTER_UNAVAILABLE, "The routing engine returned routes without usable directions.")
        standard = choose_standard(valid)
        warnings = list(dict.fromkeys(w for c in valid for w in c.warnings))
        warnings.extend(alignment_warnings(standard))
        if standard.source != "primary":
            warnings.append("Standard route is the fastest baseline candidate by reported time; it differs from the engine's primary result.")
        origin_snap, destination_snap = snap_distances_m(standard, origin, destination)

        assessment = self._assessor(standard, camera_scope, snapshot_id) if self._assessor else None
        if assessment is not None:
            warnings.extend(assessment.warnings)
        coverage = AssessmentCoverage.NOT_ASSESSED
        if assessment is not None and assessment.status == "complete":
            coverage = AssessmentCoverage.COMPLETE
        elif assessment is not None and assessment.status == "partial":
            coverage = AssessmentCoverage.PARTIAL

        option = PlannedOption(
            route_id=uuid.uuid4().hex,
            profiles=[RouteProfile.STANDARD],
            route=standard,
            extra_duration_s=0.0,
            extra_distance_m=0.0,
            origin_snap_m=origin_snap,
            destination_snap_m=destination_snap,
            assessment=assessment,
        )
        return PlanResult(
            request_id=request_id,
            options=[option],
            reference_duration_s=standard.duration_s,
            candidates_evaluated=len(valid),
            search_status="completed",
            warnings=list(dict.fromkeys(warnings)),
            assessment_coverage_status=coverage,
        )
