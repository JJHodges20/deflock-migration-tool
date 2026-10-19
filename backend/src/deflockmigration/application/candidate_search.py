"""Bounded camera-aware candidate search (roadmap section 10.3; decision 0001 D5).

The engine does all path finding; this module only decides what to ask it and keeps the book-keeping honest:

- every candidate is assessed over its entire path against the whole camera envelope;
- artificial penalties steer the engine's search and never touch reported travel time;
- the routing-call budget and the planning deadline are enforced, and the outcome says whether the search
  completed, ran out of budget, or was cut short;
- the request sequence is deterministic for a fixed snapshot and graph: penalized requests with an escalating
  factor (10, 40, 160 by default), one hard-exclusion request, then penalized requests at the maximum factor
  while new candidates keep appearing. Targets accumulate from every assessed candidate, so the search learns
  the cameras along the corridor rather than only those on the first route.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from deflockmigration.core.config_loader import AvoidanceConfig, SearchBudgetConfig
from deflockmigration.core.errors import NO_DRIVABLE_ROUTE, AppError
from deflockmigration.domain.assessment import AssessmentResult, EncounterStatus
from deflockmigration.domain.routes import AvoidanceRequest, CameraScope, EngineRoute, LatLon, PenaltySegment
from deflockmigration.domain.search import SearchStatus
from deflockmigration.geospatial.metric import cumulative_lengths_m
from deflockmigration.routing.candidates import dedupe, validate_maneuvers
from deflockmigration.routing.provider import RoutingProvider

log = logging.getLogger(__name__)
Assessor = Callable[[EngineRoute, CameraScope, str | None], AssessmentResult]
# Statuses that count towards a route's exposure: matched plus every unresolved kind (roadmap 10.4, conservative).
COUNTED_STATUSES = {EncounterStatus.ASSOCIATED, EncounterStatus.NEARBY_UNRESOLVED, EncounterStatus.NO_LONGER_MAPPED, EncounterStatus.OUTSIDE_ENVELOPE}


@dataclass
class Candidate:
    route: EngineRoute
    assessment: AssessmentResult | None
    generated_by: str  # baseline | penalized@<factor> | excluded
    key: str

    @property
    def exposure(self) -> int | None:
        """Matched plus uncertain records, each record once; None when the route was not assessed."""
        a = self.assessment
        if a is None or a.status == "not_assessed" or a.matched_record_count is None:
            return None
        return a.matched_record_count + (a.uncertain_record_count or 0)

    @property
    def rankable(self) -> bool:
        """Only routes assessed over their whole path inside the envelope take part in privacy ranking (decision 0001 D2)."""
        return self.assessment is not None and self.assessment.status == "complete"


@dataclass
class SearchOutcome:
    status: SearchStatus
    routing_calls_used: int
    iterations: int
    candidates_generated: int
    notes: list[str] = field(default_factory=list)
    unavoidable_keys: set[str] = field(default_factory=set)


def candidate_from(route: EngineRoute, assessment: AssessmentResult | None, generated_by: str) -> Candidate:
    return Candidate(route=route, assessment=assessment, generated_by=generated_by, key=route.encoded_shape_key())


class CandidateSearch:
    def __init__(
        self,
        routing: RoutingProvider,
        assessor: Assessor,
        *,
        budget: SearchBudgetConfig,
        avoidance: AvoidanceConfig,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._routing = routing
        self._assess = assessor
        self._budget = budget
        self._cfg = avoidance
        self._clock = clock

    # ----- public -------------------------------------------------------------------------------------------

    def run(
        self,
        origin: LatLon,
        destination: LatLon,
        *,
        request_id: str,
        alternates: int,
        scope: CameraScope,
        snapshot_id: str | None,
        pool: dict[str, Candidate],
        stop_bound_s: float | None,
        started_at: float,
        calls_used: int,
    ) -> SearchOutcome:
        """Extend `pool` in place with assessed avoidance candidates. `stop_bound_s` is the tightest requested detour
        bound: once a fully assessed candidate with zero exposure exists within it, nothing better can be found."""
        out = SearchOutcome(status=SearchStatus.COMPLETED, routing_calls_used=calls_used, iterations=0, candidates_generated=len(pool))
        generated_keys: set[str] = set(pool)
        factor = float(self._cfg.penalty_factor)
        stage = "penalize"
        exclusions_done = False
        last_call_found_new = False
        invalid_dropped = 0
        unassessed = 0

        while True:
            if stop_bound_s is not None and self._zero_within(pool, stop_bound_s):
                out.notes.append("A fully assessed candidate with no mapped encounters exists within the detour limit; the search stopped early.")
                break
            targets, unavoidable = self._targets(pool)
            out.unavoidable_keys = unavoidable
            if not targets:
                if unavoidable:
                    out.notes.append(f"{len(unavoidable)} mapped record(s) within {self._cfg.endpoint_margin_m:.0f} m of the start or destination cannot be avoided by any route and were not targeted.")
                break
            if out.routing_calls_used >= self._budget.max_routing_calls_per_trip:
                if last_call_found_new:
                    out.status = SearchStatus.BUDGET_EXHAUSTED
                    out.notes.append(f"The routing-call budget ({self._budget.max_routing_calls_per_trip}) ran out while new candidates were still appearing; a larger budget might find more.")
                break
            if self._deadline_passed(started_at):
                out.status = SearchStatus.PARTIAL
                out.notes.append(f"The planning deadline ({self._budget.planning_deadline_seconds} s) was reached after {out.routing_calls_used} routing calls; results come from the candidates assessed so far.")
                break

            if stage == "penalize":
                request = AvoidanceRequest("penalized", penalties=[PenaltySegment(points, factor, keys) for points, keys in targets])
                label = f"penalized@{factor:g}"
            else:
                points = self._exclusion_points(pool)
                if not points:
                    exclusions_done = True
                    stage = "penalize"
                    continue
                request = AvoidanceRequest("excluded", exclusions=points[: self._cfg.max_exclusions_per_request])
                label = "excluded"

            out.iterations += 1
            out.routing_calls_used += 1
            try:
                routes = self._routing.avoiding_candidates(origin, destination, alternates=alternates, request_id=f"{request_id}-{out.iterations}", avoidance=request)
            except AppError as exc:
                if exc.code == NO_DRIVABLE_ROUTE and request.kind == "excluded":
                    out.notes.append("The hard-exclusion request found no drivable route (the selected endpoints or their access roads would be excluded); exclusions were not applied.")
                    out.notes.append("The search converged: the strongest penalties produced no new candidate and hard exclusions were infeasible.")
                    break
                out.status = SearchStatus.PARTIAL
                out.notes.append(f"The routing engine failed during the search ({exc.code}); results come from the candidates assessed so far.")
                break

            new_count, dropped, skipped = self._absorb(routes, pool, generated_keys, label, out.iterations, scope, snapshot_id, started_at)
            invalid_dropped += dropped
            unassessed += skipped
            out.candidates_generated = len(generated_keys)
            last_call_found_new = new_count > 0

            if stage == "penalize":
                if factor < self._cfg.penalty_factor_max:
                    factor = min(factor * self._cfg.penalty_escalation, float(self._cfg.penalty_factor_max))
                elif not exclusions_done:
                    stage = "exclude"
                elif not last_call_found_new:
                    out.notes.append("The search converged: the last penalized request produced no new candidate.")
                    break
            else:
                exclusions_done = True
                stage = "penalize"
                if not last_call_found_new:
                    out.notes.append("The search converged: neither the strongest penalties nor hard exclusions produced a new candidate.")
                    break

        if invalid_dropped:
            out.notes.append(f"{invalid_dropped} engine result(s) were dropped because their directions failed validation.")
        if unassessed:
            out.status = SearchStatus.PARTIAL
            out.notes.append(f"{unassessed} candidate(s) could not be assessed before the deadline and were not ranked.")
        return out

    # ----- internals ----------------------------------------------------------------------------------------

    def _deadline_passed(self, started_at: float) -> bool:
        return self._clock() - started_at >= self._budget.planning_deadline_seconds

    @staticmethod
    def _zero_within(pool: dict[str, Candidate], bound_s: float) -> bool:
        return any(c.rankable and c.exposure == 0 and c.route.duration_s <= bound_s for c in pool.values())

    def _absorb(self, routes: list[EngineRoute], pool: dict[str, Candidate], generated: set[str], label: str, iteration: int, scope: CameraScope, snapshot_id: str | None, started_at: float) -> tuple[int, int, int]:
        """Dedupe, validate, and fully assess new engine results. Returns (new candidates, invalid dropped, unassessed)."""
        new = dropped = skipped = 0
        for route in dedupe(routes):
            key = route.encoded_shape_key()
            if key in generated:
                continue
            generated.add(key)
            if validate_maneuvers(route):
                dropped += 1
                continue
            route = replace(route, engine_route_id=f"{label}/{iteration}/{route.engine_route_id}")
            if self._deadline_passed(started_at):
                skipped += 1
                pool[key] = Candidate(route=route, assessment=None, generated_by=label, key=key)
                continue
            assessment = self._assess(route, scope, snapshot_id)
            pool[key] = Candidate(route=route, assessment=assessment, generated_by=label, key=key)
            new += 1
        return new, dropped, skipped

    def _targets(self, pool: dict[str, Candidate]) -> tuple[list[tuple[list[tuple[float, float]], tuple[str, ...]]], set[str]]:
        """Short route segments around every counted encounter of every assessed candidate, plus the records that
        sit too close to the start or destination to be avoided by any route."""
        segments: dict[tuple, tuple[list[tuple[float, float]], set[str]]] = {}
        unavoidable: set[str] = set()
        margin = self._cfg.endpoint_margin_m
        for cand in sorted(pool.values(), key=lambda c: c.key):
            a = cand.assessment
            if a is None or a.status == "not_assessed":
                continue
            cumulative = cumulative_lengths_m(cand.route.shape)
            total = cumulative[-1] if cumulative else 0.0
            for e in a.encounters:
                if e.status not in COUNTED_STATUSES or e.position_m is None:
                    continue
                if e.position_m < margin or total - e.position_m < margin:
                    unavoidable.add(e.source_key)
                    continue
                points = self._segment_points(cand.route.shape, cumulative, e.position_m)
                seg_key = tuple(round(v, 5) for p in points for v in p)
                entry = segments.setdefault(seg_key, (points, set()))
                entry[1].add(e.source_key)
        targets = [(points, tuple(sorted(keys))) for points, keys in segments.values()]
        targets.sort(key=lambda t: (t[1], t[0][0]))
        return targets, unavoidable

    def _segment_points(self, shape: list[tuple[float, float]], cumulative: list[float], position_m: float) -> list[tuple[float, float]]:
        half = self._cfg.penalty_segment_half_length_m
        indices = [i for i, d in enumerate(cumulative) if position_m - half <= d <= position_m + half]
        if len(indices) < 2:
            nearest = min(range(len(cumulative)), key=lambda i: abs(cumulative[i] - position_m))
            indices = sorted({max(0, nearest - 1), nearest, min(len(shape) - 1, nearest + 1)})
        points = [shape[i] for i in indices]
        if len(points) < 2:  # a two-point shape collapses only when the route itself is degenerate
            points = list(shape[:2])
        return points

    def _exclusion_points(self, pool: dict[str, Candidate]) -> list[LatLon]:
        """Hard exclusions target the counted encounters of the current best fully assessed candidate, never
        anything within the endpoint margin (so the start and destination roads are never excluded)."""
        rankable = [c for c in pool.values() if c.rankable]
        if not rankable:
            return []
        best = min(rankable, key=lambda c: (c.exposure, c.route.duration_s, c.route.length_m, c.key))
        cumulative = cumulative_lengths_m(best.route.shape)
        total = cumulative[-1] if cumulative else 0.0
        margin = self._cfg.endpoint_margin_m
        points: list[LatLon] = []
        seen: set[tuple[float, float]] = set()
        for e in sorted(best.assessment.encounters, key=lambda e: (e.position_m if e.position_m is not None else float("inf"), e.source_key)):
            if e.status not in COUNTED_STATUSES or e.position_m is None or e.position_m < margin or total - e.position_m < margin:
                continue
            nearest = min(range(len(cumulative)), key=lambda i: abs(cumulative[i] - e.position_m))
            lat, lon = best.route.shape[nearest]
            if (lat, lon) in seen:
                continue
            seen.add((lat, lon))
            points.append(LatLon(lat, lon))
        return points
