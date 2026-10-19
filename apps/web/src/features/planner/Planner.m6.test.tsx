import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("next/dynamic", () => ({ default: () => () => <div data-testid="map-stub" /> }));

import { Planner } from "./Planner";

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

const health = { region_id: "denver", service_boundary_id: "denver-service-v1", envelope_id: "denver-envelope-v1-20km", config_version: 1, camera_source: {}, snapshot: null, inventory: { retain_missing_hours: 72, unresolved_disappearance: "retain_as_uncertain", keep_superseded_snapshots: 30, keep_quarantined_snapshots: 10, pending_review: [] }, last_sync: null, last_failure: null, recent_syncs: [], staleness: { is_stale: true, stale_after_hours: 48, age_hours: null, message: "no camera snapshot yet" }, router: { available: true, version: "3.9.1", tileset_last_modified: null, has_tiles: true, graph_id: "g", extract_data_timestamp: "2026-10-14T20:21:12Z", message: null }, geocoder: { configured: false, available: false, provider: "none", data_updated: null, message: null }, basemap: { id: "b", attribution: "", max_zoom: 15 }, database: { available: false }, generated_at: "" };

const planBody = {
  request_id: "req", region_id: "denver", reference_duration_seconds: 618, candidates_evaluated: 1, search_status: "not_run", assessment_coverage_status: "not_assessed", warnings: [], disclaimer: "advisory",
  search: { status: "not_run", method_version: "search-1.0", routing_calls_used: 1, routing_calls_budget: 8, planning_deadline_seconds: 20, elapsed_seconds: 0.1, candidates_generated: 1, candidates_assessed: 0, iterations: 0, notes: [], profile_outcomes: [], meaning: "best among evaluated" },
  options: [{ route_id: "r1", profiles: ["standard"], geometry: { type: "LineString", coordinates: [[-105.0002, 39.753], [-104.95, 39.7503]] }, estimated_duration_seconds: 618, length_meters: 6423, extra_duration_seconds: 0, extra_distance_meters: 0, origin_snap_distance_meters: 1, destination_snap_distance_meters: 1, matched_camera_record_count: null, uncertain_nearby_camera_count: null, exposure_count: null, generated_by: "baseline", detour_bound_seconds: null, counting_method_version: null, camera_scope: "all_alpr", camera_snapshot_id: null, camera_source_as_of: null, camera_downloaded_at: null, road_graph_version: "g", assessment_coverage_status: "not_assessed", search_status: "not_run", warnings: [], maneuvers: [{ instruction: "Drive east.", verbal_pre_transition_instruction: null, street_names: [], begin_street_names: [], length_meters: 6423, time_seconds: 618, type: 1, type_name: "start", begin_shape_index: 0, end_shape_index: 1, roundabout_exit_count: null, toll: false, highway: false }], has_highway: false, has_toll: false, engine_candidate: "primary-0", assessment: null }],
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

let planHandler: () => Promise<Response>;

beforeEach(() => {
  planHandler = async () => jsonResponse(planBody);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/region")) return jsonResponse(region);
      if (url.endsWith("/api/v1/health/data")) return jsonResponse(health);
      if (url.endsWith("/api/v1/geocode")) {
        const body = JSON.parse(String(init?.body));
        const [lat, lon] = body.query.split(",").map(Number);
        return jsonResponse({ query_kind: "coordinates", provider: "coordinates", candidates: [{ label: `Coordinates ${lat}, ${lon}`, lat, lon, source: "coordinates", category: "coordinates", importance: null, inside_service_boundary: true }] });
      }
      if (url.endsWith("/api/v1/routes/plan")) {
        const response = await planHandler();
        if (init?.signal?.aborted) throw new DOMException("aborted", "AbortError");
        return response;
      }
      throw new Error(`unexpected fetch ${url}`);
    }),
  );
});

