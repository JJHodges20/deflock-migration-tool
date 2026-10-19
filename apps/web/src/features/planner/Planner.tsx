"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { api, describeError } from "@/lib/api/client";
import type { DataHealth, GeocodeCandidate, RegionResponse, RouteProfileName } from "@/lib/api/types";
import { formatDistance, formatDuration, formatTimestamp, type Units } from "@/lib/format";
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
  VALIDATION_ERROR: "The request was rejected as invalid: unsupported route settings or input. Adjust the limits and try again.",
  GEOCODER_NOT_CONFIGURED: "Address search is not configured. Type coordinates as lat, lon or place a map pin.",
  GEOCODER_UNAVAILABLE: "Address search is temporarily unavailable. Coordinates and map pins still work.",
  NETWORK: "The server could not be reached.",
};

/** A planned result keeps the versions it was computed with; when Data Health shows newer ones, say so (never recompute silently). */
export function outdatedVersions(option: { camera_snapshot_id: string | null; road_graph_version: string } | null, health: DataHealth | null): string[] {
  if (!option || !health) return [];
  const notes: string[] = [];
  const current = health.snapshot?.snapshot_id ?? null;
  if (option.camera_snapshot_id && current && current !== option.camera_snapshot_id) {
    notes.push(`a newer camera snapshot (${current}) was published after this plan`);
  }
  const graphBuilt = health.router.tileset_last_modified;
  const planned = option.road_graph_version.includes("@") ? option.road_graph_version.split("@")[1] : null;
  if (graphBuilt && planned && graphBuilt !== planned) {
    notes.push(`the road graph was rebuilt (${graphBuilt}) after this plan`);
  }
  return notes;
}

function withinBbox(lat: number, lon: number, bbox: number[] | undefined): boolean {
  if (!bbox || bbox.length !== 4) return true;
  return lon >= bbox[0] && lat >= bbox[1] && lon <= bbox[2] && lat <= bbox[3];
}

