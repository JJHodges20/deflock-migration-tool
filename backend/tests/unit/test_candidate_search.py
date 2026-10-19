"""M5 matrix on a synthetic road network (roadmap sections 10.3 to 10.5, 15 M5, 16).

Grid (metres): three east-west streets at y = 0 (Main Street, 100 s per 2 km block), y = 1000 (Park Avenue,
80 s per block) and y = 2000 (Ridge Road, 100 s per block), joined by 1st, 3rd and 5th Streets (60 s per
1 km). Trip A (0,0) -> C (4000,0). Standard = Main (200 s); Park = 280 s; Ridge = 440 s.
Balanced default bound = min(200 + 600, 1.5 x 200) = 300 s; Fewest default bound = min(1400, 350) = 350 s.
"""

from __future__ import annotations

import itertools

import pytest
from shapely.geometry import box

from deflockmigration.application.plan_trip import PlanTripService
from deflockmigration.domain.routes import CameraScope, DetourLimit, LatLon, RouteProfile
from deflockmigration.domain.search import ProfileOutcomeKind, SearchStatus
from deflockmigration.routing.candidates import validate_maneuvers
from tests.support.synthetic_graph import LAT0, LON0, SyntheticEngine, SyntheticGraph, camera, make_assessor, to_latlon

ALL = [RouteProfile.STANDARD, RouteProfile.BALANCED, RouteProfile.FEWEST_MAPPED]
ORIGIN = LatLon(*to_latlon(0, 0))
DESTINATION = LatLon(*to_latlon(4000, 0))


def grid(*, frontage: bool = False) -> SyntheticGraph:
    g = SyntheticGraph()
    for name, (x, y) in {"A": (0, 0), "B": (2000, 0), "C": (4000, 0), "D": (0, 1000), "E": (2000, 1000), "F": (4000, 1000), "G": (0, 2000), "H": (2000, 2000), "I": (4000, 2000)}.items():
        g.node(name, x, y)
    main, park, ridge = g.street(1, "Main Street"), g.street(2, "Park Avenue"), g.street(3, "Ridge Road")
    first, third, fifth = g.street(11, "1st Street"), g.street(12, "3rd Street"), g.street(13, "5th Street")
    g.connect("A", "B", 100, main)
    g.connect("B", "C", 100, main)
    g.connect("D", "E", 80, park)
    g.connect("E", "F", 80, park)
    g.connect("G", "H", 100, ridge)
    g.connect("H", "I", 100, ridge)
    g.connect("A", "D", 60, first)
    g.connect("D", "G", 60, first)
    g.connect("B", "E", 60, third)
    g.connect("E", "H", 60, third)
    g.connect("C", "F", 60, fifth)
    g.connect("F", "I", 60, fifth)
    if frontage:  # a parallel service road 30 m north of Main Street, not connected to the grid
        g.node("A2", 0, 30)
        g.node("B2", 2000, 30)
        g.connect("A2", "B2", 100, g.street(4, "Main Frontage Road"))
    return g


def plan(app_config, engine, records, *, profiles=ALL, limits=None, envelope=None, clock=None, assessor="synthetic", config=None):
    assess = make_assessor(engine, records, envelope) if assessor == "synthetic" else assessor
    service = PlanTripService(config or app_config, engine, assess, clock=clock or (lambda: 0.0))
    return service.plan(ORIGIN, DESTINATION, profiles=profiles, camera_scope=CameraScope.ALL_ALPR, snapshot_id="syn-1", detour_limits=limits)


def outcomes_of(result):
    return {o.profile: o for o in result.search.profile_outcomes}


