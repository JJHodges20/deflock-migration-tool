"use client";

import { useCallback, useEffect, useState } from "react";
import { api, describeError } from "@/lib/api/client";
import type { DataHealth, DiffHistoryResponse, ServiceMetrics, SyncJobView } from "@/lib/api/types";
import { formatTimestamp } from "@/lib/format";

function syncLine(job: SyncJobView): string {
  const when = formatTimestamp(job.finished_at ?? job.started_at);
  const counts = job.added !== null && job.added !== undefined ? ` (+${job.added} added, ${job.changed ?? 0} changed, ${job.no_longer_present ?? 0} no longer present)` : "";
  return `${job.status} · ${job.trigger} · ${when}${counts}`;
}

function dueText(seconds: number): string {
  if (seconds <= 0) return "now";
  if (seconds < 3600) return `in ${Math.round(seconds / 60)} min`;
  return `in ${(seconds / 3600).toFixed(1)} h`;
}

function bytesText(bytes: number | undefined): string {
  if (bytes === undefined || bytes === null) return "n/a";
  if (bytes < 1_000_000) return `${Math.round(bytes / 1000)} kB`;
  if (bytes < 1_000_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  return `${(bytes / 1_000_000_000).toFixed(2)} GB`;
}

export function DataHealthPanel() {
  const [health, setHealth] = useState<DataHealth | null>(null);
  const [diffs, setDiffs] = useState<DiffHistoryResponse | null>(null);
  const [metrics, setMetrics] = useState<ServiceMetrics | null>(null);
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
    // Secondary views: optional, never block the health view.
    api
      .diffHistory(8)
      .then(setDiffs)
      .catch(() => setDiffs(null));
    api
      .metrics()
      .then(setMetrics)
      .catch(() => setMetrics(null));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const snapshot = health?.snapshot ?? null;
  const inventory = health?.inventory ?? { retain_missing_hours: 0, unresolved_disappearance: "", keep_superseded_snapshots: 0, keep_quarantined_snapshots: 0, pending_review: [] };
  const pending = inventory.pending_review ?? [];
  const recentSyncs = health?.recent_syncs ?? [];
  const scheduler = health?.scheduler;
  const policy = health?.provider_policy;
  const planRequests = metrics?.requests["/api/v1/routes/plan"];
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
      {scheduler && scheduler.overdue && snapshot && (
        <div className="notice notice-warn" data-testid="scheduler-overdue">
          The scheduled camera sync is overdue ({scheduler.state}). Scheduled syncs run only while the stack is up; start it with <code>docker compose up</code> or refresh with the operator script.
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
          {scheduler && (
            <>
              <dt>Scheduled sync</dt>
              <dd data-testid="scheduler">
                every {scheduler.interval_hours} h while the stack runs · next {scheduler.next_due_at ? `${dueText(scheduler.due_in_seconds)} (${formatTimestamp(scheduler.next_due_at)})` : "as soon as the worker runs"} · {scheduler.state}
                {scheduler.cooldown_remaining_seconds > 0 ? ` · manual refresh cooldown: ${Math.ceil(scheduler.cooldown_remaining_seconds / 60)} min left` : ` · manual refresh available (shared ${scheduler.manual_refresh_cooldown_minutes} min cooldown)`}
              </dd>
            </>
          )}
          {policy && (
            <>
              <dt>Source policy</dt>
              <dd data-testid="provider-policy">
                {policy.query}; one request at a time, identified as this application; pause {policy.pause_after_rate_limit_seconds} s after a rate limit, at most {policy.max_attempts} attempts, no endpoint rotation
              </dd>
            </>
          )}
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
          {diffs && diffs.diffs.length > 0 && (
            <>
              <dt>Snapshot history</dt>
              <dd>
                <ul style={{ margin: 0, paddingLeft: 16 }} data-testid="diff-history">
                  {diffs.diffs.map((d) => (
                    <li key={d.snapshot_id}>
                      {formatTimestamp(d.source_as_of)} · {d.snapshot_state} · +{d.added} added, {d.changed} changed, {d.missing} no longer present{d.carried ? `, ${d.carried} carried` : ""}{d.review_note ? ` · ${d.review_note}` : ""}
                    </li>
                  ))}
                </ul>
                <span className="disclaimer">{diffs.meaning}</span>
              </dd>
            </>
          )}
          <dt>Routing graph</dt>
          <dd>
            {health.router.available ? "available" : `unavailable${health.router.message ? ` (${health.router.message})` : ""}`}
            {health.router.tileset_last_modified ? `, built ${formatTimestamp(health.router.tileset_last_modified)}` : ""}
            {health.router.rebuild_cadence ? ` · rebuild: ${health.router.rebuild_cadence}` : ""}
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
          {metrics && (
            <>
              <dt>Service since start</dt>
              <dd data-testid="service-metrics">
                up {(metrics.uptime_seconds / 3600).toFixed(1)} h · {metrics.plans.count} plan{metrics.plans.count === 1 ? "" : "s"}
                {planRequests ? ` (median ${planRequests.p50_ms ?? "?"} ms, p95 ${planRequests.p95_ms ?? "?"} ms, ${planRequests.rejected_4xx} rejected, ${planRequests.errors_5xx} failed)` : ""}
                {metrics.plans.routing_calls_total ? ` · ${metrics.plans.routing_calls_total} routing calls` : ""}
                {metrics.process.rss_mb ? ` · API memory ${metrics.process.rss_mb} MB` : ""}
                {metrics.storage.available ? ` · database ${bytesText(metrics.storage.database_bytes)}, raw snapshots ${bytesText(metrics.storage.raw_snapshot_bytes)}, ${metrics.storage.camera_record_rows} record rows` : ""}
                <span className="disclaimer"> {metrics.meaning}</span>
              </dd>
            </>
          )}
        </dl>
      )}
      <p className="disclaimer">Counts describe mapped OpenStreetMap records, not physical devices. "No longer present" means absent from a later source query, not physically removed.</p>
    </details>
  );
}
