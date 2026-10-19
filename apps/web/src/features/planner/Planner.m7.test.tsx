import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("next/dynamic", () => ({ default: () => () => <div data-testid="map-stub" /> }));

import type { DataHealth } from "@/lib/api/types";
import { Planner, outdatedVersions } from "./Planner";

const region = {
  region_id: "denver",
  display_name: "Denver, Colorado (pilot)",
  config_version: 1,
  service_boundary: { id: "denver-service-v1", geometry: { type: "Polygon", coordinates: [] }, bbox_wsen: [-105.11, 39.61, -104.6, 39.91], source: "test", retrieved_at: "2026-10-15" },
  camera_data_envelope: { id: "denver-envelope-v1-20km", bbox_wsen: [-105.34, 39.43, -104.37, 40.09], buffer_m: 20000, meaning: "" },
  routing_graph: { id: "colorado-geofabrik-2026-10-14", extract_data_timestamp: "2026-10-14T20:21:12Z", engine_image: "valhalla" },
  basemap: { path: "/basemap/denver.pmtiles", fonts_path: "/basemap/fonts", sprite_path: "/basemap/sprites/v4/light", attribution: "Protomaps © OpenStreetMap", bbox_wsen: [-105.34, 39.43, -104.37, 40.09], max_zoom: 15 },
  capabilities: { geocoder_configured: false, geocoder_provider: "none", routing_provider: "valhalla", camera_source_adapter: "overpass_bounded", camera_assessment: "assess-1.0", coordinate_input: true, map_pins: true },
  profiles: {
    standard: { label: "Standard route", description: "Fastest baseline.", max_extra_seconds: null, max_relative_factor: null },
    balanced: { label: "Balanced", description: "", max_extra_seconds: 600, max_relative_factor: 1.5 },
    fewest_mapped: { label: "Fewest mapped cameras found", description: "", max_extra_seconds: 1200, max_relative_factor: 1.75 },
  },
  camera_scopes: ["all_alpr", "flock_only"],
  attributions: ["© OpenStreetMap contributors"],
  disclaimer: "Routes are advisory.",
};

function healthWith(snapshotId: string, built: string): DataHealth {
  return {
    region_id: "denver", service_boundary_id: "b", envelope_id: "e", config_version: 1, camera_source: {},
    snapshot: { snapshot_id: snapshotId, timestamp_osm_base: "2026-10-19T14:46:21Z", downloaded_at: "2026-10-19T15:00:00Z", promoted_at: null, element_count: 1, record_count: 1, alpr_count: 1, flock_count: 1, unknown_manufacturer_count: 0, in_envelope_alpr_count: 1, no_longer_mapped_count: 0, previous_active_snapshot_id: null, parser_version: "p", quality: {}, review_note: null, diff: null, counts_meaning: "" },
    inventory: { retain_missing_hours: 72, unresolved_disappearance: "retain_as_uncertain", keep_superseded_snapshots: 30, keep_quarantined_snapshots: 10, pending_review: [] },
    last_sync: null, last_failure: null, recent_syncs: [],
    staleness: { is_stale: false, stale_after_hours: 48, age_hours: 1 },
    router: { available: true, version: "3.9.1", tileset_last_modified: built, has_tiles: true, graph_id: "g", extract_data_timestamp: "2026-10-14T20:21:12Z", message: null },
    geocoder: { configured: false, available: false, provider: "none", data_updated: null, message: null },
    basemap: { id: "b", attribution: "", max_zoom: 15 }, database: { available: true }, generated_at: "",
  };
}

