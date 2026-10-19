"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { api, describeError } from "@/lib/api/client";
import type { DataHealth, GeocodeCandidate, RegionResponse } from "@/lib/api/types";
import type { Units } from "@/lib/format";
import { DataHealthPanel } from "@/features/data-health/DataHealthPanel";
import { DataStatusStrip } from "./DataStatusStrip";
import { Directions } from "./Directions";
import { EndpointInput } from "./EndpointInput";
import { RouteCards } from "./RouteCards";
import { canPlan, initialPlannerState, plannerReducer, selectedRoute, type EndpointKey } from "./plannerReducer";

const MapView = dynamic(() => import("@/features/camera-map/MapView").then((m) => m.MapView), { ssr: false });

const ERROR_TEXT: Record<string, string> = {
  OUTSIDE_SERVICE_AREA: "Trips must start and end inside the Denver pilot area.",
  ROUTER_UNAVAILABLE: "The route engine is unavailable right now. Try again in a moment.",
  NO_DRIVABLE_ROUTE: "No drivable route was found between these points.",
  GEOCODER_NOT_CONFIGURED: "Address search is not configured. Type coordinates as lat, lon or place a map pin.",
  GEOCODER_UNAVAILABLE: "Address search is temporarily unavailable. Coordinates and map pins still work.",
  NETWORK: "The server could not be reached.",
};

