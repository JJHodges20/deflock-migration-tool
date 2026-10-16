"""Candidate handling that is independent of the engine.

Decision 0001 D6: the Standard route is the fastest baseline candidate by reported time, because
the engine's primary result minimises an internal cost that its reported time does not include.
"""

from __future__ import annotations

from deflockmigration.domain.routes import EngineRoute


def dedupe(candidates: list[EngineRoute]) -> list[EngineRoute]:
    seen: set[str] = set()
    unique: list[EngineRoute] = []
    for candidate in candidates:
        key = candidate.encoded_shape_key()
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def choose_standard(candidates: list[EngineRoute]) -> EngineRoute:
    if not candidates:
        raise ValueError("no candidates")
    return min(candidates, key=lambda r: (r.duration_s, r.length_m, 0 if r.source == "primary" else 1))


def validate_maneuvers(route: EngineRoute) -> list[str]:
    """Return problems that would make directions untrustworthy; empty means valid."""
    problems: list[str] = []
    if not route.maneuvers:
        problems.append("no maneuvers")
        return problems
    last = -1
    for index, maneuver in enumerate(route.maneuvers):
        if not maneuver.instruction.strip():
            problems.append(f"maneuver {index} has no instruction")
        if maneuver.begin_shape_index < last:
            problems.append(f"maneuver {index} shape index decreases")
        last = maneuver.begin_shape_index
    if route.maneuvers[0].type not in (1, 2, 3):
        problems.append("first maneuver is not a start")
    if route.maneuvers[-1].type not in (4, 5, 6):
        problems.append("last maneuver is not a destination")
    if len(route.shape) < 2:
        problems.append("shape has fewer than two points")
    return problems
