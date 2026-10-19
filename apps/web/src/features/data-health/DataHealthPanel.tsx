"use client";

import { useCallback, useEffect, useState } from "react";
import { api, describeError } from "@/lib/api/client";
import type { DataHealth, SyncJobView } from "@/lib/api/types";
import { formatTimestamp } from "@/lib/format";

function syncLine(job: SyncJobView): string {
  const when = formatTimestamp(job.finished_at ?? job.started_at);
  const counts = job.added !== null && job.added !== undefined ? ` (+${job.added} added, ${job.changed ?? 0} changed, ${job.no_longer_present ?? 0} no longer present)` : "";
  return `${job.status} · ${job.trigger} · ${when}${counts}`;
}

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
  const inventory = health?.inventory ?? { retain_missing_hours: 0, unresolved_disappearance: "", keep_superseded_snapshots: 0, keep_quarantined_snapshots: 0, pending_review: [] };
  const pending = inventory.pending_review ?? [];
  const recentSyncs = health?.recent_syncs ?? [];
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
      {pending.length > 0 && (
        <div className="notice notice-warn" data-testid="pending-review">
          {pending.length} snapshot{pending.length > 1 ? "s" : ""} quarantined and waiting for operator review (the last good snapshot stays active):
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {pending.map((p) => (
              <li key={p.snapshot_id}>
                {p.snapshot_id}: {p.reason ?? "no reason recorded"}
              </li>
            ))}
          </ul>
        </div>
      )}
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
          <dt>Inside the assessed area</dt>
          <dd>{snapshot ? `${snapshot.in_envelope_alpr_count} of ${snapshot.alpr_count}` : "n/a"}</dd>
          <dt>No longer mapped, retained as uncertain</dt>
          <dd>{snapshot ? `${snapshot.no_longer_mapped_count} (kept up to ${inventory.retain_missing_hours} h)` : "n/a"}</dd>
          <dt>Changes in this snapshot</dt>
          <dd>{snapshot?.diff ? `+${snapshot.diff.added} added, ${snapshot.diff.changed} changed, ${snapshot.diff.missing} no longer present, ${snapshot.diff.reappeared} reappeared` : "n/a"}</dd>
          <dt>Freshness</dt>
          <dd className={health.staleness.is_stale ? "notice-warn" : "notice-ok"}>
            {health.staleness.is_stale ? `stale (${health.staleness.age_hours ?? "?"} h old, limit ${health.staleness.stale_after_hours} h)` : `fresh (${health.staleness.age_hours ?? "?"} h old)`}
          </dd>
          <dt>Last sync</dt>
          <dd>{health.last_sync ? syncLine(health.last_sync) : "never"}</dd>
          <dt>Last failure</dt>
          <dd>{health.last_failure ? `${health.last_failure.status}: ${health.last_failure.message ?? ""}` : "none"}</dd>
          <dt>Recent syncs</dt>
          <dd>
            {recentSyncs.length === 0 ? (
              "none"
            ) : (
              <ul style={{ margin: 0, paddingLeft: 16 }} data-testid="recent-syncs">
                {recentSyncs.map((job, index) => (
                  <li key={`${job.started_at}-${index}`}>{syncLine(job)}</li>
                ))}
              </ul>
            )}
          </dd>
          <dt>Snapshots retained</dt>
          <dd>{inventory.retained_snapshots ?? "n/a"} (keeps {inventory.keep_superseded_snapshots} superseded, {inventory.keep_quarantined_snapshots} quarantined)</dd>
          <dt>Routing graph</dt>
          <dd>
            {health.router.available ? "available" : `unavailable${health.router.message ? ` (${health.router.message})` : ""}`}
            {health.router.tileset_last_modified ? `, built ${formatTimestamp(health.router.tileset_last_modified)}` : ""}
          </dd>
          <dt>Road data as of</dt>
          <dd>{formatTimestamp(health.router.extract_data_timestamp)}</dd>
          <dt>Address search</dt>
          <dd>{health.geocoder.configured ? (health.geocoder.available ? `available (${health.geocoder.provider}, data ${formatTimestamp(health.geocoder.data_updated)})` : "configured but unavailable") : "not configured"}</dd>
          <dt>Service boundary</dt>
          <dd>{health.service_boundary_id}</dd>
          <dt>Data envelope</dt>
          <dd>{health.envelope_id}</dd>
          <dt>Basemap</dt>
          <dd>{health.basemap.id}</dd>
        </dl>
      )}
      <p className="disclaimer">Counts describe mapped OpenStreetMap records, not physical devices. "No longer present" means absent from a later source query, not physically removed.</p>
    </details>
  );
}
