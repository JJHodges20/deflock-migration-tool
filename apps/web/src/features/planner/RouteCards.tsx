"use client";

import type { PlanResponse, RegionResponse, RouteOptionOut } from "@/lib/api/types";
import { formatDistance, formatDuration, formatSignedDuration, formatTimestamp } from "@/lib/format";

interface Props {
  result: PlanResponse;
  region: RegionResponse | null;
  selectedRouteId: string | null;
  onSelect: (routeId: string) => void;
}

function encounterText(option: RouteOptionOut): string {
  if (option.assessment_coverage_status === "not_assessed" || option.matched_camera_record_count === null) {
    return "Not assessed in this version";
  }
  if (option.matched_camera_record_count === 0) {
    return "No mapped encounters detected by this assessment";
  }
  return `${option.matched_camera_record_count} mapped`;
}

export function RouteCards({ result, region, selectedRouteId, onSelect }: Props) {
  return (
    <div className="section" data-testid="route-cards">
      <h2>Route options</h2>
      {result.warnings.length > 0 && (
        <ul className="notice notice-warn" style={{ margin: 0, paddingLeft: 24 }}>
          {result.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
      {result.options.map((option) => {
        const selected = option.route_id === selectedRouteId;
        return (
          <button key={option.route_id} type="button" className={`route-card${selected ? " selected" : ""}`} onClick={() => onSelect(option.route_id)} aria-pressed={selected} data-testid="route-card">
            <div className="labels">
              {option.profiles.map((profile) => (
                <span key={profile} className="tag tag-accent">
                  {region?.profiles[profile]?.label ?? profile}
                </span>
              ))}
              {option.has_highway && <span className="tag">uses highway</span>}
              {option.has_toll && <span className="tag">toll</span>}
            </div>
            <div className="metrics">
              <div className="metric">
                <span className="value">{formatDuration(option.estimated_duration_seconds)}</span>
                <span className="label">estimated, no live traffic</span>
              </div>
              <div className="metric">
                <span className="value">{formatDistance(option.length_meters)}</span>
                <span className="label">distance</span>
              </div>
              <div className="metric">
                <span className="value">{formatSignedDuration(option.extra_duration_seconds)}</span>
                <span className="label">versus standard</span>
              </div>
            </div>
            <dl className="kv">
              <dt>Mapped camera encounters</dt>
              <dd>{encounterText(option)}</dd>
              <dt>Uncertain nearby matches</dt>
              <dd>{option.uncertain_nearby_camera_count ?? "not assessed"}</dd>
              <dt>Assessment</dt>
              <dd>{option.assessment_coverage_status.replace("_", " ")}</dd>
              <dt>Camera data</dt>
              <dd>{option.camera_snapshot_id ? `snapshot of ${formatTimestamp(option.camera_source_as_of)}` : "no snapshot loaded"}</dd>
              <dt>Road graph</dt>
              <dd>{option.road_graph_version}</dd>
            </dl>
          </button>
        );
      })}
      <p className="disclaimer">{result.disclaimer}</p>
    </div>
  );
}
