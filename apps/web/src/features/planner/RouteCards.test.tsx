import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import type { AssessmentOut, PlanResponse, ProfileOutcomeOut, RouteOptionOut, SearchOut } from "@/lib/api/types";
import { RouteCards, generatedByText } from "./RouteCards";

function option(assessment: AssessmentOut | null, overrides: Partial<RouteOptionOut> = {}): RouteOptionOut {
  const assessed = assessment !== null && assessment.status !== "not_assessed";
  return {
    route_id: "r1",
    profiles: ["standard"],
    geometry: { type: "LineString", coordinates: [[-105.0002, 39.753], [-104.95, 39.7503]] },
    estimated_duration_seconds: 618,
    length_meters: 6423,
    extra_duration_seconds: 0,
    extra_distance_meters: 0,
    origin_snap_distance_meters: 12,
    destination_snap_distance_meters: 80,
    matched_camera_record_count: assessment?.matched_record_count ?? null,
    uncertain_nearby_camera_count: assessment?.uncertain_record_count ?? null,
    exposure_count: assessed ? (assessment.matched_record_count ?? 0) + (assessment.uncertain_record_count ?? 0) : null,
    generated_by: "baseline",
    detour_bound_seconds: null,
    counting_method_version: assessment ? "assess-1.0" : null,
    camera_scope: "all_alpr",
    camera_snapshot_id: "snap-1",
    camera_source_as_of: "2026-10-19T14:46:21Z",
    camera_downloaded_at: "2026-10-19T14:48:00Z",
    road_graph_version: "colorado@2026",
    assessment_coverage_status: assessment?.status ?? "not_assessed",
    search_status: "completed",
    warnings: [],
    maneuvers: [],
    has_highway: false,
    has_toll: false,
    engine_candidate: "alternate-2",
    assessment,
    ...overrides,
  };
}

function search(overrides: Partial<SearchOut> = {}): SearchOut {
  return {
    status: "completed",
    method_version: "search-1.0",
    routing_calls_used: 1,
    routing_calls_budget: 8,
    planning_deadline_seconds: 20,
    elapsed_seconds: 0.4,
    candidates_generated: 3,
    candidates_assessed: 3,
    iterations: 0,
    notes: [],
    profile_outcomes: [],
    meaning: "Best among the candidates this bounded search evaluated, not a proof of a globally optimal camera-minimum path.",
    ...overrides,
  };
}

function result(assessment: AssessmentOut | null, extra: Partial<PlanResponse> = {}): PlanResponse {
  return { request_id: "req", region_id: "denver", reference_duration_seconds: 618, candidates_evaluated: 3, search_status: "completed", assessment_coverage_status: assessment?.status ?? "not_assessed", warnings: [], options: [option(assessment)], search: search(), disclaimer: "advisory", ...extra };
}

const assessed: AssessmentOut = {
  status: "partial",
  counting_method_version: "assess-1.0",
  radius_m: 50,
  scope: "all_alpr",
  snapshot_id: "snap-1",
  graph_version: "colorado@2026",
  coverage_fraction: 0.62,
  matched_record_count: 2,
  uncertain_record_count: 1,
  sensitivity: [{ radius_m: 25, records_within: 1 }, { radius_m: 50, records_within: 3 }, { radius_m: 100, records_within: 4 }],
  warnings: ["Route leaves the assessed data area (62% of its length is inside); camera counts are not complete."],
  meaning: "Counts are mapped records, not observed recordings.",
  encounters: [
    { source_key: "osm:node:1", lat: 39.75, lon: -104.99, status: "associated", reason: "nearest drivable road is Main Street (4 m), which the route traverses", distance_m: 4, position_m: 1200, position_fraction: 0.19, pass_count: 1, site_group_id: "osm:node:1", manufacturer: "flock_safety", is_flock: true, lifecycle_state: "mapped", direction_raw: "90", direction_conflict: false, heading_relation: "mapped direction 90°, travel heading 88° (difference 2°; not used for counting)", in_envelope: true, source_url: "https://www.openstreetmap.org/node/1", source_timestamp: null, check_date: null, association: { method: "valhalla_locate_nearest_way", radius_m: 50, graph_version: "colorado@2026", nearest_way_id: 10, nearest_road_names: ["Main Street"], nearest_distance_m: 4, route_way_id: 10, route_road_names: ["Main Street"], route_way_distance_m: 4, candidates_within_radius: 2, same_road: true, ambiguous: false, grade_separated: false } },
    { source_key: "osm:node:2", lat: 39.76, lon: -104.98, status: "nearby_unresolved", reason: "nearest drivable road is Frontage Road (5 m); the route uses Main Street (30 m), a different road nearby (possibly a parallel or frontage road)", distance_m: 30, position_m: 2500, position_fraction: 0.39, pass_count: 2, site_group_id: "osm:node:2", manufacturer: null, is_flock: false, lifecycle_state: "mapped", direction_raw: null, direction_conflict: false, heading_relation: null, in_envelope: true, source_url: "https://www.openstreetmap.org/node/2", source_timestamp: null, check_date: null, association: { method: "valhalla_locate_nearest_way", radius_m: 50, graph_version: "colorado@2026", nearest_way_id: 11, nearest_road_names: ["Frontage Road"], nearest_distance_m: 5, route_way_id: 10, route_road_names: ["Main Street"], route_way_distance_m: 30, candidates_within_radius: 2, same_road: false, ambiguous: false, grade_separated: false } },
    { source_key: "osm:node:3", lat: 39.77, lon: -104.97, status: "excluded_scope", reason: "outside the selected camera scope; not counted", distance_m: 8, position_m: 3000, position_fraction: 0.47, pass_count: 1, site_group_id: "osm:node:3", manufacturer: "axon", is_flock: false, lifecycle_state: "mapped", direction_raw: null, direction_conflict: false, heading_relation: null, in_envelope: true, source_url: "https://www.openstreetmap.org/node/3", source_timestamp: null, check_date: null, association: null },
  ],
};

