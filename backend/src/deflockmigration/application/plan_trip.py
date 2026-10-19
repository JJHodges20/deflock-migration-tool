"""Plan-trip use case (M5): validate, obtain baseline candidates, assess them, run the bounded camera-aware
candidate search for the requested preferences, rank deterministically, and return up to three genuinely
different options with explicit search and assessment disclosures.

Honesty rules enforced here: the Standard route is always returned; no preference silently degrades to the
Standard route (every requested preference gets an explicit outcome); a route that cannot be assessed says
`not_assessed` with null counts, never zero; reported travel times come straight from the engine.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from deflockmigration.application.candidate_search import Assessor, Candidate, CandidateSearch, candidate_from
from deflockmigration.application.ranking import rank_profiles
from deflockmigration.core.config_loader import AppConfig
from deflockmigration.core.errors import OUTSIDE_SERVICE_AREA, ROUTER_UNAVAILABLE, VALIDATION_ERROR, AppError
from deflockmigration.domain.assessment import AssessmentResult
from deflockmigration.domain.routes import AssessmentCoverage, CameraScope, DetourLimit, EngineRoute, LatLon, RouteProfile
from deflockmigration.domain.search import SEARCH_METHOD_VERSION, ProfileOutcome, ProfileOutcomeKind, SearchStatus, SearchSummary
from deflockmigration.routing.candidates import alignment_warnings, choose_standard, dedupe, haversine_m, snap_distances_m, validate_maneuvers
from deflockmigration.routing.provider import RoutingProvider

log = logging.getLogger(__name__)
MIN_TRIP_DISTANCE_M = 25.0
PROFILE_ORDER = [RouteProfile.STANDARD, RouteProfile.BALANCED, RouteProfile.FEWEST_MAPPED]


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
    exposure: int | None
    generated_by: str
    detour_bound_s: float | None


@dataclass(frozen=True)
class PlanResult:
    request_id: str
    options: list[PlannedOption]
    reference_duration_s: float
    candidates_evaluated: int
    search_status: str
    warnings: list[str]
    assessment_coverage_status: AssessmentCoverage
    search: SearchSummary


class PlanTripService:
    def __init__(self, config: AppConfig, routing: RoutingProvider, assessor: Assessor | None = None, *, clock: Callable[[], float] = time.monotonic):
        self._config = config
        self._routing = routing
        self._assessor = assessor
        self._clock = clock

    def _limits(self, user_limit: DetourLimit | None) -> dict[RouteProfile, DetourLimit]:
        """The user's detour limit applies to Balanced; Fewest mapped uses its configured, looser limit but is never
        tighter than the user's choice."""
        cfg = self._config.route_profiles.profiles
        balanced_cfg = cfg.get(RouteProfile.BALANCED.value)
        fewest_cfg = cfg.get(RouteProfile.FEWEST_MAPPED.value)
        balanced = user_limit or DetourLimit(float(balanced_cfg.max_extra_seconds if balanced_cfg and balanced_cfg.max_extra_seconds is not None else 600), float(balanced_cfg.max_relative_factor if balanced_cfg and balanced_cfg.max_relative_factor is not None else 1.5))
        fewest_default = DetourLimit(float(fewest_cfg.max_extra_seconds if fewest_cfg and fewest_cfg.max_extra_seconds is not None else 1200), float(fewest_cfg.max_relative_factor if fewest_cfg and fewest_cfg.max_relative_factor is not None else 1.75))
        fewest = DetourLimit(max(fewest_default.max_extra_s, balanced.max_extra_s), max(fewest_default.max_relative_factor, balanced.max_relative_factor))
        return {RouteProfile.BALANCED: balanced, RouteProfile.FEWEST_MAPPED: fewest}

    def plan(
        self,
        origin: LatLon,
        destination: LatLon,
        *,
        profiles: list[RouteProfile],
        camera_scope: CameraScope,
        snapshot_id: str | None = None,
        detour_limits: DetourLimit | None = None,
    ) -> PlanResult:
        started = self._clock()
        request_id = uuid.uuid4().hex
        boundary = self._config.service_boundary
        outside = [name for name, point in (("origin", origin), ("destination", destination)) if not boundary.contains(point.lat, point.lon)]
        if outside:
            raise AppError(OUTSIDE_SERVICE_AREA, "Trips must start and end inside the Denver pilot area.", details={"outside": outside, "service_boundary_id": boundary.boundary_id})
        if haversine_m((origin.lat, origin.lon), (destination.lat, destination.lon)) < MIN_TRIP_DISTANCE_M:
            raise AppError(VALIDATION_ERROR, "Start and destination are the same place. Choose two different points.", details={"min_distance_m": MIN_TRIP_DISTANCE_M})

        requested = [p for p in PROFILE_ORDER if p is RouteProfile.STANDARD or p in profiles]
        avoidance_profiles = [p for p in requested if p is not RouteProfile.STANDARD]
        limits = self._limits(detour_limits)
        budget = self._config.route_profiles.search_budget

        alternates = self._config.providers.routing.alternates
        candidates = dedupe(self._routing.baseline_candidates(origin, destination, alternates=alternates, request_id=request_id))
        calls_used = 1
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

        # Assess every valid baseline candidate over its whole path (Standard first so it is assessed even if time runs out).
        pool: dict[str, Candidate] = {}
        ordered = [standard, *[c for c in valid if c is not standard]]
        for route in ordered:
            assessment = self._assessor(route, camera_scope, snapshot_id) if self._assessor else None
            cand = candidate_from(route, assessment, "baseline")
            pool[cand.key] = cand
        standard_cand = pool[standard.encoded_shape_key()]
        assessment_available = standard_cand.assessment is not None and standard_cand.assessment.status != "not_assessed"
        if standard_cand.assessment is not None:
            warnings.extend(standard_cand.assessment.warnings)

        notes: list[str] = []
        status = SearchStatus.COMPLETED
        iterations = 0
        unavoidable: set[str] = set()
        if avoidance_profiles and not assessment_available:
            status = SearchStatus.NOT_RUN
            notes.append("Camera assessment is unavailable, so the camera-aware preferences were not evaluated; only the Standard route is shown, unassessed.")
            warnings.append("Camera-aware preferences could not be evaluated because the camera assessment is unavailable; the Standard route is shown unassessed.")
        elif avoidance_profiles and standard_cand.rankable and standard_cand.exposure == 0:
            notes.append("The Standard route has no mapped encounters in this assessment, so no avoidance search was needed.")
        elif avoidance_profiles:
            stop_bound = min(limits[p].bound_s(standard.duration_s) for p in avoidance_profiles)
            search = CandidateSearch(self._routing, self._assessor, budget=budget, avoidance=self._config.route_profiles.avoidance, clock=self._clock)
            outcome = search.run(
                origin, destination, request_id=request_id, alternates=alternates, scope=camera_scope, snapshot_id=snapshot_id,
                pool=pool, stop_bound_s=stop_bound, started_at=started, calls_used=calls_used,
            )
            status, calls_used, iterations, notes, unavoidable = outcome.status, outcome.routing_calls_used, outcome.iterations, outcome.notes, outcome.unavoidable_keys

        partial_candidates = sum(1 for c in pool.values() if c.assessment is not None and c.assessment.status == "partial")
        if partial_candidates:
            notes.append(f"{partial_candidates} candidate(s) leave the assessed data area and were not ranked; their counts would be incomplete.")

        outcomes = rank_profiles(pool, standard_cand.key, requested, limits, assessment_available=assessment_available)
        options = self._options(pool, standard_cand, outcomes, origin, destination)
        coverage = AssessmentCoverage.NOT_ASSESSED
        if standard_cand.assessment is not None and standard_cand.assessment.status == "complete":
            coverage = AssessmentCoverage.COMPLETE
        elif standard_cand.assessment is not None and standard_cand.assessment.status == "partial":
            coverage = AssessmentCoverage.PARTIAL
        assessed = sum(1 for c in pool.values() if c.exposure is not None)
        summary = SearchSummary(
            status=status,
            method_version=SEARCH_METHOD_VERSION,
            routing_calls_used=calls_used,
            routing_calls_budget=budget.max_routing_calls_per_trip,
            planning_deadline_s=float(budget.planning_deadline_seconds),
            elapsed_s=round(self._clock() - started, 3),
            candidates_generated=len(pool),
            candidates_assessed=assessed,
            iterations=iterations,
            notes=notes,
            profile_outcomes=outcomes,
        )
        return PlanResult(
            request_id=request_id,
            options=options,
            reference_duration_s=standard.duration_s,
            candidates_evaluated=len(pool),
            search_status=status.value,
            warnings=list(dict.fromkeys(warnings)),
            assessment_coverage_status=coverage,
            search=summary,
        )

    @staticmethod
    def _options(pool: dict[str, Candidate], standard: Candidate, outcomes: list[ProfileOutcome], origin: LatLon, destination: LatLon) -> list[PlannedOption]:
        """One option per distinct chosen geometry; preferences that resolve to the same path share one card."""
        labels: dict[str, list[RouteProfile]] = {standard.key: [RouteProfile.STANDARD]}
        bounds: dict[str, float | None] = {standard.key: None}
        for outcome in outcomes:
            if outcome.outcome is ProfileOutcomeKind.NOT_ASSESSED or outcome.route_key is None:
                continue
            profile = RouteProfile(outcome.profile)
            labels.setdefault(outcome.route_key, []).append(profile)
            if outcome.outcome is ProfileOutcomeKind.IMPROVED:
                bounds[outcome.route_key] = outcome.bound_s if bounds.get(outcome.route_key) is None else max(bounds[outcome.route_key], outcome.bound_s)
            else:
                bounds.setdefault(outcome.route_key, None)
        ordered_keys = [standard.key, *[k for k in labels if k != standard.key]]
        options: list[PlannedOption] = []
        for key in ordered_keys:
            cand = pool[key]
            origin_snap, destination_snap = snap_distances_m(cand.route, origin, destination)
            options.append(PlannedOption(
                route_id=uuid.uuid4().hex,
                profiles=[p for p in PROFILE_ORDER if p in labels[key]],
                route=cand.route,
                extra_duration_s=cand.route.duration_s - standard.route.duration_s,
                extra_distance_m=cand.route.length_m - standard.route.length_m,
                origin_snap_m=origin_snap,
                destination_snap_m=destination_snap,
                assessment=cand.assessment,
                exposure=cand.exposure,
                generated_by=cand.generated_by,
                detour_bound_s=bounds.get(key),
            ))
        return options
