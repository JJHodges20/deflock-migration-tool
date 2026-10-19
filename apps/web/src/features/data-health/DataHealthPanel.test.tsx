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
  scheduler: { interval_hours: 6, manual_refresh_cooldown_minutes: 30, last_trigger: "scheduled", runs_only_while_stack_is_up: true, note: "", next_due_at: "2026-10-16T07:14:23Z", due_in_seconds: 15000, overdue: false, cooldown_remaining_seconds: 0, state: "on schedule" },
  provider_policy: { endpoint: "https://overpass-api.de/api/interpreter", query: "one fixed query over the camera-data envelope; never derived from a trip", one_request_at_a_time: true, refresh_interval_hours: 6, identifies_application: true, timeout_seconds: 180, pause_after_rate_limit_seconds: 30, max_attempts: 3, backoff_seconds: 5, no_endpoint_rotation: true },
  router: { available: true, version: "3.9.1", tileset_last_modified: "2026-10-15T23:22:43Z", has_tiles: true, graph_id: "g", extract_data_timestamp: "2026-10-14T20:21:12Z", rebuild_cadence: "weekly", message: null },
  geocoder: { configured: true, available: true, provider: "nominatim_local", data_updated: "2026-10-14T20:20:43+00:00", message: "OK" },
  basemap: { id: "protomaps-20261015-denver-envelope-z15", attribution: "", max_zoom: 15 },
  database: { available: true },
  generated_at: "2026-10-16T03:00:00Z",
};

const metrics = {
  uptime_seconds: 7200,
  requests: { "/api/v1/routes/plan": { count: 12, rejected_4xx: 1, errors_5xx: 0, samples: 12, p50_ms: 180, p95_ms: 720, max_ms: 900 } },
  plans: { count: 11, by_search_status: { completed: 11 }, options_returned: { "2": 11 }, routing_calls_total: 23, errors_by_code: {}, elapsed_p50_ms: 150, elapsed_p95_ms: 700, elapsed_max_ms: 800 },
  meaning: "Counts and latency summaries kept in memory since the process started; no trip, address, coordinate, or geometry is recorded.",
  process: { version: "0.1.0", rss_mb: 140.5 },
  storage: { available: true, database_bytes: 95_000_000, raw_snapshot_bytes: 4_700_000, camera_record_rows: 9300 },
};
const diffs = {
  region_id: "denver",
  diffs: [
    { snapshot_id: "ovp-denver-20261016T011204Z-f45379e3", previous_snapshot_id: "ovp-denver-older", snapshot_state: "active", source_as_of: "2026-10-16T01:12:04Z", downloaded_at: "2026-10-16T01:14:23Z", promoted_at: "2026-10-16T01:14:23Z", added: 2, changed: 5, missing: 3, reappeared: 1, carried: 3, expired: 0, alpr_count: 1540, in_envelope_alpr_count: 1324, review_note: null },
    { snapshot_id: "ovp-denver-older", previous_snapshot_id: null, snapshot_state: "superseded", source_as_of: "2026-10-15T20:00:00Z", downloaded_at: "2026-10-15T20:02:00Z", promoted_at: "2026-10-15T20:02:00Z", added: 1591, changed: 0, missing: 0, reappeared: 0, carried: 0, expired: 0, alpr_count: 1540, in_envelope_alpr_count: 1324, review_note: "rolled back to: corridor check" },
  ],
  meaning: "Added means newly mapped records in the source, not cameras installed that day.",
};

describe("DataHealthPanel", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
        if (url.includes("/api/v1/health/metrics")) return json(metrics);
        if (url.includes("/api/v1/cameras/diffs")) return json(diffs);
        return json(health);
      }),
    );
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

  it("shows the scheduler, the source policy, the snapshot history, and trip-free service metrics (M7)", async () => {
    render(<DataHealthPanel />);
    await screen.findByText("ovp-denver-20261016T011204Z-f45379e3");
    const scheduler = await screen.findByTestId("scheduler");
    expect(scheduler).toHaveTextContent("every 6 h while the stack runs");
    expect(scheduler).toHaveTextContent("in 4.2 h");
    expect(scheduler).toHaveTextContent("on schedule");
    expect(scheduler).toHaveTextContent("manual refresh available (shared 30 min cooldown)");
    expect(screen.getByTestId("provider-policy")).toHaveTextContent("never derived from a trip; one request at a time");
    expect(screen.getByTestId("provider-policy")).toHaveTextContent("pause 30 s after a rate limit, at most 3 attempts, no endpoint rotation");
    const history = await screen.findByTestId("diff-history");
    expect(history.querySelectorAll("li")).toHaveLength(2);
    expect(history).toHaveTextContent("rolled back to: corridor check");
    const service = await screen.findByTestId("service-metrics");
    expect(service).toHaveTextContent("up 2.0 h · 11 plans (median 180 ms, p95 720 ms, 1 rejected, 0 failed) · 23 routing calls · API memory 140.5 MB");
    expect(service).toHaveTextContent("database 95.0 MB, raw snapshots 4.7 MB, 9300 record rows");
    expect(service).toHaveTextContent("no trip, address, coordinate, or geometry is recorded");
    expect(screen.queryByTestId("scheduler-overdue")).not.toBeInTheDocument();
    expect(screen.getByText(/rebuild: weekly/)).toBeInTheDocument();
  });
});
