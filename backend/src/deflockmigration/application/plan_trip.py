"""Plan-trip use case, M1 scope: validate, obtain baseline candidates, return the Standard route.

No camera assessment happens yet (M4/M5). Counts are therefore reported as null with
assessment_coverage_status = not_assessed, never as zero.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from deflockmigration.core.config_loader import AppConfig
from deflockmigration.core.errors import OUTSIDE_SERVICE_AREA, ROUTER_UNAVAILABLE, AppError
from deflockmigration.domain.routes import AssessmentCoverage, CameraScope, EngineRoute, LatLon, RouteProfile
from deflockmigration.routing.candidates import choose_standard, dedupe, validate_maneuvers
from deflockmigration.routing.provider import RoutingProvider

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SnapshotVersions:
    camera_snapshot_id: str | None
    camera_source_as_of: str | None
    camera_downloaded_at: str | None


@dataclass(frozen=True)
class PlannedOption:
    route_id: str
    profiles: list[RouteProfile]
    route: EngineRoute
    extra_duration_s: float
    extra_distance_m: float


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
    def __init__(self, config: AppConfig, routing: RoutingProvider):
        self._config = config
        self._routing = routing

    def plan(self, origin: LatLon, destination: LatLon, *, profiles: list[RouteProfile], camera_scope: CameraScope) -> PlanResult:
        request_id = uuid.uuid4().hex
        boundary = self._config.service_boundary
        outside = [name for name, point in (("origin", origin), ("destination", destination)) if not boundary.contains(point.lat, point.lon)]
        if outside:
            raise AppError(
                OUTSIDE_SERVICE_AREA,
                "Trips must start and end inside the Denver pilot area.",
                details={"outside": outside, "service_boundary_id": boundary.boundary_id},
            )
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
        if standard.source != "primary":
            warnings.append("Standard route is the fastest baseline candidate by reported time; it differs from the engine's primary result.")
        labels = [RouteProfile.STANDARD]
        option = PlannedOption(route_id=uuid.uuid4().hex, profiles=labels, route=standard, extra_duration_s=0.0, extra_distance_m=0.0)
        return PlanResult(
            request_id=request_id,
            options=[option],
            reference_duration_s=standard.duration_s,
            candidates_evaluated=len(valid),
            search_status="completed",
            warnings=warnings,
            assessment_coverage_status=AssessmentCoverage.NOT_ASSESSED,
        )
