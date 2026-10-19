"""Results of the bounded camera-aware candidate search (roadmap sections 10.3 to 10.5).

A result is always "best among the candidates this search evaluated", never a proof of a globally optimal
camera-minimum path. The exposure of a route is its matched plus uncertain record count (each record once).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

SEARCH_METHOD_VERSION = "search-1.0"


class SearchStatus(StrEnum):
    COMPLETED = "completed"              # converged, or nothing to search for
    BUDGET_EXHAUSTED = "budget_exhausted"  # the routing-call budget ran out while new candidates were still appearing
    PARTIAL = "partial"                  # the planning deadline or an engine failure cut the search short
    NOT_RUN = "not_run"                  # camera assessment unavailable, so avoidance preferences could not be evaluated


class ProfileOutcomeKind(StrEnum):
    IMPROVED = "improved"                  # a fully assessed candidate within the limit has lower exposure; shown as an option
    SAME_AS_STANDARD = "same_as_standard"  # the Standard route is the best choice within the limit (or already has nothing to avoid)
    NOT_ASSESSED = "not_assessed"          # camera assessment unavailable; the preference could not be evaluated


@dataclass(frozen=True)
class ProfileOutcome:
    profile: str
    outcome: ProfileOutcomeKind
    message: str
    max_extra_s: float | None
    max_relative_factor: float | None
    bound_s: float | None
    best_exposure: int | None
    route_key: str | None  # geometry key of the chosen candidate when improved


@dataclass(frozen=True)
class SearchSummary:
    status: SearchStatus
    method_version: str
    routing_calls_used: int
    routing_calls_budget: int
    planning_deadline_s: float
    elapsed_s: float
    candidates_generated: int   # unique routes the engine returned across all calls, valid or not
    candidates_assessed: int    # unique valid routes assessed over their whole path
    iterations: int             # avoidance requests made
    notes: list[str] = field(default_factory=list)
    profile_outcomes: list[ProfileOutcome] = field(default_factory=list)
