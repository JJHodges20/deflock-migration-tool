"use client";

import type { DataHealth, RegionResponse } from "@/lib/api/types";
import { describeAge } from "@/lib/age";
import { formatTimestamp } from "@/lib/format";

interface Props {
  region: RegionResponse | null;
  health: DataHealth | null;
  now?: Date;
}

/** Always-visible freshness and privacy disclosures (roadmap M3 gate) with data-age badges (M6). */
export function DataStatusStrip({ region, health, now = new Date() }: Props) {
  const snapshot = health?.snapshot ?? null;
  const geocoder = health?.geocoder;
  const addressSearch = !geocoder || !geocoder.configured ? "not configured (coordinates and map pins work)" : geocoder.available ? "local only, on this computer" : "configured, not available right now";
  const staleAfter = health?.staleness?.stale_after_hours ?? null;
  const cameraAge = describeAge(snapshot?.downloaded_at ?? null, now, staleAfter);
  const cameraStale = Boolean(health?.staleness?.is_stale) || cameraAge.stale;
  const roadAge = describeAge(region?.routing_graph.extract_data_timestamp ?? null, now);
  const pending = health?.inventory?.pending_review?.length ?? 0;
  const emptyInventory = snapshot !== null && snapshot.in_envelope_alpr_count === 0;
  return (
    <div className="status-strip" data-testid="data-status">
      <span>
        <strong>Road data</strong> as of {region ? formatTimestamp(region.routing_graph.extract_data_timestamp) : "unknown"}
        {region && <span className="badge" data-testid="road-age">{roadAge.text}</span>}
      </span>
      <span>
        <strong>Camera records</strong> {snapshot ? `snapshot of ${formatTimestamp(snapshot.timestamp_osm_base)}` : "none loaded"}
        {snapshot && <span className={`badge${cameraStale ? " badge-warn" : ""}`} data-testid="camera-age">{cameraStale ? `stale, ${cameraAge.text}` : `downloaded ${cameraAge.text}`}</span>}
        {!snapshot && <span className="badge badge-warn">unknown data</span>}
        {emptyInventory && <span className="badge badge-warn" data-testid="empty-inventory">no records inside the assessed area</span>}
        {pending > 0 && <span className="badge badge-warn" data-testid="pending-review-badge">{pending} snapshot{pending > 1 ? "s" : ""} awaiting operator review</span>}
      </span>
      <span>
        <strong>Address search</strong> {addressSearch}
      </span>
      <span>
        <strong>Privacy</strong> trips are planned on this computer and never stored
      </span>
    </div>
  );
}
