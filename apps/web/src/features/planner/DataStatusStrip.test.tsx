import { render, screen } from "@testing-library/react";
import type { DataHealth, RegionResponse } from "@/lib/api/types";
import { DataStatusStrip } from "./DataStatusStrip";

const now = new Date("2026-10-19T20:00:00Z");
const region = { routing_graph: { id: "g", extract_data_timestamp: "2026-10-14T20:21:12Z", engine_image: "v" } } as RegionResponse;

function health(overrides: Partial<DataHealth> = {}): DataHealth {
  return {
    region_id: "denver",
    service_boundary_id: "b",
    envelope_id: "e",
    config_version: 1,
    camera_source: {},
    snapshot: { snapshot_id: "snap-1", timestamp_osm_base: "2026-10-19T14:46:21Z", downloaded_at: "2026-10-19T15:00:00Z", promoted_at: null, element_count: 1, record_count: 1, alpr_count: 1548, flock_count: 1, unknown_manufacturer_count: 0, in_envelope_alpr_count: 1285, no_longer_mapped_count: 0, previous_active_snapshot_id: null, parser_version: "p", quality: {}, review_note: null, diff: null, counts_meaning: "" },
    inventory: { retain_missing_hours: 72, unresolved_disappearance: "retain_as_uncertain", keep_superseded_snapshots: 30, keep_quarantined_snapshots: 10, pending_review: [] },
    last_sync: null,
    last_failure: null,
    recent_syncs: [],
    staleness: { is_stale: false, stale_after_hours: 48, age_hours: 5 },
    router: { available: true, version: "3.9.1", tileset_last_modified: null, has_tiles: true, graph_id: "g", extract_data_timestamp: "2026-10-14T20:21:12Z", message: null },
    geocoder: { configured: true, available: true, provider: "nominatim_local", data_updated: null, message: null },
    basemap: { id: "b", attribution: "", max_zoom: 15 },
    database: { available: true },
    generated_at: "",
    ...overrides,
  };
}

describe("DataStatusStrip data-age badges", () => {
  it("shows fresh camera and road ages", () => {
    render(<DataStatusStrip region={region} health={health()} now={now} />);
    expect(screen.getByTestId("camera-age")).toHaveTextContent("downloaded 5 h old");
    expect(screen.getByTestId("camera-age")).not.toHaveClass("badge-warn");
    expect(screen.getByTestId("road-age")).toHaveTextContent("5 days old");
    expect(screen.queryByTestId("empty-inventory")).not.toBeInTheDocument();
    expect(screen.queryByTestId("pending-review-badge")).not.toBeInTheDocument();
  });

  it("flags stale data, an empty inventory, and snapshots awaiting review", () => {
    const h = health({ staleness: { is_stale: true, stale_after_hours: 48, age_hours: 80 } });
    h.snapshot!.downloaded_at = "2026-10-16T12:00:00Z";
    h.snapshot!.in_envelope_alpr_count = 0;
    h.inventory.pending_review = [{ snapshot_id: "q-1", created_at: "", reason: "count drop", alpr_count: 10 }];
    render(<DataStatusStrip region={region} health={h} now={now} />);
    expect(screen.getByTestId("camera-age")).toHaveTextContent("stale, 3 days old");
    expect(screen.getByTestId("camera-age")).toHaveClass("badge-warn");
    expect(screen.getByTestId("empty-inventory")).toHaveTextContent("no records inside the assessed area");
    expect(screen.getByTestId("pending-review-badge")).toHaveTextContent("1 snapshot awaiting operator review");
  });

  it("says unknown when no snapshot is loaded", () => {
    render(<DataStatusStrip region={region} health={health({ snapshot: null })} now={now} />);
    expect(screen.getByTestId("data-status")).toHaveTextContent("none loaded");
    expect(screen.getByTestId("data-status")).toHaveTextContent("unknown data");
  });
});