async function confirmBothEndpoints() {
  const start = screen.getByLabelText("Start") as HTMLInputElement;
  fireEvent.change(start, { target: { value: "39.7530, -105.0002" } });
  fireEvent.submit(start.closest("form")!);
  const destination = screen.getByLabelText("Destination") as HTMLInputElement;
  fireEvent.change(destination, { target: { value: "39.7503, -104.9500" } });
  fireEvent.submit(destination.closest("form")!);
  await waitFor(() => expect(screen.getByTestId("plan-button")).toBeEnabled());
}

describe("Planner experience (M6)", () => {
  it("fills the start from the device location after one explicit click, and labels it as an estimate", async () => {
    Object.defineProperty(window.navigator, "geolocation", {
      configurable: true,
      value: { getCurrentPosition: (ok: (position: { coords: { latitude: number; longitude: number; accuracy: number } }) => void) => ok({ coords: { latitude: 39.753, longitude: -105.0002, accuracy: 25 } }) },
    });
    render(<Planner />);
    await screen.findByText("Standard route");
    fireEvent.click(screen.getByTestId("origin-use-location"));
    await screen.findByText(/My location \(device estimate, about 25 m accuracy\)/);
    expect(screen.getByText(/Asks the browser for your position once/)).toBeInTheDocument();
  });

  it("explains a denied location permission without leaving the user stuck", async () => {
    Object.defineProperty(window.navigator, "geolocation", {
      configurable: true,
      value: { getCurrentPosition: (_ok: unknown, fail: (error: { code: number; PERMISSION_DENIED: number }) => void) => fail({ code: 1, PERMISSION_DENIED: 1 }) },
    });
    render(<Planner />);
    await screen.findByText("Standard route");
    fireEvent.click(screen.getByTestId("origin-use-location"));
    await screen.findByText(/Location permission was denied/);
  });

  it("cancelling is an explicit state and the late answer is ignored", async () => {
    let release: (() => void) | null = null;
    planHandler = () => new Promise<Response>((resolve) => {
      release = () => resolve(jsonResponse(planBody));
    });
    render(<Planner />);
    await screen.findByText("Standard route");
    await confirmBothEndpoints();
    fireEvent.click(screen.getByTestId("plan-button"));
    await screen.findByTestId("cancel-button");
    fireEvent.click(screen.getByTestId("cancel-button"));
    await screen.findByTestId("plan-cancelled");
    release!();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByTestId("route-cards")).not.toBeInTheDocument();
    expect(screen.getByTestId("plan-cancelled")).toBeInTheDocument();
  });

  it("no route at all is a distinct state, and a successful plan moves focus to the results", async () => {
    planHandler = async () => jsonResponse({ error: { code: "NO_DRIVABLE_ROUTE", message: "No drivable route was found between these points.", details: { engine_error_code: 171 } }, request_id: "r" }, 422);
    render(<Planner />);
    await screen.findByText("Standard route");
    await confirmBothEndpoints();
    fireEvent.click(screen.getByTestId("plan-button"));
    const noRoute = await screen.findByTestId("state-no-route");
    expect(noRoute).toHaveTextContent("No route at all");
    expect(noRoute).toHaveTextContent("No drivable route was found between these points.");
    expect(screen.queryByTestId("plan-error")).not.toBeInTheDocument();

    planHandler = async () => jsonResponse(planBody);
    fireEvent.click(screen.getByTestId("plan-button"));
    await screen.findByTestId("route-cards");
    await waitFor(() => expect(document.activeElement?.id).toBe("route-options-heading"));
    expect(screen.getByTestId("result-state")).toHaveAttribute("data-state", "unknown");
    expect(screen.getByTestId("directions-summary")).toHaveTextContent("Standard route: 1 step");

    fireEvent.click(screen.getByTestId("clear-trip"));
    expect(screen.queryByTestId("route-cards")).not.toBeInTheDocument();
    expect((screen.getByLabelText("Start") as HTMLInputElement).value).toBe("");
  });
});