export function Planner() {
  const [state, dispatch] = useReducer(plannerReducer, initialPlannerState);
  const [region, setRegion] = useState<RegionResponse | null>(null);
  const [health, setHealth] = useState<DataHealth | null>(null);
  const [regionError, setRegionError] = useState<string | null>(null);
  const [mapStatus, setMapStatus] = useState<"loading" | "ready" | "failed">("loading");
  const [highlighted, setHighlighted] = useState<number | null>(null);
  const [locating, setLocating] = useState(false);
  const [locationSupported, setLocationSupported] = useState(false); // decided after mount so server and client render the same HTML
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
    const refreshHealth = () => {
      api
        .dataHealth(controller.signal)
        .then(setHealth)
        .catch(() => undefined);
    };
    refreshHealth();
    // Data Health is polled every five minutes and when the tab becomes visible again, so a route planned on an
    // older snapshot or graph is shown as outdated instead of silently changing (roadmap 8, step 10).
    const timer = window.setInterval(refreshHealth, 5 * 60 * 1000);
    const onVisible = () => {
      if (document.visibilityState === "visible") refreshHealth();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      controller.abort();
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  useEffect(() => {
    setLocationSupported(typeof navigator !== "undefined" && "geolocation" in navigator);
  }, []);

  // Keyboard and screen-reader users land on the results as soon as they exist.
  useEffect(() => {
    if (state.request.status === "success" && state.result) {
      document.getElementById("route-options-heading")?.focus();
    }
  }, [state.request.status, state.result]);

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

  const relabel = useCallback(
    (endpoint: EndpointKey, lat: number, lon: number, prefix: string) => {
      if (!geocoderConfigured) return;
      // Label the point with the nearest mapped place; the coordinates themselves never change.
      api
        .reverse(lat, lon)
        .then((result) => {
          if (result.found && result.label) {
            dispatch({ type: "RELABEL_ENDPOINT", endpoint, lat, lon, label: `${prefix} near ${result.label}` });
          }
        })
        .catch(() => undefined);
    },
    [geocoderConfigured],
  );

  const onPinPlaced = useCallback(
    (lat: number, lon: number) => {
      const endpoint = pinModeRef.current;
      dispatch({ type: "PIN_PLACED", lat, lon });
      if (endpoint) relabel(endpoint, lat, lon, "Map pin");
    },
    [relabel],
  );

  // Optional one-shot device location (roadmap section 12): asked only on this click, never watched or stored.
  const useLocation = useCallback(() => {
    if (typeof navigator === "undefined" || !("geolocation" in navigator)) return;
    if (typeof window !== "undefined" && window.isSecureContext === false) {
      dispatch({ type: "SEARCH_ERROR", endpoint: "origin", error: { code: "LOCATION_INSECURE", message: "Browsers share location only on secure pages (https or localhost). Open the planner at http://127.0.0.1:3000, or type an address, coordinates, or place a map pin." } });
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocating(false);
        const { latitude: lat, longitude: lon, accuracy } = position.coords;
        const candidate: GeocodeCandidate = {
          label: `My location (device estimate, about ${Math.round(accuracy)} m accuracy)`,
          lat,
          lon,
          source: "device_location",
          category: "location",
          importance: null,
          inside_service_boundary: withinBbox(lat, lon, region?.service_boundary.bbox_wsen),
        };
        dispatch({ type: "CONFIRM_CANDIDATE", endpoint: "origin", candidate });
        relabel("origin", lat, lon, "My location");
      },
      (error) => {
        setLocating(false);
        const denied = error.code === error.PERMISSION_DENIED;
        dispatch({
          type: "SEARCH_ERROR",
          endpoint: "origin",
          error: { code: "LOCATION_UNAVAILABLE", message: denied ? "Location permission was denied. Type an address, coordinates, or place a map pin instead." : "Your location is not available right now. Type an address, coordinates, or place a map pin instead." },
        });
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 0 },
    );
  }, [region, relabel]);

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
          profiles: ["standard", "balanced", "fewest_mapped"],
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

  const clearTrip = useCallback(() => {
    planAbort.current?.abort();
    setHighlighted(null);
    dispatch({ type: "CLEAR_TRIP" });
  }, []);

  // "Raise the limit and plan again": the slider moves first, then the next render re-plans with the new limit.
  const replanRef = useRef(false);
  const raiseLimit = useCallback((minutes: number) => {
    replanRef.current = true;
    dispatch({ type: "SET_MAX_EXTRA", minutes });
  }, []);
  useEffect(() => {
    if (!replanRef.current) return;
    replanRef.current = false;
    void plan();
  }, [state.maxExtraMinutes, plan]);

  const route = useMemo(() => selectedRoute(state), [state]);
  const highlightRange = useMemo<[number, number] | null>(() => {
    if (!route || highlighted === null) return null;
    const maneuver = route.maneuvers[highlighted];
    return maneuver ? [maneuver.begin_shape_index, maneuver.end_shape_index] : null;
  }, [route, highlighted]);
  const labelOf = (profile: RouteProfileName) => region?.profiles[profile]?.label ?? profile;
  const routeLabels = route ? route.profiles.map(labelOf).join(", ") : "";
  const outdated = useMemo(() => outdatedVersions(state.result?.options[0] ?? null, health), [state.result, health]);

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
  const planError = state.request.status === "error" ? state.request.error : null;

  return (
    <div className="planner-layout">
      <a className="skip-link" href="#trip-heading">
        Skip to the trip planner
      </a>
      <aside id="planner-panel" className={`panel${state.sheetExpanded ? "" : " collapsed"}`} aria-label="Trip planner">
        <button type="button" className="btn btn-small sheet-handle" onClick={() => dispatch({ type: "TOGGLE_SHEET" })} aria-expanded={state.sheetExpanded} aria-controls="planner-panel">
          {state.sheetExpanded ? "Hide planner" : "Show planner"}
        </button>
        <div className="sheet-summary" data-testid="sheet-summary" aria-live="polite">
          {route
            ? `${routeLabels}: ${formatDuration(route.estimated_duration_seconds)}, ${formatDistance(route.length_meters, state.units)}, ${route.exposure_count !== null ? `${route.exposure_count} mapped record${route.exposure_count === 1 ? "" : "s"} (matched plus uncertain)` : "camera data unknown"}`
            : state.request.status === "loading"
              ? "Planning…"
              : "No route planned yet"}
        </div>
        <header>
          <h1 className="app-title">DeFlockMigration</h1>
          <p className="app-subtitle">{region ? region.display_name : "Denver pilot"} · compare routes by mapped ALPR cameras</p>
        </header>
        <DataStatusStrip region={region} health={health} />
        {regionError && (
          <div className="notice notice-error" role="alert">
            Region configuration could not be loaded: {regionError}
          </div>
        )}
        {mapStatus === "failed" && <div className="notice notice-warn">The map could not be rendered on this device. Coordinates, typed addresses, and written directions still work; map pins need the map.</div>}

        <section className="section" aria-labelledby="trip-heading">
          <h2 id="trip-heading" tabIndex={-1}>
            Trip
          </h2>
          <EndpointInput {...endpointProps("origin", "Start")} onUseLocation={locationSupported ? useLocation : undefined} locating={locating} />
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
            <legend>Routes compared</legend>
            <ul className="compare-list" data-testid="compare-list">
              <li>
                <strong>{region?.profiles.standard?.label ?? "Standard route"}</strong>
                <span className="desc">Fastest baseline by the engine&apos;s reported time, with no camera preference.</span>
              </li>
              <li>
                <strong>{region?.profiles.balanced?.label ?? "Balanced"}</strong>
                <span className="desc">
                  Fewest mapped encounters among evaluated candidates within your limit: {state.maxExtraMinutes} min extra or {state.relativeLimit.toFixed(2)} × the standard time, whichever is smaller.
                </span>
              </li>
              <li>
                <strong>{region?.profiles.fewest_mapped?.label ?? "Fewest mapped cameras found"}</strong>
                <span className="desc">
                  Fewest mapped encounters within a wider limit: {Math.round((region?.profiles.fewest_mapped?.max_extra_seconds ?? 1200) / 60)} min extra or {(region?.profiles.fewest_mapped?.max_relative_factor ?? 1.75).toFixed(2)} × the standard time, and never tighter than your limit.
                </span>
              </li>
            </ul>
            <span className="disclaimer">Best among the candidates evaluated within a bounded search, never a guaranteed minimum. Encounters count mapped records (matched plus uncertain), each record once.</span>
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
              <button type="button" className="btn" onClick={cancel} data-testid="cancel-button">
                Cancel
              </button>
            )}
            <button type="button" className="btn" onClick={clearTrip} data-testid="clear-trip">
              Clear trip
            </button>
          </div>
          <div aria-live="polite">
            {state.request.status === "loading" && (
              <div className="notice notice-info" role="status">
                Calculating the standard route, then searching camera-aware alternatives (up to about 20 s)…
              </div>
            )}
            {state.request.status === "cancelled" && (
              <div className="notice notice-info" role="status" data-testid="plan-cancelled">
                Planning cancelled. Nothing was kept; plan again when you are ready.
              </div>
            )}
            {planError && planError.code === "NO_DRIVABLE_ROUTE" && (
              <div className="state state-no-route" role="alert" data-testid="state-no-route">
                <span className="state-label">No route at all</span>
                <span>{planError.message} Nothing is drawn, because no road-legal path exists between these points in the current road graph. Try points on nearby public roads.</span>
              </div>
            )}
            {planError && planError.code !== "NO_DRIVABLE_ROUTE" && (
              <div className="notice notice-error" role="alert" data-testid="plan-error">
                {planError.message} <span className="disclaimer">({planError.code})</span>
              </div>
            )}
            {!canPlan(state) && state.request.status === "idle" && !state.result && <div className="notice notice-info">Confirm a start and a destination to plan a route.</div>}
          </div>
        </section>

        {state.result && route && (
          <div className="print-only" data-testid="print-header">
            <h2>DeFlockMigration route plan</h2>
            <p>
              Planned {formatTimestamp(new Date().toISOString())}. Start: {state.origin.confirmed?.label ?? "unknown"}. Destination: {state.destination.confirmed?.label ?? "unknown"}.
            </p>
            <p>
              Selected option: {routeLabels}; {formatDuration(route.estimated_duration_seconds)} estimated without live traffic; camera snapshot {route.camera_snapshot_id ?? "none"} as of {formatTimestamp(route.camera_source_as_of)}; road graph {route.road_graph_version}.
            </p>
            <p>{state.result.disclaimer}</p>
          </div>
        )}

        {state.result && outdated.length > 0 && (
          <div className="notice notice-warn" role="status" data-testid="outdated-result">
            These results keep the data versions they were computed with, but {outdated.join(" and ")}. Plan again to use the current data.
          </div>
        )}
        {state.result && (
          <RouteCards
            result={state.result}
            region={region}
            health={health}
            selectedRouteId={state.selectedRouteId}
            units={state.units}
            maxExtraMinutes={state.maxExtraMinutes}
            exportContext={{ originLabel: state.origin.confirmed?.label ?? "start", destinationLabel: state.destination.confirmed?.label ?? "destination" }}
            onSelect={(routeId) => dispatch({ type: "SELECT_ROUTE", routeId })}
            onRaiseLimit={raiseLimit}
          />
        )}
        {route && <Directions route={route} units={state.units} highlighted={highlighted} onHighlight={setHighlighted} profileLabel={routeLabels} />}

        <DataHealthPanel />

        <footer className="section">
          <p className="disclaimer">{region?.disclaimer ?? "Routes are advisory. Camera counts describe mapped records, not physical devices."}</p>
          <ul className="disclaimer" style={{ paddingLeft: 18, margin: 0 }}>
            {(region?.attributions ?? []).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <p className="disclaimer">DeFlockMigration is an independent project, not affiliated with DeFlock, Flock Safety, OpenStreetMap, or the City and County of Denver. No trip is stored, no account exists, and nothing leaves this computer except requests to the local services.</p>
        </footer>
      </aside>
      <main className="map-area">
        <p className="visually-hidden">The map is optional: the route cards and the written directions describe every option in full.</p>
        {mapStatus === "failed" ? (
          <div className="map-fallback" role="status">
            Map rendering is unavailable on this device. The planner and written directions remain usable.
          </div>
        ) : (
          <MapView
            region={region}
            route={route}
            options={state.result?.options ?? null}
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
