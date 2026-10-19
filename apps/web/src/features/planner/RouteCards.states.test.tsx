import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import type { AssessmentOut, DataHealth, PlanResponse, RouteOptionOut, SearchOut } from "@/lib/api/types";
import { RouteCards, cardState } from "./RouteCards";

const NOW = new Date("2026-10-19T20:00:00Z");

function assessment(matched: number, uncertain: number, status: AssessmentOut["status"] = "complete"): AssessmentOut {
  return { status, counting_method_version: "assess-1.0", radius_m: 50, scope: "all_alpr", snapshot_id: "snap-1", graph_version: "g@1", coverage_fraction: status === "partial" ? 0.4 : 1, matched_record_count: matched, uncertain_record_count: uncertain, sensitivity: [], warnings: status === "partial" ? ["Route leaves the assessed data area (40% of its length is inside); camera counts are not complete."] : [], meaning: "records", encounters: [] };
}

function option(id: string, profiles: RouteOptionOut["profiles"], a: AssessmentOut | null, overrides: Partial<RouteOptionOut> = {}): RouteOptionOut {
  const assessed = a !== null && a.status !== "not_assessed";
  return {
    route_id: id, profiles, geometry: { type: "LineString", coordinates: [[-105, 39.7], [-104.9, 39.8]] }, estimated_duration_seconds: 600, length_meters: 6000, extra_duration_seconds: 0, extra_distance_meters: 0,
    origin_snap_distance_meters: 1, destination_snap_distance_meters: 1, matched_camera_record_count: a?.matched_record_count ?? null, uncertain_nearby_camera_count: a?.uncertain_record_count ?? null,
    exposure_count: assessed ? (a.matched_record_count ?? 0) + (a.uncertain_record_count ?? 0) : null, generated_by: "baseline", detour_bound_seconds: null, counting_method_version: assessed ? "assess-1.0" : null,
    camera_scope: "all_alpr", camera_snapshot_id: "snap-1", camera_source_as_of: "2026-10-19T14:46:21Z", camera_downloaded_at: "2026-10-19T15:00:00Z", road_graph_version: "g@1", assessment_coverage_status: a?.status ?? "not_assessed",
    search_status: "completed", warnings: [], maneuvers: [], has_highway: false, has_toll: false, engine_candidate: "primary-0", assessment: a, ...overrides,
  };
}

function search(overrides: Partial<SearchOut> = {}): SearchOut {
  return { status: "completed", method_version: "search-1.0", routing_calls_used: 2, routing_calls_budget: 8, planning_deadline_seconds: 20, elapsed_seconds: 0.3, candidates_generated: 3, candidates_assessed: 3, iterations: 1, notes: [], profile_outcomes: [], meaning: "best among evaluated", ...overrides };
}

function plan(options: RouteOptionOut[], s: SearchOut = search()): PlanResponse {
  return { request_id: "req", region_id: "denver", reference_duration_seconds: 600, candidates_evaluated: 3, search_status: s.status, assessment_coverage_status: options[0].assessment_coverage_status, warnings: [], options, search: s, disclaimer: "advisory" };
}

const health = { snapshot: { in_envelope_alpr_count: 1285 }, staleness: { is_stale: false, stale_after_hours: 48 } } as unknown as DataHealth;
const emptyHealth = { snapshot: { in_envelope_alpr_count: 0 }, staleness: { is_stale: false, stale_after_hours: 48 } } as unknown as DataHealth;

