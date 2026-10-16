"use client";

import { useCallback, useEffect, useState } from "react";
import { api, describeError } from "@/lib/api/client";
import type { DataHealth } from "@/lib/api/types";
import { formatTimestamp } from "@/lib/format";

export function DataHealthPanel() {
  const [health, setHealth] = useState<DataHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setHealth(await api.dataHealth());
      setError(null);
    } catch (err) {
      setError(describeError(err).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const snapshot = health?.snapshot ?? null;
  return (
    <details className="section" data-testid="data-health">
      <summary>Data health</summary>
      <div className="row">
        <button type="button" className="btn btn-small" onClick={() => void load()} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh view"}
        </button>
        <span className="disclaimer">Shows the state of public data; it does not trigger a sync.</span>
      </div>
      {error && <div className="notice notice-error">{error}</div>}
      {health && (
        <dl className="kv">
          <dt>Camera snapshot</dt>
          <dd>{snapshot ? snapshot.snapshot_id : "none loaded yet"}</dd>
          <dt>Source data as of</dt>
          <dd>{snapshot ? formatTimestamp(snapshot.timestamp_osm_base) : "n/a"}</dd>
          <dt>Downloaded</dt>
          <dd>{snapshot ? formatTimestamp(snapshot.downloaded_at) : "n/a"}</dd>
          <dt>Mapped ALPR records</dt>
          <dd>{snapshot ? `${snapshot.alpr_count} (Flock ${snapshot.flock_count}, manufacturer unknown ${snapshot.unknown_manufacturer_count})` : "n/a"}</dd>
          <dt>Freshness</dt>
          <dd className={health.staleness.is_stale ? "notice-warn" : "notice-ok"}>
            {health.staleness.is_stale ? `stale (${health.staleness.age_hours ?? "?"} h old, limit ${health.staleness.stale_after_hours} h)` : `fresh (${health.staleness.age_hours ?? "?"} h old)`}
          </dd>
          <dt>Last sync</dt>
          <dd>{health.last_sync ? `${String(health.last_sync.status)} at ${formatTimestamp(String(health.last_sync.finished_at ?? health.last_sync.started_at))}` : "never"}</dd>
          <dt>Last failure</dt>
          <dd>{health.last_failure ? `${String(health.last_failure.status)}: ${String(health.last_failure.message ?? "")}` : "none"}</dd>
          <dt>Routing graph</dt>
          <dd>
            {health.router.available ? "available" : `unavailable${health.router.message ? ` (${health.router.message})` : ""}`}
            {health.router.tileset_last_modified ? `, built ${formatTimestamp(health.router.tileset_last_modified)}` : ""}
          </dd>
          <dt>Road data as of</dt>
          <dd>{formatTimestamp(health.router.extract_data_timestamp)}</dd>
          <dt>Address search</dt>
          <dd>{health.geocoder.configured ? (health.geocoder.available ? `available (${health.geocoder.provider}, data ${formatTimestamp(health.geocoder.data_updated)})` : `configured but unavailable`) : "not configured"}</dd>
          <dt>Service boundary</dt>
          <dd>{health.service_boundary_id}</dd>
          <dt>Data envelope</dt>
          <dd>{health.envelope_id}</dd>
          <dt>Basemap</dt>
          <dd>{health.basemap.id}</dd>
        </dl>
      )}
      <p className="disclaimer">Counts describe mapped OpenStreetMap records, not physical devices.</p>
    </details>
  );
}
