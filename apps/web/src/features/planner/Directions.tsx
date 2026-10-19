"use client";

import type { RouteOptionOut } from "@/lib/api/types";
import { formatDistance, type Units } from "@/lib/format";

interface Props {
  route: RouteOptionOut;
  units: Units;
  highlighted: number | null;
  onHighlight: (index: number | null) => void;
}

export function Directions({ route, units, highlighted, onHighlight }: Props) {
  return (
    <div className="section" data-testid="directions">
      <h2>Street-by-street directions</h2>
      <p className="notice notice-info">Plan while stopped. These instructions come from the routing engine for the selected route and are not live navigation. Point at a step to see it on the map.</p>
      <ol className="directions">
        {route.maneuvers.map((maneuver, index) => (
          <li
            key={`${index}-${maneuver.begin_shape_index}`}
            className={`direction${highlighted === index ? " highlighted" : ""}`}
            tabIndex={0}
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
            </span>
            <span className="distance">{maneuver.length_meters > 0 ? formatDistance(maneuver.length_meters, units) : ""}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
