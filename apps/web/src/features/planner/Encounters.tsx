"use client";

import type { AssessmentOut, EncounterOut, EncounterStatus } from "@/lib/api/types";
import { formatDistance, type Units } from "@/lib/format";

export const STATUS_LABEL: Record<EncounterStatus, string> = {
  associated: "counted",
  nearby_unresolved: "uncertain",
  no_longer_mapped: "uncertain (no longer mapped)",
  outside_envelope: "uncertain (outside assessed area)",
  beyond_radius: "beyond counting radius",
  excluded_scope: "not in selected scope",
};

export function summaryLine(assessment: AssessmentOut | null): string {
  if (!assessment || assessment.status === "not_assessed") return "Not assessed";
  const matched = assessment.matched_record_count ?? 0;
  if (matched === 0) return "No mapped encounters detected by this assessment. Unmapped or mislocated cameras may still be present.";
  return `${matched} mapped record${matched === 1 ? "" : "s"} on roads this route uses`;
}

function roads(encounter: EncounterOut): string {
  const a = encounter.association;
  if (!a) return "";
  const nearest = a.nearest_road_names.length ? a.nearest_road_names.join(" / ") : a.nearest_way_id ? `way ${a.nearest_way_id}` : "no road";
  const route = a.route_road_names.length ? a.route_road_names.join(" / ") : a.route_way_id ? `way ${a.route_way_id}` : "route";
  return a.same_road ? `on ${nearest}` : `nearest ${nearest}; route on ${route}`;
}

export function Encounters({ assessment, units }: { assessment: AssessmentOut; units: Units }) {
  const listed = assessment.encounters.filter((e) => e.status !== "excluded_scope");
  return (
    <details className="evidence" data-testid="encounter-list">
      <summary>Camera evidence ({listed.length} record{listed.length === 1 ? "" : "s"} near this route)</summary>
      <p className="disclaimer">{assessment.meaning} Counting radius {assessment.radius_m} m; method {assessment.counting_method_version}; graph {assessment.graph_version ?? "unknown"}.</p>
      {listed.length === 0 ? (
        <p className="notice notice-info">No mapped ALPR records within {Math.max(...assessment.sensitivity.map((s) => s.radius_m), assessment.radius_m)} m of this route in the current snapshot.</p>
      ) : (
        <ol className="encounters">
          {listed.map((encounter) => (
            <li key={encounter.source_key} className={`encounter encounter-${encounter.status}`} data-testid="encounter">
              <div className="row">
                <span className={`tag ${encounter.status === "associated" ? "tag-accent" : ""}`}>{STATUS_LABEL[encounter.status]}</span>
                <span>{encounter.manufacturer ?? "manufacturer unknown"}{encounter.is_flock ? " (Flock scope)" : ""}</span>
                <span className="disclaimer">
                  {formatDistance(encounter.distance_m, units)} from the route{encounter.position_m !== null ? `, ${formatDistance(encounter.position_m, units)} into the trip` : ""}
                  {encounter.pass_count > 1 ? `, passed ${encounter.pass_count} times` : ""}
                </span>
              </div>
              <div className="disclaimer">{roads(encounter)}</div>
              <div>{encounter.reason}</div>
              {encounter.heading_relation && <div className="disclaimer">{encounter.heading_relation}</div>}
              <a href={encounter.source_url} target="_blank" rel="noopener noreferrer">
                {encounter.source_key} on OpenStreetMap
              </a>
            </li>
          ))}
        </ol>
      )}
    </details>
  );
}