def test_lower_exposure_detour_is_found_and_shared_by_both_preferences(app_config):
    engine = SyntheticEngine(grid())
    result = plan(app_config, engine, [camera("osm:node:1", 1000, 5)])
    assert [o.profiles for o in result.options] == [[RouteProfile.STANDARD], [RouteProfile.BALANCED, RouteProfile.FEWEST_MAPPED]]
    standard, park = result.options
    assert standard.exposure == 1 and standard.assessment.matched_record_count == 1 and standard.route.duration_s == 200
    assert park.exposure == 0 and park.route.duration_s == 280 and park.extra_duration_s == 80 and park.generated_by == "penalized@10"
    assert park.assessment.status == "complete" and not validate_maneuvers(park.route)
    assert result.search.status is SearchStatus.COMPLETED and result.search.routing_calls_used == 2 and result.search.iterations == 1
    assert outcomes_of(result)["balanced"].outcome is ProfileOutcomeKind.IMPROVED and outcomes_of(result)["fewest_mapped"].outcome is ProfileOutcomeKind.IMPROVED
    assert park.detour_bound_s == 350  # the looser of the two limits that chose it
    # The penalized request carried the camera's road segment, and the engine applied it to Main Street.
    assert engine.calls[1]["kind"] == "penalized" and engine.calls[1]["factors"]


def test_longer_unchanged_exposure_detour_is_not_a_benefit_and_over_budget_candidate_is_rejected(app_config):
    engine = SyntheticEngine(grid())
    records = [camera("osm:node:1", 1000, 5), camera("osm:node:2", 1000, 1005)]
    result = plan(app_config, engine, records)
    assert len(result.options) == 1 and result.options[0].profiles == ALL  # one card, three labels
    outcomes = outcomes_of(result)
    for profile in ("balanced", "fewest_mapped"):
        assert outcomes[profile].outcome is ProfileOutcomeKind.SAME_AS_STANDARD
        assert "No lower-exposure route found within your detour limit" in outcomes[profile].message
    # Park (same exposure, slower) and the zig-zag over Ridge Road (zero exposure, 420 s > 350 s) were both generated,
    # fully assessed, and rejected: the first is no benefit, the second is over budget.
    assert result.search.candidates_assessed == 3 and result.search.status is SearchStatus.COMPLETED
    generated = {tuple(r["nodes"]): r["physical_s"] for call in engine.calls for r in call["routes"]}
    assert generated[("A", "D", "E", "F", "C")] == 280 and generated[("A", "D", "G", "H", "E", "F", "C")] == 420
    assert outcomes["fewest_mapped"].bound_s == 350 < 420


def test_raising_the_detour_limit_admits_the_zero_exposure_candidate(app_config):
    engine = SyntheticEngine(grid())
    records = [camera("osm:node:1", 1000, 5), camera("osm:node:2", 1000, 1005)]
    result = plan(app_config, engine, records, limits=DetourLimit(300, 3.0))
    assert [o.profiles for o in result.options] == [[RouteProfile.STANDARD], [RouteProfile.BALANCED, RouteProfile.FEWEST_MAPPED]]
    detour = result.options[1]
    assert detour.exposure == 0 and detour.route.duration_s == 420 and detour.extra_duration_s == 220 and detour.generated_by == "penalized@40"
    outcomes = outcomes_of(result)
    assert outcomes["balanced"].bound_s == 500  # min(200 + 300, 3.0 x 200)
    assert outcomes["fewest_mapped"].bound_s == 600  # never tighter than the user's choice: min(200 + 1200, 3.0 x 200)


def test_repeated_requests_are_deterministic_on_a_fixed_snapshot(app_config):
    def run():
        engine = SyntheticEngine(grid())
        result = plan(app_config, engine, [camera("osm:node:1", 1000, 5), camera("osm:node:2", 1000, 1005)], limits=DetourLimit(300, 3.0))
        return (
            [(tuple(o.profiles), o.route.encoded_shape_key(), o.exposure, o.route.duration_s, o.generated_by) for o in result.options],
            (result.search.status, result.search.routing_calls_used, result.search.iterations, result.search.candidates_assessed, tuple(result.search.notes)),
            [(o.profile, o.outcome, o.route_key, o.message) for o in result.search.profile_outcomes],
            [call["kind"] for call in engine.calls],
        )

    assert run() == run()


