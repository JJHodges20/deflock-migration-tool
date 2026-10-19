"use client";

import type { DataHealth, RegionResponse } from "@/lib/api/types";
import { formatTimestamp } from "@/lib/format";

interface Props {
  region: RegionResponse | null;
  health: DataHealth | null;
}

/** Always-visible freshness and privacy disclosures (roadmap M3 gate). */
export function DataStatusStrip({ region, health }: Props) {
  const snapshot = health?.snapshot ?? null;
  const geocoder = health?.geocoder;
  const addressSearch = !geocoder || !geocoder.configured ? "not configured (coordinates and map pins work)" : geocoder.available ? "local only, on this computer" : "configured, not available right now";
  return (
    <div className="status-strip" data-testid="data-status">
      <span>
        <strong>Road data</strong> as of {region ? formatTimestamp(region.routing_graph.extract_data_timestamp) : "unknown"}
      </span>
      <span>
        <strong>Camera records</strong> {snapshot ? `snapshot of ${formatTimestamp(snapshot.timestamp_osm_base)}${health?.staleness?.is_stale ? " (stale)" : ""}` : "none loaded"}
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
