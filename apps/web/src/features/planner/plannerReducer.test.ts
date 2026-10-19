import type { GeocodeCandidate, PlanResponse } from "@/lib/api/types";
import { canPlan, initialPlannerState, plannerReducer, selectedRoute } from "./plannerReducer";

const unionStation: GeocodeCandidate = { label: "Union Station", lat: 39.753, lon: -105.0002, source: "nominatim_local", category: "railway", importance: 0.5, inside_service_boundary: true };
const zoo: GeocodeCandidate = { label: "Denver Zoo", lat: 39.7503, lon: -104.95, source: "nominatim_local", category: "tourism", importance: 0.5, inside_service_boundary: true };

function fakeResult(id = "r1"): PlanResponse {
  return {
    request_id: "req",
    region_id: "denver",
    reference_duration_seconds: 618,
    candidates_evaluated: 3,
    search_status: "completed",
    assessment_coverage_status: "not_assessed",
    warnings: [],
    disclaimer: "advisory",
    search: { status: "completed", method_version: "search-1.0", routing_calls_used: 1, routing_calls_budget: 8, planning_deadline_seconds: 20, elapsed_seconds: 0.2, candidates_generated: 3, candidates_assessed: 0, iterations: 0, notes: [], profile_outcomes: [], meaning: "best among evaluated" },
    options: [
      {
        route_id: id,
        profiles: ["standard"],
        geometry: { type: "LineString", coordinates: [[-105.0002, 39.753], [-104.95, 39.7503]] },
        estimated_duration_seconds: 618,
        length_meters: 6423,
        extra_duration_seconds: 0,
        extra_distance_meters: 0,
        origin_snap_distance_meters: 12.5,
        destination_snap_distance_meters: 80.0,
        matched_camera_record_count: null,
        uncertain_nearby_camera_count: null,
        exposure_count: null,
        generated_by: "baseline",
        detour_bound_seconds: null,
        counting_method_version: null,
        camera_scope: "all_alpr",
        camera_snapshot_id: null,
        camera_source_as_of: null,
        camera_downloaded_at: null,
        road_graph_version: "colorado",
        assessment_coverage_status: "not_assessed",
        search_status: "completed",
        warnings: [],
        maneuvers: [],
        has_highway: false,
        has_toll: false,
        engine_candidate: "alternate-2",
        assessment: null,
      },
    ],
  };
}