def test_record_at_the_destination_is_unavoidable_and_never_excluded(app_config):
    engine = SyntheticEngine(grid())
    result = plan(app_config, engine, [camera("osm:node:9", 4000, 0)])
    assert len(result.options) == 1 and result.options[0].profiles == ALL
    assert result.options[0].exposure == 1  # ambiguous between Main Street and 5th Street at the node: counted as uncertain
    assert result.search.routing_calls_used == 1 and [c["kind"] for c in engine.calls] == ["baseline"]
    assert any("cannot be avoided by any route" in note for note in result.search.notes)
    assert all(o.outcome is ProfileOutcomeKind.SAME_AS_STANDARD for o in result.search.profile_outcomes)


def test_engine_refusing_exclusions_is_handled_and_penalties_never_change_reported_time(app_config):
    engine = SyntheticEngine(grid(), fail_exclusions=True)
    records = [camera("osm:node:1", 1000, 5), camera("osm:node:2", 1000, 1005), camera("osm:node:3", 1000, 2005)]
    result = plan(app_config, engine, records)
    assert len(result.options) == 1 and result.options[0].route.duration_s == 200
    assert result.search.status is SearchStatus.COMPLETED
    kinds = [c["kind"] for c in engine.calls]
    assert kinds == ["baseline", "penalized", "penalized", "penalized", "excluded"]
    assert any("hard-exclusion request found no drivable route" in note for note in result.search.notes)
    assert any("converged" in note for note in result.search.notes)
    # ETA integrity: the engine's penalized cost exceeded the physical time on penalized routes, yet every
    # duration the planner reports is the physical time.
    def physical(nodes: list[str]) -> float:
        return sum(next(e.time_s for e in engine.graph.edges if e.a == a and e.b == b) for a, b in zip(nodes, nodes[1:]))

    penalized = [r for call in engine.calls for r in call["routes"] if call["kind"] == "penalized"]
    assert penalized and any(r["penalized_cost"] > r["physical_s"] for r in penalized)
    assert all(r["physical_s"] == physical(r["nodes"]) for r in penalized)
    assert result.options[0].route.duration_s == 200.0 == physical(["A", "B", "C"])


def test_no_silent_profile_degradation_without_assessment(app_config):
    engine = SyntheticEngine(grid())
    result = plan(app_config, engine, [], assessor=None)
    assert len(result.options) == 1 and result.options[0].profiles == [RouteProfile.STANDARD]  # no camera-aware label without evidence
    assert result.search.status is SearchStatus.NOT_RUN and result.search.routing_calls_used == 1
    outcomes = outcomes_of(result)
    assert {o.outcome for o in outcomes.values()} == {ProfileOutcomeKind.NOT_ASSESSED} and set(outcomes) == {"balanced", "fewest_mapped"}
    assert any("could not be evaluated" in w for w in result.warnings)
    assert result.options[0].exposure is None and result.options[0].assessment is None


def test_standard_without_mapped_encounters_needs_no_search(app_config):
    engine = SyntheticEngine(grid())
    result = plan(app_config, engine, [camera("osm:node:5", 1000, 2005)])  # only on Ridge Road
    assert len(result.options) == 1 and result.options[0].profiles == ALL and result.options[0].exposure == 0
    assert result.search.routing_calls_used == 1 and result.search.status is SearchStatus.COMPLETED
    assert all("nothing to avoid" in o.message for o in result.search.profile_outcomes)


def test_baseline_alternates_are_assessed_and_ranked_without_extra_calls(app_config):
    engine = SyntheticEngine(grid(), alternates_mode="yen")
    result = plan(app_config, engine, [camera("osm:node:1", 1000, 5)])
    assert result.search.routing_calls_used == 1 and len(engine.calls[0]["routes"]) == 3
    assert [o.profiles for o in result.options] == [[RouteProfile.STANDARD], [RouteProfile.BALANCED, RouteProfile.FEWEST_MAPPED]]
    assert result.options[1].route.duration_s == 280 and result.options[1].generated_by == "baseline"


