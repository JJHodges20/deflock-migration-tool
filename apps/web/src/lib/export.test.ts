import type { PlanResponse, RouteOptionOut } from "./api/types";
import { EXPORT_WARNING, exportFileName, routeToGeoJSON } from "./export";

const option: RouteOptionOut = {
  route_id: "r2",
  profiles: ["balanced", "fewest_mapped"],
  geometry: { type: "LineString", coordinates: [[-105.0002, 39.753], [-104.95, 39.7503]] },
  estimated_duration_seconds: 730.7,
  length_meters: 12414,
  extra_duration_seconds: 112.6,
  extra_distance_meters: 5991,
  origin_snap_distance_meters: 12,
  destination_snap_distance_meters: 80,
  matched_camera_record_count: 0,
  uncertain_nearby_camera_count: 0,
  exposure_count: 0,
  generated_by: "baseline",
  detour_bound_seconds: 1081,
  counting_method_version: "assess-1.0",
  camera_scope: "all_alpr",
  camera_snapshot_id: "snap-1",
  camera_source_as_of: "2026-10-19T14:46:21Z",
  camera_downloaded_at: "2026-10-19T14:48:00Z",
  road_graph_version: "colorado@2026",
  assessment_coverage_status: "complete",
  search_status: "completed",
  warnings: [],
  maneuvers: [{ instruction: "Drive east.", verbal_pre_transition_instruction: null, street_names: ["17th Street"], begin_street_names: [], length_meters: 500, time_seconds: 60, type: 1, type_name: "start", begin_shape_index: 0, end_shape_index: 1, roundabout_exit_count: null, toll: false, highway: false }],
  has_highway: true,
  has_toll: false,
  engine_candidate: "primary-0",
  assessment: { status: "complete", counting_method_version: "assess-1.0", radius_m: 50, scope: "all_alpr", snapshot_id: "snap-1", graph_version: "colorado@2026", coverage_fraction: 1, matched_record_count: 0, uncertain_record_count: 0, sensitivity: [], warnings: [], meaning: "records", encounters: [{ source_key: "osm:node:9", lat: 39.75, lon: -104.99, status: "beyond_radius", reason: "beyond", distance_m: 70, position_m: 100, position_fraction: 0.1, pass_count: 1, site_group_id: "osm:node:9", manufacturer: null, is_flock: false, lifecycle_state: "mapped", direction_raw: null, direction_conflict: false, heading_relation: null, in_envelope: true, source_url: "https://www.openstreetmap.org/node/9", source_timestamp: null, check_date: null, association: null }, { source_key: "osm:node:10", lat: 39.75, lon: -104.99, status: "excluded_scope", reason: "scope", distance_m: 7, position_m: 200, position_fraction: 0.2, pass_count: 1, site_group_id: "osm:node:10", manufacturer: "axon", is_flock: false, lifecycle_state: "mapped", direction_raw: null, direction_conflict: false, heading_relation: null, in_envelope: true, source_url: "https://www.openstreetmap.org/node/10", source_timestamp: null, check_date: null, association: null }] },
};

const result = { search: { method_version: "search-1.0" } } as PlanResponse;
const generatedAt = new Date("2026-10-19T18:05:07Z");

describe("routeToGeoJSON", () => {
  it("preserves geometry and timestamps and carries the recalculation warning", () => {
    const doc = routeToGeoJSON(option, result, { originLabel: "Union Station", destinationLabel: "Denver Zoo", generatedAt, disclaimer: "advisory", regionId: "denver", searchStatus: "completed" });
    expect(doc.type).toBe("FeatureCollection");
    const feature = doc.features[0];
    expect(feature.geometry).toEqual(option.geometry);
    expect(feature.properties.generated_at).toBe("2026-10-19T18:05:07.000Z");
    expect(feature.properties.camera_source_as_of).toBe("2026-10-19T14:46:21Z");
    expect(feature.properties.road_graph_version).toBe("colorado@2026");
    expect(feature.properties.profiles).toEqual(["balanced", "fewest_mapped"]);
    expect(feature.properties.warning).toBe(EXPORT_WARNING);
    expect(feature.properties.warning).toMatch(/may recalculate a different path/);
    expect(feature.properties.maneuvers[0].instruction).toBe("Drive east.");
    expect(feature.properties.encounters).toEqual([{ source_key: "osm:node:9", status: "beyond_radius", distance_m: 70, position_m: 100, source_url: "https://www.openstreetmap.org/node/9" }]); // out-of-scope records are not exported
  });

  it("names the file after the preferences and the time", () => {
    expect(exportFileName(option, generatedAt)).toBe("deflockmigration-balanced-fewest_mapped-20261019T180507.geojson");
  });
});
