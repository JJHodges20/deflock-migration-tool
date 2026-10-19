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
  capabilities: { geocoder_configured: false, geocoder_provider: "none", routing_provider: "valhalla", camera_source_adapter: "overpass_bounded", camera_assessment: "not_implemented_in_m1", coordinate_input: true, map_pins: true },
  profiles: {
    standard: { label: "Standard route", description: "Fastest baseline.", max_extra_seconds: null, max_relative_factor: null },
    balanced: { label: "Balanced", description: "", max_extra_seconds: 600, max_relative_factor: 1.5 },
    fewest_mapped: { label: "Fewest mapped cameras found", description: "", max_extra_seconds: 1200, max_relative_factor: 1.75 },
  },
  camera_scopes: ["all_alpr", "flock_only"],
  attributions: ["© OpenStreetMap contributors"],
  disclaimer: "Routes are advisory.",
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("Planner shell", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/api/v1/region")) return jsonResponse(region);
        if (url.endsWith("/api/v1/health/data")) return jsonResponse({ region_id: "denver", service_boundary_id: "denver-service-v1", envelope_id: "denver-envelope-v1-20km", config_version: 1, camera_source: {}, snapshot: null, inventory: { retain_missing_hours: 72, unresolved_disappearance: "retain_as_uncertain", keep_superseded_snapshots: 30, keep_quarantined_snapshots: 10, pending_review: [] }, last_sync: null, last_failure: null, recent_syncs: [], staleness: { is_stale: true, stale_after_hours: 48, age_hours: null, message: "no camera snapshot yet" }, router: { available: true, version: "3.9.1", tileset_last_modified: null, has_tiles: true, graph_id: "g", extract_data_timestamp: "2026-10-14T20:21:12Z", message: null }, geocoder: { configured: false, available: false, provider: "none", data_updated: null, message: null }, basemap: { id: "b", attribution: "", max_zoom: 15 }, database: { available: false }, generated_at: "" });
        if (url.endsWith("/api/v1/geocode")) {
          const body = JSON.parse(String(init?.body));
          if (/^\s*-?\d/.test(body.query)) {
            const [lat, lon] = body.query.split(",").map(Number);
            return jsonResponse({ query_kind: "coordinates", provider: "coordinates", candidates: [{ label: `Coordinates ${lat}, ${lon}`, lat, lon, source: "coordinates", category: "coordinates", importance: null, inside_service_boundary: true }] });
          }
          return jsonResponse({ error: { code: "GEOCODER_NOT_CONFIGURED", message: "Address search is not configured.", details: {} }, request_id: "r" }, 503);
        }
        throw new Error(`unexpected fetch ${url}`);
      }),
    );
  });

  it("keeps typed input, confirms coordinates, and explains missing address search", async () => {
    render(<Planner />);
    await screen.findByText("Denver, Colorado (pilot) · compare routes by mapped ALPR cameras");
    const start = screen.getByLabelText("Start") as HTMLInputElement;
    fireEvent.change(start, { target: { value: "Union Station" } });
    expect(start.value).toBe("Union Station");
    fireEvent.submit(start.closest("form")!);
    await screen.findByText(/Address search is not configured/);

    fireEvent.change(start, { target: { value: "39.7530, -105.0002" } });
    fireEvent.submit(start.closest("form")!);
    await screen.findByText(/Confirmed:/);
    expect(screen.getByTestId("plan-button")).toBeDisabled();

    const destination = screen.getByLabelText("Destination") as HTMLInputElement;
    fireEvent.change(destination, { target: { value: "39.7503, -104.9500" } });
    fireEvent.submit(destination.closest("form")!);
    await waitFor(() => expect(screen.getByTestId("plan-button")).toBeEnabled());

    fireEvent.click(screen.getByText("Swap start and destination"));
    expect((screen.getByLabelText("Start") as HTMLInputElement).value).toContain("39.7503");
  });

  it("shows the freshness and privacy strip and a units toggle", async () => {
    render(<Planner />);
    await screen.findByText("Standard route");
    const strip = screen.getByTestId("data-status");
    expect(strip).toHaveTextContent("Road data");
    expect(strip).toHaveTextContent("never stored");
    expect(strip).toHaveTextContent("not configured");
    const miles = screen.getByRole("button", { name: "mi" });
    fireEvent.click(miles);
    expect(miles).toHaveAttribute("aria-pressed", "true");
  });

  it("offers the scope control and explains the three compared routes with the extra-time limit", async () => {
    render(<Planner />);
    await screen.findByText("Standard route");
    const compared = screen.getByTestId("compare-list");
    expect(compared).toHaveTextContent("Balanced");
    expect(compared).toHaveTextContent("within your limit: 10 min extra or 1.50 × the standard time");
    expect(compared).toHaveTextContent("Fewest mapped cameras found");
    expect(compared).toHaveTextContent("20 min extra or 1.75 × the standard time, and never tighter than your limit");
    expect(screen.queryByRole("radio", { name: /Balanced/ })).not.toBeInTheDocument(); // all three are always compared
    expect(screen.getByLabelText(/All mapped ALPRs/)).toBeChecked();
    fireEvent.click(screen.getByLabelText(/Flock-tagged ALPRs only/));
    expect(screen.getByLabelText(/Flock-tagged ALPRs only/)).toBeChecked();
    expect(screen.getByText(/Confirm a start and a destination/)).toBeInTheDocument();
    expect(screen.getByText("Data health")).toBeInTheDocument();
  });
});
