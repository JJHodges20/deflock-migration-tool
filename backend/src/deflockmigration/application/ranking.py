"""Deterministic ranking of assessed candidates per route preference (roadmap section 10.4).

For each avoidance profile: among fully assessed candidates with T(r) <= min(T0 + max_extra, factor * T0),
minimise exposure (matched plus uncertain records), then duration, then distance, then a geometry key.
The outcome is explicit: an improvement, "same as Standard" (nothing to avoid, or nothing better within the
limit), or "not assessed". Ties never favour a longer route, so a longer route with unchanged exposure is
never presented as a benefit.
"""

from __future__ import annotations

from deflockmigration.application.candidate_search import Candidate
from deflockmigration.domain.routes import DetourLimit, RouteProfile
from deflockmigration.domain.search import ProfileOutcome, ProfileOutcomeKind


def _limit_text(limit: DetourLimit, bound_s: float) -> str:
    minutes = limit.max_extra_s / 60.0
    return f"up to {minutes:g} min extra or {limit.max_relative_factor:.2f} x the Standard time, whichever is smaller ({bound_s:.0f} s for this trip)"


def rank_profiles(
    pool: dict[str, Candidate],
    standard_key: str,
    requested: list[RouteProfile],
    limits: dict[RouteProfile, DetourLimit],
    *,
    assessment_available: bool,
) -> list[ProfileOutcome]:
    standard = pool[standard_key]
    reference_s = standard.route.duration_s
    outcomes: list[ProfileOutcome] = []
    for profile in requested:
        if profile is RouteProfile.STANDARD:
            continue
        limit = limits[profile]
        bound_s = limit.bound_s(reference_s)
        common = dict(profile=profile.value, max_extra_s=limit.max_extra_s, max_relative_factor=limit.max_relative_factor, bound_s=bound_s)
        if not assessment_available or standard.exposure is None:
            outcomes.append(ProfileOutcome(**common, outcome=ProfileOutcomeKind.NOT_ASSESSED, best_exposure=None, route_key=None,
                                           message="Camera assessment is unavailable, so this preference could not be evaluated; only the Standard route is shown, unassessed."))
            continue
        if standard.rankable and standard.exposure == 0:
            outcomes.append(ProfileOutcome(**common, outcome=ProfileOutcomeKind.SAME_AS_STANDARD, best_exposure=0, route_key=standard_key,
                                           message="The Standard route already has no mapped encounters in this assessment; there is nothing to avoid."))
            continue
        feasible = [c for c in pool.values() if c.rankable and c.route.duration_s <= bound_s]
        assessed = sum(1 for c in pool.values() if c.exposure is not None)
        best = min(feasible, key=lambda c: (c.exposure, c.route.duration_s, c.route.length_m, c.key)) if feasible else None
        if best is None or best.key == standard_key or best.exposure >= standard.exposure:
            if not standard.rankable:
                message = ("The Standard route leaves the assessed data area, so its count is incomplete; no fully assessed candidate within the limit "
                           f"({_limit_text(limit, bound_s)}) has fewer mapped encounters than the part of the Standard route that was assessed.")
            else:
                message = (f"No lower-exposure route found within your detour limit ({_limit_text(limit, bound_s)}); {assessed} candidate(s) were assessed. "
                           "Increase the limit to search further.")
            outcomes.append(ProfileOutcome(**common, outcome=ProfileOutcomeKind.SAME_AS_STANDARD, best_exposure=standard.exposure, route_key=standard_key, message=message))
            continue
        extra = best.route.duration_s - reference_s
        qualifier = "" if standard.rankable else " (the Standard count is incomplete because that route leaves the assessed area)"
        outcomes.append(ProfileOutcome(
            **common, outcome=ProfileOutcomeKind.IMPROVED, best_exposure=best.exposure, route_key=best.key,
            message=(f"{best.exposure} mapped encounter(s), matched plus uncertain, versus {standard.exposure} on the Standard route{qualifier}; "
                     f"{extra:+.0f} s, within the limit ({_limit_text(limit, bound_s)})."),
        ))
    return outcomes
