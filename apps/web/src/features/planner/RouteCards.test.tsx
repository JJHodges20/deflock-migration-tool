import { render, screen } from "@testing-library/react";
import type { AssessmentOut, PlanResponse, RouteOptionOut } from "@/lib/api/types";
import { RouteCards } from "./RouteCards";

function option(assessment: AssessmentOut | null): RouteOptionOut {
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
  };
}

function result(assessment: AssessmentOut | null): PlanResponse {
  return { request_id: "req", region_id: "denver", reference_duration_seconds: 618, candidates_evaluated: 3, search_status: "completed", assessment_coverage_status: assessment?.status ?? "not_assessed", warnings: [], options: [option(assessment)], disclaimer: "advisory" };
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
    { source_key: "osm:node:1", lat: 39.75, lon: -104.99, status: "associated", reason: "nearest drivable road is Main Street (4 m), which the route traverses", distance_m: 4, position_m: 1200, position_fraction: 0.19, pass_count: 1, site_group_id: "osm:node:1", manufacturer: "flock_safety", is_flock: true, lifecycle_state: "mapped", direction_raw: "90", direction_conflict: false, heading_relation: "mapped direction 90°, travel heading 88° (difference 2°; not used for counting)", in_envelope: true, source_url: "https://www.openstreetmap.org/node/1", association: { method: "valhalla_locate_nearest_way", radius_m: 50, graph_version: "colorado@2026", nearest_way_id: 10, nearest_road_names: ["Main Street"], nearest_distance_m: 4, route_way_id: 10, route_road_names: ["Main Street"], route_way_distance_m: 4, candidates_within_radius: 2, same_road: true, ambiguous: false, grade_separated: false } },
    { source_key: "osm:node:2", lat: 39.76, lon: -104.98, status: "nearby_unresolved", reason: "nearest drivable road is Frontage Road (5 m); the route uses Main Street (30 m), a different road nearby (possibly a parallel or frontage road)", distance_m: 30, position_m: 2500, position_fraction: 0.39, pass_count: 2, site_group_id: "osm:node:2", manufacturer: null, is_flock: false, lifecycle_state: "mapped", direction_raw: null, direction_conflict: false, heading_relation: null, in_envelope: true, source_url: "https://www.openstreetmap.org/node/2", association: { method: "valhalla_locate_nearest_way", radius_m: 50, graph_version: "colorado@2026", nearest_way_id: 11, nearest_road_names: ["Frontage Road"], nearest_distance_m: 5, route_way_id: 10, route_road_names: ["Main Street"], route_way_distance_m: 30, candidates_within_radius: 2, same_road: false, ambiguous: false, grade_separated: false } },
    { source_key: "osm:node:3", lat: 39.77, lon: -104.97, status: "excluded_scope", reason: "outside the selected camera scope; not counted", distance_m: 8, position_m: 3000, position_fraction: 0.47, pass_count: 1, site_group_id: "osm:node:3", manufacturer: "axon", is_flock: false, lifecycle_state: "mapped", direction_raw: null, direction_conflict: false, heading_relation: null, in_envelope: true, source_url: "https://www.openstreetmap.org/node/3", association: null },
  ],
};

describe("RouteCards assessment display", () => {
  it("shows counts, uncertainty, sensitivity, partial coverage, and per-record evidence", () => {
    render(<RouteCards result={result(assessed)} region={null} selectedRouteId="r1" units="km" onSelect={() => undefined} />);
    expect(screen.getByTestId("encounter-summary")).toHaveTextContent("2 mapped records on roads this route uses");
    expect(screen.getByText(/^1 \(different or ambiguous road/)).toBeInTheDocument();
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
    render(<RouteCards result={result({ ...assessed, status: "complete", coverage_fraction: 1, matched_record_count: 0, uncertain_record_count: 0, encounters: [], warnings: [] })} region={null} selectedRouteId="r1" units="km" onSelect={() => undefined} />);
    expect(screen.getByTestId("encounter-summary")).toHaveTextContent("No mapped encounters detected by this assessment. Unmapped or mislocated cameras may still be present.");
    expect(screen.getByText(/complete: the whole route/)).toBeInTheDocument();
  });

  it("never shows zero when nothing was assessed", () => {
    render(<RouteCards result={result(null)} region={null} selectedRouteId="r1" units="km" onSelect={() => undefined} />);
    expect(screen.getByTestId("encounter-summary")).toHaveTextContent("Not assessed");
    expect(screen.queryByTestId("encounter-list")).not.toBeInTheDocument();
  });
});
