import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import type { DataHealth } from "@/lib/api/types";
import { DataHealthPanel } from "./DataHealthPanel";

const health: DataHealth = {
  region_id: "denver",
  service_boundary_id: "denver-service-v1",
  envelope_id: "denver-envelope-v1-20km",
  config_version: 1,
  camera_source: {},
  snapshot: {
    snapshot_id: "ovp-denver-20261016T011204Z-f45379e3",
    timestamp_osm_base: "2026-10-16T01:12:04Z",
    downloaded_at: "2026-10-16T01:14:23Z",
    promoted_at: "2026-10-16T01:14:23Z",
    element_count: 1593,
    record_count: 1596,
    alpr_count: 1540,
    flock_count: 1263,
    unknown_manufacturer_count: 157,
    in_envelope_alpr_count: 1324,
    no_longer_mapped_count: 3,
    previous_active_snapshot_id: "ovp-denver-older",
    parser_version: "normalize-1.1",
    quality: {},
    review_note: null,
    diff: { added: 2, changed: 5, missing: 3, reappeared: 1, carried: 3, expired: 0 },
    counts_meaning: "records",
  },
  inventory: {
    retain_missing_hours: 72,
    unresolved_disappearance: "retain_as_uncertain",
    keep_superseded_snapshots: 30,
    keep_quarantined_snapshots: 10,
    pending_review: [{ snapshot_id: "ovp-denver-quarantined", created_at: "2026-10-16T02:00:00Z", reason: "ALPR count dropped by 80%", alpr_count: 300 }],
    retained_snapshots: 4,
  },
  last_sync: { status: "succeeded", trigger: "scheduled", started_at: "2026-10-16T01:12:04Z", finished_at: "2026-10-16T01:14:23Z", snapshot_id: "x", http_status: 200, attempts: 2, added: 2, changed: 5, no_longer_present: 3, message: "promoted" },
  last_failure: null,
  recent_syncs: [
    { status: "succeeded", trigger: "scheduled", started_at: "2026-10-16T01:12:04Z", finished_at: "2026-10-16T01:14:23Z", snapshot_id: "x", http_status: 200, attempts: 2, added: 2, changed: 5, no_longer_present: 3, message: "promoted" },
    { status: "quarantined", trigger: "manual", started_at: "2026-10-16T02:00:00Z", finished_at: "2026-10-16T02:01:00Z", snapshot_id: "q", http_status: 200, attempts: 1, added: 0, changed: 0, no_longer_present: 1200, message: "quarantined" },
  ],
  staleness: { age_hours: 1.5, stale_after_hours: 48, is_stale: false },
  router: { available: true, version: "3.9.1", tileset_last_modified: "2026-10-15T23:22:43Z", has_tiles: true, graph_id: "g", extract_data_timestamp: "2026-10-14T20:21:12Z", message: null },
  geocoder: { configured: true, available: true, provider: "nominatim_local", data_updated: "2026-10-14T20:20:43+00:00", message: "OK" },
  basemap: { id: "protomaps-20261015-denver-envelope-z15", attribution: "", max_zoom: 15 },
  database: { available: true },
  generated_at: "2026-10-16T03:00:00Z",
};

describe("DataHealthPanel", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(health), { status: 200, headers: { "Content-Type": "application/json" } })));
  });

  it("shows inventory counts, the diff, pending review, and recent syncs", async () => {
    render(<DataHealthPanel />);
    await screen.findByText("ovp-denver-20261016T011204Z-f45379e3");
    expect(screen.getByText("1324 of 1540")).toBeInTheDocument();
    expect(screen.getByText("3 (kept up to 72 h)")).toBeInTheDocument();
    expect(screen.getByText("+2 added, 5 changed, 3 no longer present, 1 reappeared")).toBeInTheDocument();
    expect(screen.getByTestId("pending-review")).toHaveTextContent("ALPR count dropped by 80%");
    expect(screen.getByTestId("recent-syncs").querySelectorAll("li")).toHaveLength(2);
    expect(screen.getByText(/available \(nominatim_local/)).toBeInTheDocument();
    expect(screen.getByText(/not physically removed/)).toBeInTheDocument();
  });
});