const complete: AssessmentOut = { ...assessed, status: "complete", coverage_fraction: 1, warnings: [] };
const zero: AssessmentOut = { ...complete, matched_record_count: 0, uncertain_record_count: 0, encounters: [] };

describe("RouteCards assessment display", () => {
  it("shows counts, uncertainty, sensitivity, partial coverage, and per-record evidence", () => {
    render(<RouteCards result={result(assessed)} region={null} selectedRouteId="r1" units="km" onSelect={() => undefined} />);
    expect(screen.getByTestId("encounter-summary")).toHaveTextContent("2 mapped records on roads this route uses");
    expect(screen.getByText(/^1 \(different or ambiguous road/)).toBeInTheDocument();
    expect(screen.getByTestId("exposure")).toHaveTextContent("3 (matched plus uncertain, each record once)");
    expect(screen.getByText("1 / 3 / 4")).toBeInTheDocument();
    expect(screen.getByText(/partial: 62% of the route/)).toBeInTheDocument();
    const list = screen.getByTestId("encounter-list");
    expect(list).toHaveTextContent("Camera evidence (2 records near this route)"); // the out-of-scope record is not listed
    const items = screen.getAllByTestId("encounter");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("counted");
    expect(items[0]).toHaveTextContent("on Main Street");
    expect(items[1]).toHaveTextContent("uncertain");
    expect(items[1]).toHaveTextContent("nearest Frontage Road; route on Main Street");
    expect(items[1]).toHaveTextContent("passed 2 times");
    expect(screen.getByText("osm:node:2 on OpenStreetMap")).toHaveAttribute("href", "https://www.openstreetmap.org/node/2");
    expect(screen.getByTestId("snap-note")).toHaveTextContent("ends 80 m");
  });

  it("states the zero case and the not-assessed case honestly", () => {
    render(<RouteCards result={result(zero)} region={null} selectedRouteId="r1" units="km" onSelect={() => undefined} />);
    expect(screen.getByTestId("encounter-summary")).toHaveTextContent("No mapped encounters detected by this assessment. Unmapped or mislocated cameras may still be present.");
    expect(screen.getByText(/complete: the whole route/)).toBeInTheDocument();
  });

  it("never shows zero when nothing was assessed", () => {
    render(<RouteCards result={result(null)} region={null} selectedRouteId="r1" units="km" onSelect={() => undefined} />);
    expect(screen.getByTestId("encounter-summary")).toHaveTextContent("Not assessed");
    expect(screen.getByTestId("exposure")).toHaveTextContent("not assessed");
    expect(screen.queryByTestId("encounter-list")).not.toBeInTheDocument();
  });
});

describe("RouteCards comparison display (M5)", () => {
  const improved: ProfileOutcomeOut[] = [
    { profile: "balanced", outcome: "improved", message: "0 mapped encounter(s) versus 3", max_extra_seconds: 600, max_relative_factor: 1.5, bound_seconds: 927, best_exposure_count: 0, route_id: "r2" },
    { profile: "fewest_mapped", outcome: "improved", message: "0 mapped encounter(s) versus 3", max_extra_seconds: 1200, max_relative_factor: 1.75, bound_seconds: 1081, best_exposure_count: 0, route_id: "r2" },
  ];

  it("shows the comparison summary, shared labels on one card, and how a route was found", () => {
    const detour = option(zero, { route_id: "r2", profiles: ["balanced", "fewest_mapped"], estimated_duration_seconds: 790, extra_duration_seconds: 172, generated_by: "penalized@40", detour_bound_seconds: 1081 });
    const plan = result(complete, { options: [option(complete), detour], search: search({ routing_calls_used: 3, candidates_assessed: 4, elapsed_seconds: 1.3, iterations: 2, profile_outcomes: improved }) });
    const region = { profiles: { standard: { label: "Standard route" }, balanced: { label: "Balanced" }, fewest_mapped: { label: "Fewest mapped cameras found" } } } as never;
    render(<RouteCards result={plan} region={region} selectedRouteId="r2" units="km" maxExtraMinutes={10} onSelect={() => undefined} onRaiseLimit={() => undefined} />);
    const summary = screen.getByTestId("search-summary");
    expect(summary).toHaveTextContent("4 candidate routes fully assessed using 3 of 8 routing calls in 1.3 s");
    expect(screen.getByTestId("search-status")).toHaveTextContent("search completed");
    expect(screen.queryByTestId("profile-outcome")).not.toBeInTheDocument(); // both preferences produced a route
    expect(screen.queryByTestId("raise-limit")).not.toBeInTheDocument();
    const cards = screen.getAllByTestId("route-card");
    expect(cards).toHaveLength(2);
    expect(cards[1]).toHaveTextContent("Balanced");
    expect(cards[1]).toHaveTextContent("Fewest mapped cameras found");
    expect(cards[1]).toHaveTextContent("+3 min");
    expect(cards[1]).toHaveTextContent("soft road penalties during path search (factor 40); reported time is unaffected");
    expect(cards[1]).toHaveTextContent("Detour limit applied");
    expect(cards[0]).toHaveTextContent("engine baseline (no camera preference)");
    expect(summary).toHaveTextContent("not a proof of a globally optimal camera-minimum path");
  });

  it("explains a preference that found nothing within the limit and offers to raise it", () => {
    const onRaiseLimit = vi.fn();
    const outcomes: ProfileOutcomeOut[] = [
      { profile: "balanced", outcome: "same_as_standard", message: "No lower-exposure route found within your detour limit (up to 10 min extra or 1.50 x the Standard time, whichever is smaller (927 s for this trip)); 5 candidate(s) were assessed. Increase the limit to search further.", max_extra_seconds: 600, max_relative_factor: 1.5, bound_seconds: 927, best_exposure_count: 3, route_id: "r1" },
      { profile: "fewest_mapped", outcome: "same_as_standard", message: "No lower-exposure route found within your detour limit (up to 20 min extra or 1.75 x the Standard time, whichever is smaller (1081 s for this trip)); 5 candidate(s) were assessed. Increase the limit to search further.", max_extra_seconds: 1200, max_relative_factor: 1.75, bound_seconds: 1081, best_exposure_count: 3, route_id: "r1" },
    ];
    const plan = result(complete, { options: [option(complete, { profiles: ["standard", "balanced", "fewest_mapped"] })], search: search({ status: "budget_exhausted", routing_calls_used: 8, candidates_assessed: 5, notes: ["The routing-call budget (8) ran out while new candidates were still appearing; a larger budget might find more."], profile_outcomes: outcomes }) });
    render(<RouteCards result={plan} region={null} selectedRouteId="r1" units="km" maxExtraMinutes={10} onSelect={() => undefined} onRaiseLimit={onRaiseLimit} />);
    expect(screen.getByTestId("search-status")).toHaveTextContent("routing-call budget exhausted");
    expect(screen.getByText(/ran out while new candidates/)).toBeInTheDocument();
    const outcomesShown = screen.getAllByTestId("profile-outcome");
    expect(outcomesShown).toHaveLength(2);
    expect(outcomesShown[0]).toHaveTextContent("balanced: No lower-exposure route found within your detour limit");
    expect(screen.getAllByTestId("route-card")).toHaveLength(1);
    expect(screen.getByTestId("route-card")).toHaveTextContent("fewest_mapped"); // the Standard card carries every label that resolved to it
    fireEvent.click(screen.getByTestId("raise-limit"));
    expect(onRaiseLimit).toHaveBeenCalledWith(20);
  });

  it("warns when preferences could not be evaluated and offers no false improvement", () => {
    const outcomes: ProfileOutcomeOut[] = [
      { profile: "balanced", outcome: "not_assessed", message: "Camera assessment is unavailable, so this preference could not be evaluated; only the Standard route is shown, unassessed.", max_extra_seconds: 600, max_relative_factor: 1.5, bound_seconds: 927, best_exposure_count: null, route_id: null },
    ];
    const plan = result(null, { search_status: "not_run", search: search({ status: "not_run", candidates_assessed: 0, profile_outcomes: outcomes }) });
    render(<RouteCards result={plan} region={null} selectedRouteId="r1" units="km" maxExtraMinutes={10} onSelect={() => undefined} onRaiseLimit={() => undefined} />);
    expect(screen.getByTestId("search-status")).toHaveTextContent("camera-aware search not run");
    expect(screen.getByTestId("profile-outcome")).toHaveClass("notice-warn");
    expect(screen.getByTestId("profile-outcome")).toHaveTextContent("could not be evaluated");
    expect(screen.queryByTestId("raise-limit")).not.toBeInTheDocument();
    expect(screen.getByTestId("route-card")).not.toHaveTextContent("Balanced");
  });

  it("describes every generation method in plain words", () => {
    expect(generatedByText("baseline")).toContain("engine baseline");
    expect(generatedByText("penalized@160")).toContain("factor 160");
    expect(generatedByText("excluded")).toContain("hard road exclusions");
  });
});