describe("result states are unmistakable (M6 gate)", () => {
  it("unknown data: nothing assessed, counts unknown rather than zero", () => {
    const p = plan([option("r1", ["standard"], null, { camera_snapshot_id: null })]);
    render(<RouteCards result={p} region={null} health={health} selectedRouteId="r1" units="km" now={NOW} onSelect={() => undefined} />);
    const state = screen.getByTestId("result-state");
    expect(state).toHaveAttribute("data-state", "unknown");
    expect(state).toHaveTextContent("Unknown data");
    expect(state).toHaveTextContent("unknown, not zero");
    expect(screen.getByTestId("route-card")).toHaveTextContent("unknown data");
  });

  it("no mapped encounters: the honest zero, with the empty-inventory caveat when the snapshot holds no records", () => {
    const p = plan([option("r1", ["standard", "balanced", "fewest_mapped"], assessment(0, 0))]);
    const { unmount } = render(<RouteCards result={p} region={null} health={health} selectedRouteId="r1" units="km" now={NOW} onSelect={() => undefined} />);
    expect(screen.getByTestId("result-state")).toHaveAttribute("data-state", "none");
    expect(screen.getByTestId("result-state")).toHaveTextContent("Unmapped or mislocated cameras may still be present.");
    expect(screen.getByTestId("result-state")).not.toHaveTextContent("empty inventory");
    unmount();
    render(<RouteCards result={p} region={null} health={emptyHealth} selectedRouteId="r1" units="km" now={NOW} onSelect={() => undefined} />);
    expect(screen.getByTestId("result-state")).toHaveTextContent("reflects an empty inventory");
  });

  it("no better route: the Standard card says so and offers to raise the limit", () => {
    const outcomes = [{ profile: "balanced" as const, outcome: "same_as_standard" as const, message: "No lower-exposure route found within your detour limit (…); 4 candidate(s) were assessed. Increase the limit to search further.", max_extra_seconds: 600, max_relative_factor: 1.5, bound_seconds: 900, best_exposure_count: 3, route_id: "r1" }];
    const p = plan([option("r1", ["standard", "balanced"], assessment(2, 1))], search({ profile_outcomes: outcomes }));
    const onRaiseLimit = vi.fn();
    render(<RouteCards result={p} region={null} health={health} selectedRouteId="r1" units="km" now={NOW} maxExtraMinutes={10} onSelect={() => undefined} onRaiseLimit={onRaiseLimit} />);
    const state = screen.getByTestId("result-state");
    expect(state).toHaveAttribute("data-state", "no-better");
    expect(state).toHaveTextContent("No better route within your limit");
    expect(state).toHaveTextContent("No lower-exposure route found");
    fireEvent.click(screen.getByTestId("raise-limit"));
    expect(onRaiseLimit).toHaveBeenCalledWith(20);
  });

  it("lower exposure: the alternative card compares itself with the Standard route; an incomplete candidate says so", () => {
    const standard = option("r1", ["standard"], assessment(2, 1));
    const better = option("r2", ["balanced", "fewest_mapped"], assessment(0, 0), { extra_duration_seconds: 240, generated_by: "penalized@40" });
    const partial = option("r3", ["standard"], assessment(1, 0, "partial"));
    render(<RouteCards result={plan([standard, better])} region={null} health={health} selectedRouteId="r2" units="km" now={NOW} onSelect={() => undefined} />);
    const states = screen.getAllByTestId("result-state");
    expect(states[0]).toHaveAttribute("data-state", "assessed");
    expect(states[0]).toHaveTextContent("3 mapped records near this route");
    expect(states[1]).toHaveAttribute("data-state", "better");
    expect(states[1]).toHaveTextContent("Lower exposure than Standard");
    expect(states[1]).toHaveTextContent("versus 3 on the Standard route; +4 min");
    expect(cardState(partial, plan([partial]), false)).toMatchObject({ kind: "incomplete", label: "Incomplete assessment" });
    expect(cardState(partial, plan([partial]), false).text).toContain("40%");
  });

  it("shows data-age badges and flags stale camera data", () => {
    const p = plan([option("r1", ["standard"], assessment(0, 0))]);
    const region = { routing_graph: { id: "g", extract_data_timestamp: "2026-10-14T20:21:12Z", engine_image: "v" }, profiles: {} } as never;
    const { unmount } = render(<RouteCards result={p} region={region} health={health} selectedRouteId="r1" units="km" now={NOW} onSelect={() => undefined} />);
    expect(screen.getByTestId("card-camera-age")).toHaveTextContent("5 h old");
    expect(screen.getByTestId("card-road-age")).toHaveTextContent("5 days old");
    unmount();
    render(<RouteCards result={p} region={region} health={{ ...health, staleness: { is_stale: true, stale_after_hours: 48 } } as unknown as DataHealth} selectedRouteId="r1" units="km" now={NOW} onSelect={() => undefined} />);
    expect(screen.getByTestId("card-camera-age")).toHaveTextContent("stale, 5 h old");
    expect(screen.getByTestId("card-camera-age")).toHaveClass("badge-warn");
  });

  it("offers print and GeoJSON download only on the selected card and names the file", () => {
    const p = plan([option("r1", ["standard"], assessment(0, 0)), option("r2", ["balanced"], assessment(0, 0))]);
    const printSpy = vi.fn();
    vi.stubGlobal("print", printSpy);
    const createObjectURL = vi.fn(() => "blob:route");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL }));
    const clicks: string[] = [];
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicks.push(this.download);
    });
    render(<RouteCards result={p} region={null} health={health} selectedRouteId="r2" units="km" now={NOW} exportContext={{ originLabel: "Union Station", destinationLabel: "Denver Zoo" }} onSelect={() => undefined} />);
    expect(screen.getAllByTestId("download-route")).toHaveLength(1);
    fireEvent.click(screen.getByTestId("print-route"));
    expect(printSpy).toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("download-route"));
    expect(createObjectURL).toHaveBeenCalled();
    expect(clicks).toEqual(["deflockmigration-balanced-20261019T200000.geojson"]);
    click.mockRestore();
    vi.unstubAllGlobals();
  });
});
