"use client";

import type { PlanResponse, ProfileOutcomeOut, RegionResponse, RouteOptionOut, RouteProfileName, SearchOut, SearchStatus } from "@/lib/api/types";
import { formatDistance, formatDuration, formatSignedDuration, formatTimestamp, type Units } from "@/lib/format";
import { Encounters, summaryLine } from "./Encounters";

interface Props {
  result: PlanResponse;
  region: RegionResponse | null;
  selectedRouteId: string | null;
  units: Units;
  maxExtraMinutes?: number;
  onSelect: (routeId: string) => void;
  onRaiseLimit?: (minutes: number) => void;
}

const SNAP_NOTE_THRESHOLD_M = 50;
const MAX_EXTRA_MINUTES = 120;

export const SEARCH_STATUS_TEXT: Record<SearchStatus, string> = {
  completed: "search completed",
  budget_exhausted: "routing-call budget exhausted; a larger budget might find more",
  partial: "search cut short; results come from the candidates assessed so far",
  not_run: "camera-aware search not run",
};

export function generatedByText(generatedBy: string): string {
  if (generatedBy === "baseline") return "engine baseline (no camera preference)";
  if (generatedBy.startsWith("penalized@")) return `soft road penalties during path search (factor ${generatedBy.slice("penalized@".length)}); reported time is unaffected`;
  if (generatedBy === "excluded") return "hard road exclusions during path search";
  return generatedBy;
}

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

function profileLabel(region: RegionResponse | null, profile: RouteProfileName): string {
  return region?.profiles[profile]?.label ?? profile;
}

function SearchSummary({ search, region, maxExtraMinutes, onRaiseLimit }: { search: SearchOut; region: RegionResponse | null; maxExtraMinutes?: number; onRaiseLimit?: (minutes: number) => void }) {
  const unresolved = search.profile_outcomes.filter((o) => o.outcome !== "improved");
  const limited = unresolved.some((o: ProfileOutcomeOut) => o.outcome === "same_as_standard" && (o.best_exposure_count ?? 0) > 0);
  const nextMinutes = Math.min(MAX_EXTRA_MINUTES, Math.max(5, (maxExtraMinutes ?? 10) * 2));
  const canRaise = limited && onRaiseLimit && maxExtraMinutes !== undefined && maxExtraMinutes < MAX_EXTRA_MINUTES;
  return (
    <div className="search-summary" data-testid="search-summary">
      <p>
        <strong>Comparison:</strong> {search.candidates_assessed} candidate route{search.candidates_assessed === 1 ? "" : "s"} fully assessed using {search.routing_calls_used} of {search.routing_calls_budget} routing calls in {search.elapsed_seconds.toFixed(1)} s · <span data-testid="search-status">{SEARCH_STATUS_TEXT[search.status] ?? search.status}</span>.
      </p>
      {search.notes.length > 0 && (
        <ul className="disclaimer notes">
          {search.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      {unresolved.map((outcome) => (
        <div key={outcome.profile} className={`notice ${outcome.outcome === "not_assessed" ? "notice-warn" : "notice-info"}`} data-testid="profile-outcome">
          <strong>{profileLabel(region, outcome.profile)}:</strong> {outcome.message}
        </div>
      ))}
      {canRaise && (
        <button type="button" className="btn btn-small" onClick={() => onRaiseLimit(nextMinutes)} data-testid="raise-limit">
          Raise the extra-time limit to {nextMinutes} min and plan again
        </button>
      )}
      <p className="disclaimer">
        {search.meaning} Method {search.method_version}.
      </p>
    </div>
  );
}

export function RouteCards({ result, region, selectedRouteId, units, maxExtraMinutes, onSelect, onRaiseLimit }: Props) {
  return (
    <div className="section" data-testid="route-cards">
      <h2>Route options</h2>
      <p className="disclaimer">The Standard route plus up to two camera-aware alternatives. Preferences that pick the same path share one card with several labels.</p>
      {result.warnings.length > 0 && (
        <ul className="notice notice-warn" style={{ margin: 0, paddingLeft: 24 }}>
          {result.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
      <SearchSummary search={result.search} region={region} maxExtraMinutes={maxExtraMinutes} onRaiseLimit={onRaiseLimit} />
      {result.options.map((option) => {
        const selected = option.route_id === selectedRouteId;
        const notes = snapNotes(option, units);
        const assessment = option.assessment;
        const assessed = assessment !== null && assessment.status !== "not_assessed";
        return (
          <div key={option.route_id} className={`route-card${selected ? " selected" : ""}`} data-testid="route-card">
            <button type="button" className="route-card-select" onClick={() => onSelect(option.route_id)} aria-pressed={selected}>
              <div className="labels">
                {option.profiles.map((profile) => (
                  <span key={profile} className="tag tag-accent">
                    {profileLabel(region, profile)}
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
              <dd>{assessed ? `${assessment.uncertain_record_count ?? 0} (different or ambiguous road, no longer mapped, or outside the assessed area)` : "not assessed"}</dd>
              <dt>Exposure compared</dt>
              <dd data-testid="exposure">{option.exposure_count !== null ? `${option.exposure_count} (matched plus uncertain, each record once)` : "not assessed"}</dd>
              <dt>Records within 25 / 50 / 100 m</dt>
              <dd>{assessed ? assessment.sensitivity.map((s) => s.records_within).join(" / ") : "not assessed"}</dd>
              <dt>Assessment</dt>
              <dd>{coverageText(option)}</dd>
              <dt>Found by</dt>
              <dd>{generatedByText(option.generated_by)}</dd>
              {option.detour_bound_seconds !== null && (
                <>
                  <dt>Detour limit applied</dt>
                  <dd>within {formatDuration(option.detour_bound_seconds)} total travel time</dd>
                </>
              )}
              <dt>Camera data</dt>
              <dd>{option.camera_snapshot_id ? `snapshot of ${formatTimestamp(option.camera_source_as_of)}` : "no snapshot loaded"}</dd>
              <dt>Road graph</dt>
              <dd>{option.road_graph_version}</dd>
            </dl>
            {assessed && <Encounters assessment={assessment} units={units} />}
          </div>
        );
      })}
      <p className="disclaimer">{result.disclaimer}</p>
    </div>
  );
}
