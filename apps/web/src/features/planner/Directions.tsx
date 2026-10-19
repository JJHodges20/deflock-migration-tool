"use client";

import type { RouteOptionOut } from "@/lib/api/types";
import { formatDistance, formatDuration, type Units } from "@/lib/format";

interface Props {
  route: RouteOptionOut;
  units: Units;
  highlighted: number | null;
  onHighlight: (index: number | null) => void;
  profileLabel?: string;
}

/** Engine-generated maneuvers for the selected route (roadmap section 11). Instruction text comes from the engine and is
 *  never rewritten; road names appear only when the engine supplied them; the distance is the length of the step, which is
 *  the distance until the next maneuver. */
export function Directions({ route, units, highlighted, onHighlight, profileLabel }: Props) {
  const steps = route.maneuvers.length;
  return (
    <div className="section" data-testid="directions">
      <h2>Street-by-street directions</h2>
      <p className="disclaimer" data-testid="directions-summary">
        {profileLabel ? `${profileLabel}: ` : ""}
        {steps} step{steps === 1 ? "" : "s"} · {formatDistance(route.length_meters, units)} · about {formatDuration(route.estimated_duration_seconds)} without live traffic
        {route.has_toll ? " · includes a toll road" : ""}
        {route.has_highway ? " · uses a highway" : ""}
      </p>
      <p className="notice notice-info">Plan while stopped. These instructions come from the routing engine for the selected route and are not live navigation; the app does not follow your position or know about closures. Point at or tab to a step to see it on the map.</p>
      <ol className="directions">
        {route.maneuvers.map((maneuver, index) => (
          <li
            key={`${index}-${maneuver.begin_shape_index}`}
            className={`direction${highlighted === index ? " highlighted" : ""}`}
            tabIndex={0}
            aria-current={highlighted === index ? "step" : undefined}
            onMouseEnter={() => onHighlight(index)}
            onMouseLeave={() => onHighlight(null)}
            onFocus={() => onHighlight(index)}
            onBlur={() => onHighlight(null)}
          >
            <span className="step" aria-hidden="true">
              {index + 1}
            </span>
            <span>
              <span>{maneuver.instruction}</span>
              {maneuver.street_names.length > 0 && <span className="streets"> {maneuver.street_names.join(" / ")}</span>}
              {maneuver.roundabout_exit_count !== null && maneuver.roundabout_exit_count !== undefined && <span className="streets"> (exit {maneuver.roundabout_exit_count})</span>}
            </span>
            <span className="distance">{maneuver.length_meters > 0 ? `${formatDistance(maneuver.length_meters, units)} to next` : ""}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