export function Planner() {
  const [state, dispatch] = useReducer(plannerReducer, initialPlannerState);
  const [region, setRegion] = useState<RegionResponse | null>(null);
  const [health, setHealth] = useState<DataHealth | null>(null);
  const [regionError, setRegionError] = useState<string | null>(null);
  const [mapStatus, setMapStatus] = useState<"loading" | "ready" | "failed">("loading");
  const [highlighted, setHighlighted] = useState<number | null>(null);
  const planAbort = useRef<AbortController | null>(null);
  const searchAborts = useRef<Record<EndpointKey, AbortController | null>>({ origin: null, destination: null });
  const pinModeRef = useRef(state.pinMode);
  pinModeRef.current = state.pinMode;

  useEffect(() => {
    const controller = new AbortController();
    api
      .region(controller.signal)
      .then(setRegion)
      .catch((error) => {
        if (!controller.signal.aborted) setRegionError(describeError(error).message);
      });
    api
      .dataHealth(controller.signal)
      .then(setHealth)
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  const search = useCallback(
    async (endpoint: EndpointKey) => {
      const text = state[endpoint].text.trim();
      if (!text) return;
      searchAborts.current[endpoint]?.abort();
      const controller = new AbortController();
      searchAborts.current[endpoint] = controller;
      dispatch({ type: "SEARCH_START", endpoint });
      try {
        const response = await api.geocode(text, controller.signal);
        if (controller.signal.aborted) return;
        if (response.candidates.length === 1 && response.query_kind === "coordinates" && !response.candidates[0].note) {
          dispatch({ type: "CONFIRM_CANDIDATE", endpoint, candidate: response.candidates[0] });
        } else {
          dispatch({ type: "SEARCH_RESULT", endpoint, candidates: response.candidates });
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        const described = describeError(error);
        dispatch({ type: "SEARCH_ERROR", endpoint, error: { code: described.code, message: ERROR_TEXT[described.code] ?? described.message } });
      }
    },
    [state],
  );

  const geocoderConfigured = region?.capabilities.geocoder_configured ?? false;

  const onPinPlaced = useCallback(
    (lat: number, lon: number) => {
      const endpoint = pinModeRef.current;
      dispatch({ type: "PIN_PLACED", lat, lon });
      if (!endpoint || !geocoderConfigured) return;
      // Label the pin with the nearest mapped place; the pin coordinates themselves never change.
      api
        .reverse(lat, lon)
        .then((result) => {
          if (result.found && result.label) {
            dispatch({ type: "RELABEL_ENDPOINT", endpoint, lat, lon, label: `Map pin near ${result.label}` });
          }
        })
        .catch(() => undefined);
    },
    [geocoderConfigured],
  );

  const plan = useCallback(async () => {
    const origin = state.origin.confirmed;
    const destination = state.destination.confirmed;
    if (!origin || !destination || !region) return;
    planAbort.current?.abort();
    const controller = new AbortController();
    planAbort.current = controller;
    dispatch({ type: "PLAN_START" });
    setHighlighted(null);
    const sequence = state.request.sequence + 1;
    try {
      const result = await api.plan(
        {
          origin: { lat: origin.lat, lon: origin.lon },
          destination: { lat: destination.lat, lon: destination.lon },
          region_id: region.region_id,
          profiles: [state.profile],
          camera_scope: state.scope,
          detour_limits: { max_extra_seconds: state.maxExtraMinutes * 60, max_relative_factor: state.relativeLimit },
          units: state.units,
        },
        controller.signal,
      );
      dispatch({ type: "PLAN_SUCCESS", sequence, result });
    } catch (error) {
      if (controller.signal.aborted) return;
      const described = describeError(error);
      dispatch({ type: "PLAN_ERROR", sequence, error: { code: described.code, message: ERROR_TEXT[described.code] ?? described.message } });
    }
  }, [state, region]);

  const cancel = useCallback(() => {
    planAbort.current?.abort();
    dispatch({ type: "PLAN_CANCEL" });
  }, []);

  const route = useMemo(() => selectedRoute(state), [state]);
  const highlightRange = useMemo<[number, number] | null>(() => {
    if (!route || highlighted === null) return null;
    const maneuver = route.maneuvers[highlighted];
    return maneuver ? [maneuver.begin_shape_index, maneuver.end_shape_index] : null;
  }, [route, highlighted]);

  const endpointProps = (endpoint: EndpointKey, label: string) => ({
    endpoint,
    label,
    state: state[endpoint],
    pinModeActive: state.pinMode === endpoint,
    geocoderConfigured,
    onTextChange: (text: string) => dispatch({ type: "SET_TEXT", endpoint, text }),
    onSearch: () => void search(endpoint),
    onConfirm: (candidate: GeocodeCandidate) => dispatch({ type: "CONFIRM_CANDIDATE", endpoint, candidate }),
    onClear: () => dispatch({ type: "CLEAR_ENDPOINT", endpoint }),
    onTogglePinMode: () => dispatch({ type: "SET_PIN_MODE", endpoint: state.pinMode === endpoint ? null : endpoint }),
  });

  const setUnits = (units: Units) => dispatch({ type: "SET_UNITS", units });

  return (
    <div className="planner-layout">
      <aside className={`panel${state.sheetExpanded ? "" : " collapsed"}`} aria-label="Trip planner">
        <button type="button" className="btn btn-small sheet-handle" onClick={() => dispatch({ type: "TOGGLE_SHEET" })} aria-expanded={state.sheetExpanded}>
          {state.sheetExpanded ? "Hide planner" : "Show planner"}
        </button>
        <header>
          <h1 className="app-title">DeFlockMigration</h1>
          <p className="app-subtitle">{region ? region.display_name : "Denver pilot"} · compare routes by mapped ALPR cameras</p>
        </header>
        <DataStatusStrip region={region} health={health} />
        {regionError && <div className="notice notice-error">Region configuration could not be loaded: {regionError}</div>}
        {mapStatus === "failed" && <div className="notice notice-warn">The map could not be rendered on this device. Coordinates, typed addresses, and written directions still work; map pins need the map.</div>}

        <section className="section" aria-labelledby="trip-heading">
          <h2 id="trip-heading">Trip</h2>
          <EndpointInput {...endpointProps("origin", "Start")} />
          <EndpointInput {...endpointProps("destination", "Destination")} />
          <div className="row">
            <button type="button" className="btn btn-small" onClick={() => dispatch({ type: "SWAP" })} disabled={!state.origin.confirmed && !state.destination.confirmed}>
              Swap start and destination
            </button>
            <span className="units-toggle" role="group" aria-label="Distance units">
              <button type="button" className="btn btn-small" aria-pressed={state.units === "km"} onClick={() => setUnits("km")}>
                km
              </button>
              <button type="button" className="btn btn-small" aria-pressed={state.units === "mi"} onClick={() => setUnits("mi")}>
                mi
              </button>
            </span>
          </div>
        </section>

        <section className="section" aria-labelledby="prefs-heading">
          <h2 id="prefs-heading">Preferences</h2>
          <fieldset>
            <legend>Route preference</legend>
            {(["standard", "balanced", "fewest_mapped"] as const).map((profile) => (
              <label key={profile} className="radio">
                <input type="radio" name="profile" value={profile} checked={state.profile === profile} onChange={() => dispatch({ type: "SET_PROFILE", profile })} />
                <span>
                  {region?.profiles[profile]?.label ?? profile}
                  <span className="desc">{region?.profiles[profile]?.description ?? ""}{profile !== "standard" ? " Camera-aware comparison arrives in a later milestone; this version returns the standard route." : ""}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend>Camera scope</legend>
            <label className="radio">
              <input type="radio" name="scope" value="all_alpr" checked={state.scope === "all_alpr"} onChange={() => dispatch({ type: "SET_SCOPE", scope: "all_alpr" })} />
              <span>
                All mapped ALPRs<span className="desc">Includes devices with an unknown manufacturer. Recommended.</span>
              </span>
            </label>
            <label className="radio">
              <input type="radio" name="scope" value="flock_only" checked={state.scope === "flock_only"} onChange={() => dispatch({ type: "SET_SCOPE", scope: "flock_only" })} />
              <span>
                Flock-tagged ALPRs only<span className="desc">Only records whose manufacturer tag names Flock Safety.</span>
              </span>
            </label>
          </fieldset>
          <div className="field">
            <label htmlFor="max-extra">Maximum extra travel time: {state.maxExtraMinutes} min</label>
            <input id="max-extra" type="range" min={0} max={60} step={1} value={state.maxExtraMinutes} onChange={(event) => dispatch({ type: "SET_MAX_EXTRA", minutes: Number(event.target.value) })} />
          </div>
          <details open={state.showAdvanced} onToggle={(event) => {
            if ((event.target as HTMLDetailsElement).open !== state.showAdvanced) dispatch({ type: "TOGGLE_ADVANCED" });
          }}>
            <summary>Advanced limits</summary>
            <div className="field">
              <label htmlFor="relative-limit">Relative limit: up to {state.relativeLimit.toFixed(2)} × the standard time</label>
              <input id="relative-limit" type="range" min={1} max={2} step={0.05} value={state.relativeLimit} onChange={(event) => dispatch({ type: "SET_RELATIVE", factor: Number(event.target.value) })} />
              <span className="disclaimer">Both limits apply; for short trips the relative limit usually binds first.</span>
            </div>
          </details>
          <label className="radio">
            <input type="checkbox" checked={state.showCameras} onChange={() => dispatch({ type: "TOGGLE_CAMERAS" })} />
            <span>Show mapped cameras on the map (zoom in to see them)</span>
          </label>
        </section>

        <section className="section">
          <div className="row">
            <button type="button" className="btn btn-primary" onClick={() => void plan()} disabled={!canPlan(state) || !region} data-testid="plan-button">
              {state.request.status === "loading" ? "Planning…" : "Plan route"}
            </button>
            {state.request.status === "loading" && (
              <button type="button" className="btn" onClick={cancel}>
                Cancel
              </button>
            )}
            <button type="button" className="btn" onClick={() => dispatch({ type: "CLEAR_TRIP" })}>
              Clear trip
            </button>
          </div>
          <div aria-live="polite">
            {state.request.status === "loading" && <div className="notice notice-info">Calculating a standard route…</div>}
            {state.request.status === "error" && state.request.error && (
              <div className="notice notice-error" data-testid="plan-error">
                {state.request.error.message} <span className="disclaimer">({state.request.error.code})</span>
              </div>
            )}
            {!canPlan(state) && state.request.status === "idle" && !state.result && <div className="notice notice-info">Confirm a start and a destination to plan a route.</div>}
          </div>
        </section>

        {state.result && <RouteCards result={state.result} region={region} selectedRouteId={state.selectedRouteId} units={state.units} onSelect={(routeId) => dispatch({ type: "SELECT_ROUTE", routeId })} />}
        {route && <Directions route={route} units={state.units} highlighted={highlighted} onHighlight={setHighlighted} />}

        <DataHealthPanel />

        <footer className="section">
          <p className="disclaimer">{region?.disclaimer ?? "Routes are advisory. Camera counts describe mapped records, not physical devices."}</p>
          <ul className="disclaimer" style={{ paddingLeft: 18, margin: 0 }}>
            {(region?.attributions ?? []).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <p className="disclaimer">DeFlockMigration is an independent project, not affiliated with DeFlock, Flock Safety, OpenStreetMap, or the City and County of Denver. No trip is stored.</p>
        </footer>
      </aside>
      <main className="map-area">
        {mapStatus === "failed" ? (
          <div className="map-fallback" role="status">
            Map rendering is unavailable on this device. The planner and written directions remain usable.
          </div>
        ) : (
          <MapView
            region={region}
            route={route}
            origin={state.origin.confirmed}
            destination={state.destination.confirmed}
            pinMode={state.pinMode !== null}
            showCameras={state.showCameras}
            scope={state.scope}
            highlightRange={highlightRange}
            encounters={route?.assessment?.encounters ?? null}
            onPinPlaced={onPinPlaced}
            onStatus={setMapStatus}
          />
        )}
      </main>
    </div>
  );
}