def test_budget_exhaustion_is_disclosed(app_config):
    from deflockmigration.core.config_loader import SearchBudgetConfig

    budget = SearchBudgetConfig(max_routing_calls_per_trip=2, planning_deadline_seconds=app_config.route_profiles.search_budget.planning_deadline_seconds)
    config = app_config.model_copy(update={"route_profiles": app_config.route_profiles.model_copy(update={"search_budget": budget})})
    engine = SyntheticEngine(grid())
    result = plan(app_config, engine, [camera("osm:node:1", 1000, 5), camera("osm:node:2", 1000, 1005)], config=config)
    assert result.search.status is SearchStatus.BUDGET_EXHAUSTED and result.search.routing_calls_used == 2 and result.search.routing_calls_budget == 2
    assert any("budget" in note for note in result.search.notes)
    assert len(result.options) == 1 and result.options[0].profiles == ALL


def test_deadline_cuts_the_search_short_with_a_partial_label(app_config):
    ticks = itertools.count(0, 30)
    engine = SyntheticEngine(grid())
    result = plan(app_config, engine, [camera("osm:node:1", 1000, 5)], clock=lambda: float(next(ticks)))
    assert result.search.status is SearchStatus.PARTIAL and result.search.routing_calls_used == 1
    assert any("planning deadline" in note for note in result.search.notes)
    assert len(result.options) == 1 and result.options[0].profiles == ALL


def test_candidates_leaving_the_envelope_are_not_ranked(app_config):
    envelope = box(LON0 - 0.01, LAT0 - 0.001, LON0 + 0.06, to_latlon(0, 1500)[0])  # Main and Park inside, Ridge outside
    engine = SyntheticEngine(grid())
    result = plan(app_config, engine, [camera("osm:node:1", 1000, 5), camera("osm:node:2", 1000, 1005)], limits=DetourLimit(300, 3.0), envelope=envelope)
    assert len(result.options) == 1 and result.options[0].profiles == ALL
    assert any("leave the assessed data area and were not ranked" in note for note in result.search.notes)
    assert all(o.outcome is ProfileOutcomeKind.SAME_AS_STANDARD for o in result.search.profile_outcomes)


def test_frontage_road_camera_counts_as_uncertain_not_matched(app_config):
    engine = SyntheticEngine(grid(frontage=True))
    result = plan(app_config, engine, [camera("osm:node:7", 1000, 20)])
    standard, park = result.options
    assert standard.assessment.matched_record_count == 0 and standard.assessment.uncertain_record_count == 1 and standard.exposure == 1
    assert standard.assessment.encounters[0].status.value == "nearby_unresolved"
    assert park.exposure == 0 and park.profiles == [RouteProfile.BALANCED, RouteProfile.FEWEST_MAPPED]


def test_only_standard_requested_makes_no_avoidance_calls(app_config):
    engine = SyntheticEngine(grid())
    result = plan(app_config, engine, [camera("osm:node:1", 1000, 5)], profiles=[RouteProfile.STANDARD])
    assert len(result.options) == 1 and result.search.routing_calls_used == 1 and result.search.profile_outcomes == []
    assert result.search.status is SearchStatus.COMPLETED


@pytest.mark.parametrize("profiles", [[RouteProfile.BALANCED], [RouteProfile.FEWEST_MAPPED, RouteProfile.STANDARD]])
def test_standard_is_always_included_and_ordered_first(app_config, profiles):
    engine = SyntheticEngine(grid())
    result = plan(app_config, engine, [camera("osm:node:1", 1000, 5)], profiles=profiles)
    assert result.options[0].profiles == [RouteProfile.STANDARD]
    assert len(result.options) == 2 and result.options[1].profiles == [p for p in ALL if p in profiles and p is not RouteProfile.STANDARD]