describe("plannerReducer", () => {
  it("requires both confirmed endpoints before planning", () => {
    let state = initialPlannerState;
    expect(canPlan(state)).toBe(false);
    state = plannerReducer(state, { type: "CONFIRM_CANDIDATE", endpoint: "origin", candidate: unionStation });
    expect(canPlan(state)).toBe(false);
    state = plannerReducer(state, { type: "CONFIRM_CANDIDATE", endpoint: "destination", candidate: zoo });
    expect(canPlan(state)).toBe(true);
    expect(state.origin.text).toBe("Union Station");
  });

  it("swaps endpoints and invalidates a displayed result", () => {
    let state = plannerReducer(initialPlannerState, { type: "CONFIRM_CANDIDATE", endpoint: "origin", candidate: unionStation });
    state = plannerReducer(state, { type: "CONFIRM_CANDIDATE", endpoint: "destination", candidate: zoo });
    state = plannerReducer(state, { type: "PLAN_START" });
    state = plannerReducer(state, { type: "PLAN_SUCCESS", sequence: state.request.sequence, result: fakeResult() });
    expect(selectedRoute(state)?.route_id).toBe("r1");
    state = plannerReducer(state, { type: "SWAP" });
    expect(state.origin.confirmed?.label).toBe("Denver Zoo");
    expect(state.destination.confirmed?.label).toBe("Union Station");
    expect(state.result).toBeNull();
  });

  it("discards late responses from superseded requests", () => {
    let state = plannerReducer(initialPlannerState, { type: "PLAN_START" });
    const first = state.request.sequence;
    state = plannerReducer(state, { type: "PLAN_START" });
    state = plannerReducer(state, { type: "PLAN_SUCCESS", sequence: first, result: fakeResult("late") });
    expect(state.result).toBeNull();
    expect(state.request.status).toBe("loading");
    state = plannerReducer(state, { type: "PLAN_SUCCESS", sequence: state.request.sequence, result: fakeResult("current") });
    expect(state.result?.options[0].route_id).toBe("current");
  });

  it("cancelling a request is an explicit state and ignores its eventual result", () => {
    let state = plannerReducer(initialPlannerState, { type: "PLAN_START" });
    const seq = state.request.sequence;
    state = plannerReducer(state, { type: "PLAN_CANCEL" });
    expect(state.request.status).toBe("cancelled");
    state = plannerReducer(state, { type: "PLAN_SUCCESS", sequence: seq, result: fakeResult() });
    expect(state.result).toBeNull();
  });

  it("places a map pin only while pin mode is active", () => {
    let state = plannerReducer(initialPlannerState, { type: "PIN_PLACED", lat: 39.7, lon: -104.9 });
    expect(state.origin.confirmed).toBeNull();
    state = plannerReducer(state, { type: "SET_PIN_MODE", endpoint: "destination" });
    state = plannerReducer(state, { type: "PIN_PLACED", lat: 39.7, lon: -104.9 });
    expect(state.destination.confirmed?.source).toBe("map_pin");
    expect(state.pinMode).toBeNull();
  });

  it("clear trip keeps preferences but drops endpoints, results, and errors", () => {
    let state = plannerReducer(initialPlannerState, { type: "SET_SCOPE", scope: "flock_only" });
    state = plannerReducer(state, { type: "CONFIRM_CANDIDATE", endpoint: "origin", candidate: unionStation });
    state = plannerReducer(state, { type: "PLAN_START" });
    state = plannerReducer(state, { type: "PLAN_ERROR", sequence: state.request.sequence, error: { code: "ROUTER_UNAVAILABLE", message: "down" } });
    expect(state.request.status).toBe("error");
    state = plannerReducer(state, { type: "CLEAR_TRIP" });
    expect(state.scope).toBe("flock_only");
    expect(state.origin.confirmed).toBeNull();
    expect(state.request.status).toBe("idle");
  });

  it("reports an explicit no-match state for empty search results", () => {
    const state = plannerReducer(initialPlannerState, { type: "SEARCH_RESULT", endpoint: "origin", candidates: [] });
    expect(state.origin.error?.code).toBe("NO_MATCH");
  });

  it("relabels a map pin from a reverse lookup only while that pin is still confirmed", () => {
    let state = plannerReducer(initialPlannerState, { type: "SET_PIN_MODE", endpoint: "origin" });
    state = plannerReducer(state, { type: "PIN_PLACED", lat: 39.753, lon: -105.0002 });
    state = plannerReducer(state, { type: "RELABEL_ENDPOINT", endpoint: "origin", lat: 39.753, lon: -105.0002, label: "Map pin near Union Station" });
    expect(state.origin.confirmed?.label).toBe("Map pin near Union Station");
    expect(state.origin.confirmed?.lat).toBe(39.753);
    // A stale lookup for a different pin position is ignored.
    state = plannerReducer(state, { type: "RELABEL_ENDPOINT", endpoint: "origin", lat: 39.7, lon: -105.0, label: "elsewhere" });
    expect(state.origin.confirmed?.label).toBe("Map pin near Union Station");
    // Typed addresses are never relabelled.
    state = plannerReducer(state, { type: "CONFIRM_CANDIDATE", endpoint: "origin", candidate: unionStation });
    state = plannerReducer(state, { type: "RELABEL_ENDPOINT", endpoint: "origin", lat: unionStation.lat, lon: unionStation.lon, label: "nope" });
    expect(state.origin.confirmed?.label).toBe("Union Station");
  });

  it("keeps the units preference across clear trip", () => {
    let state = plannerReducer(initialPlannerState, { type: "SET_UNITS", units: "mi" });
    state = plannerReducer(state, { type: "CLEAR_TRIP" });
    expect(state.units).toBe("mi");
  });

  it("bounds the detour controls", () => {
    expect(plannerReducer(initialPlannerState, { type: "SET_MAX_EXTRA", minutes: 999 }).maxExtraMinutes).toBe(120);
    expect(plannerReducer(initialPlannerState, { type: "SET_RELATIVE", factor: 0.2 }).relativeLimit).toBe(1);
  });
});

describe("plannerReducer cancel and clear (M6)", () => {
  function planning() {
    let state = initialPlannerState;
    state = plannerReducer(state, { type: "CONFIRM_CANDIDATE", endpoint: "origin", candidate: unionStation });
    state = plannerReducer(state, { type: "CONFIRM_CANDIDATE", endpoint: "destination", candidate: zoo });
    return plannerReducer(state, { type: "PLAN_START" });
  }

  it("cancelling is an explicit state and the late answer to the cancelled request is dropped", () => {
    let state = planning();
    const sequence = state.request.sequence;
    state = plannerReducer(state, { type: "PLAN_CANCEL" });
    expect(state.request.status).toBe("cancelled");
    expect(canPlan(state)).toBe(true);
    state = plannerReducer(state, { type: "PLAN_SUCCESS", sequence, result: fakeResult("late") });
    expect(state.result).toBeNull();
    expect(state.request.status).toBe("cancelled");
  });

  it("clear trip removes endpoints, result, selection, and errors but keeps preferences", () => {
    let state = planning();
    state = plannerReducer(state, { type: "SET_SCOPE", scope: "flock_only" });
    state = plannerReducer(state, { type: "SET_UNITS", units: "mi" });
    state = plannerReducer(state, { type: "PLAN_SUCCESS", sequence: state.request.sequence, result: fakeResult("r9") });
    expect(selectedRoute(state)?.route_id).toBe("r9");
    state = plannerReducer(state, { type: "CLEAR_TRIP" });
    expect(state.origin.confirmed).toBeNull();
    expect(state.destination.text).toBe("");
    expect(state.result).toBeNull();
    expect(state.selectedRouteId).toBeNull();
    expect(state.request.status).toBe("idle");
    expect(state.scope).toBe("flock_only");
    expect(state.units).toBe("mi");
  });
});
