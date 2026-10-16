"use client";

import type { RouteOptionOut } from "@/lib/api/types";
import { formatDistance } from "@/lib/format";

export function Directions({ route }: { route: RouteOptionOut }) {
  return (
    <div className="section" data-testid="directions">
      <h2>Street-by-street directions</h2>
      <p className="notice notice-info">Plan while stopped. These instructions come from the routing engine for the selected route and are not live navigation.</p>
      <ol className="directions">
        {route.maneuvers.map((maneuver, index) => (
          <li key={`${index}-${maneuver.begin_shape_index}`} className="direction">
            <span className="step" aria-hidden="true">
              {index + 1}
            </span>
            <span>
              <span>{maneuver.instruction}</span>
              {maneuver.street_names.length > 0 && <span className="streets"> {maneuver.street_names.join(" / ")}</span>}
            </span>
            <span className="distance">{maneuver.length_meters > 0 ? formatDistance(maneuver.length_meters) : ""}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
