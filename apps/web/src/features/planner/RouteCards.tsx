"use client";

import type { PlanResponse, RegionResponse, RouteOptionOut } from "@/lib/api/types";
import { formatDistance, formatDuration, formatSignedDuration, formatTimestamp, type Units } from "@/lib/format";
import { Encounters, summaryLine } from "./Encounters";

interface Props {
  result: PlanResponse;
  region: RegionResponse | null;
  selectedRouteId: string | null;
  units: Units;
  onSelect: (routeId: string) => void;
}

const SNAP_NOTE_THRESHOLD_M = 50;

function snapNotes(option: RouteOptionOut, units: Units): string[] {
  const notes: string[] = [];
  if (option.origin_snap_distance_meters > SNAP_NOTE_THRESHOLD_M) {
    notes.push(`The route starts ${formatDistance(option.origin_snap_distance_meters, units)} from your start point, on the nearest drivable road.`);
  }
  if (option.destination_snap_distance_meters > SNAP_NOTE_THRESHOLD_M) {
    notes.push(`The route ends ${formatDistance(option.destination_snap_distance_meters, units)} from your destination point, on the nearest drivable road.`);
  }
  return notes;
}

function coverageText(option: RouteOptionOut): string {
  const a = option.assessment;
  if (!a || a.status === "not_assessed") return a?.warnings[0] ?? "not assessed";
  if (a.status === "partial") return `partial: ${Math.round((a.coverage_fraction ?? 0) * 100)}% of the route is inside the assessed data area; counts are not complete`;
  return "complete: the whole route lies inside the assessed data area";
}

export function RouteCards({ result, region, selectedRouteId, units, onSelect }: Props) {
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
        const notes = snapNotes(option, units);
        const assessment = option.assessment;
        return (
          <div key={option.route_id} className={`route-card${selected ? " selected" : ""}`} data-testid="route-card">
            <button type="button" className="route-card-select" onClick={() => onSelect(option.route_id)} aria-pressed={selected}>
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
                  <span className="value" data-testid="route-distance">{formatDistance(option.length_meters, units)}</span>
                  <span className="label">distance</span>
                </div>
                <div className="metric">
                  <span className="value">{formatSignedDuration(option.extra_duration_seconds)}</span>
                  <span className="label">versus standard</span>
                </div>
              </div>
            </button>
            {notes.map((note) => (
              <span key={note} className="notice notice-info" data-testid="snap-note">
                {note}
              </span>
            ))}
            <dl className="kv">
              <dt>Mapped camera encounters</dt>
              <dd data-testid="encounter-summary">{summaryLine(assessment)}</dd>
              <dt>Uncertain nearby matches</dt>
              <dd>{assessment && assessment.status !== "not_assessed" ? `${assessment.uncertain_record_count ?? 0} (different or ambiguous road, no longer mapped, or outside the assessed area)` : "not assessed"}</dd>
              <dt>Records within 25 / 50 / 100 m</dt>
              <dd>{assessment && assessment.status !== "not_assessed" ? assessment.sensitivity.map((s) => s.records_within).join(" / ") : "not assessed"}</dd>
              <dt>Assessment</dt>
              <dd>{coverageText(option)}</dd>
              <dt>Camera data</dt>
              <dd>{option.camera_snapshot_id ? `snapshot of ${formatTimestamp(option.camera_source_as_of)}` : "no snapshot loaded"}</dd>
              <dt>Road graph</dt>
              <dd>{option.road_graph_version}</dd>
            </dl>
            {assessment && assessment.status !== "not_assessed" && <Encounters assessment={assessment} units={units} />}
          </div>
        );
      })}
      <p className="disclaimer">{result.disclaimer}</p>
    </div>
  );
}