const option = { route_id: "r1", profiles: ["standard"], geometry: { type: "LineString", coordinates: [[-105.0002, 39.753], [-104.95, 39.7503]] }, estimated_duration_seconds: 618, length_meters: 6423, extra_duration_seconds: 0, extra_distance_meters: 0, origin_snap_distance_meters: 1, destination_snap_distance_meters: 1, matched_camera_record_count: 0, uncertain_nearby_camera_count: 0, exposure_count: 0, generated_by: "baseline", detour_bound_seconds: null, counting_method_version: "assess-1.0", camera_scope: "all_alpr", camera_snapshot_id: "snap-old", camera_source_as_of: "2026-10-19T14:46:21Z", camera_downloaded_at: "2026-10-19T15:00:00Z", road_graph_version: "colorado@2026-10-15T23:22:43Z", assessment_coverage_status: "complete", search_status: "completed", warnings: [], maneuvers: [{ instruction: "Drive east.", verbal_pre_transition_instruction: null, street_names: [], begin_street_names: [], length_meters: 6423, time_seconds: 618, type: 1, type_name: "start", begin_shape_index: 0, end_shape_index: 1, roundabout_exit_count: null, toll: false, highway: false }], has_highway: false, has_toll: false, engine_candidate: "primary-0", assessment: { status: "complete", counting_method_version: "assess-1.0", radius_m: 50, scope: "all_alpr", snapshot_id: "snap-old", graph_version: "colorado@2026-10-15T23:22:43Z", coverage_fraction: 1, matched_record_count: 0, uncertain_record_count: 0, sensitivity: [], warnings: [], meaning: "records", encounters: [] } };
const planBody = { request_id: "req", region_id: "denver", reference_duration_seconds: 618, candidates_evaluated: 1, search_status: "completed", assessment_coverage_status: "complete", warnings: [], disclaimer: "advisory", search: { status: "completed", method_version: "search-1.0", routing_calls_used: 1, routing_calls_budget: 8, planning_deadline_seconds: 20, elapsed_seconds: 0.1, candidates_generated: 1, candidates_assessed: 1, iterations: 0, notes: [], profile_outcomes: [], meaning: "best among evaluated" }, options: [option] };

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

let currentHealth: DataHealth;

beforeEach(() => {
  currentHealth = healthWith("snap-old", "2026-10-15T23:22:43Z");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/region")) return jsonResponse(region);
      if (url.endsWith("/api/v1/health/data")) return jsonResponse(currentHealth);
      if (url.includes("/api/v1/health/metrics") || url.includes("/api/v1/cameras/diffs")) return jsonResponse({ error: { code: "X", message: "n/a", details: {} }, request_id: "r" }, 503);
      if (url.endsWith("/api/v1/geocode")) {
        const body = JSON.parse(String(init?.body));
        const [lat, lon] = body.query.split(",").map(Number);
        return jsonResponse({ query_kind: "coordinates", provider: "coordinates", candidates: [{ label: `Coordinates ${lat}, ${lon}`, lat, lon, source: "coordinates", category: "coordinates", importance: null, inside_service_boundary: true }] });
      }
      if (url.endsWith("/api/v1/routes/plan")) return jsonResponse(planBody);
      throw new Error(`unexpected fetch ${url}`);
    }),
  );
});

describe("outdated results (M7: per-request version pinning made visible)", () => {
  it("names the newer snapshot and the rebuilt graph", () => {
    expect(outdatedVersions(option, healthWith("snap-old", "2026-10-15T23:22:43Z"))).toEqual([]);
    expect(outdatedVersions(option, healthWith("snap-new", "2026-10-15T23:22:43Z"))).toEqual(["a newer camera snapshot (snap-new) was published after this plan"]);
    expect(outdatedVersions(option, healthWith("snap-old", "2026-10-22T01:00:00Z"))).toEqual(["the road graph was rebuilt (2026-10-22T01:00:00Z) after this plan"]);
    expect(outdatedVersions({ camera_snapshot_id: null, road_graph_version: "colorado-geofabrik" }, healthWith("snap-new", "x"))).toEqual([]);
    expect(outdatedVersions(null, null)).toEqual([]);
  });

  it("shows the notice after Data Health reports a newer snapshot, without changing the planned result", async () => {
    render(<Planner />);
    await screen.findByText("Standard route");
    const start = screen.getByLabelText("Start") as HTMLInputElement;
    fireEvent.change(start, { target: { value: "39.7530, -105.0002" } });
    fireEvent.submit(start.closest("form")!);
    const destination = screen.getByLabelText("Destination") as HTMLInputElement;
    fireEvent.change(destination, { target: { value: "39.7503, -104.9500" } });
    fireEvent.submit(destination.closest("form")!);
    await waitFor(() => expect(screen.getByTestId("plan-button")).toBeEnabled());
    fireEvent.click(screen.getByTestId("plan-button"));
    await screen.findByTestId("route-cards");
    expect(screen.queryByTestId("outdated-result")).not.toBeInTheDocument();

    currentHealth = healthWith("snap-new", "2026-10-15T23:22:43Z");
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "visible" });
    document.dispatchEvent(new Event("visibilitychange"));
    const notice = await screen.findByTestId("outdated-result");
    expect(notice).toHaveTextContent("a newer camera snapshot (snap-new) was published after this plan");
    expect(screen.getByTestId("route-card")).toHaveTextContent("Standard route"); // the result itself is untouched
  });
});
