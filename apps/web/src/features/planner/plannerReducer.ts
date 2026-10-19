import type { CameraScope, GeocodeCandidate, PlanResponse } from "@/lib/api/types";
import type { Units } from "@/lib/format";

export type EndpointKey = "origin" | "destination";

export interface EndpointState {
  text: string;
  candidates: GeocodeCandidate[];
  confirmed: GeocodeCandidate | null;
  searching: boolean;
  error: { code: string; message: string } | null;
}

export type RequestStatus = "idle" | "loading" | "success" | "error" | "cancelled";

export interface PlannerState {
  origin: EndpointState;
  destination: EndpointState;
  pinMode: EndpointKey | null;
  scope: CameraScope;
  maxExtraMinutes: number;
  relativeLimit: number;
  showAdvanced: boolean;
  showCameras: boolean;
  units: Units;
  request: { status: RequestStatus; error: { code: string; message: string } | null; sequence: number };
  result: PlanResponse | null;
  selectedRouteId: string | null;
  sheetExpanded: boolean;
}

export type PlannerAction =
  | { type: "SET_TEXT"; endpoint: EndpointKey; text: string }
  | { type: "SEARCH_START"; endpoint: EndpointKey }
  | { type: "SEARCH_RESULT"; endpoint: EndpointKey; candidates: GeocodeCandidate[] }
  | { type: "SEARCH_ERROR"; endpoint: EndpointKey; error: { code: string; message: string } }
  | { type: "CONFIRM_CANDIDATE"; endpoint: EndpointKey; candidate: GeocodeCandidate }
  | { type: "CLEAR_ENDPOINT"; endpoint: EndpointKey }
  | { type: "SET_PIN_MODE"; endpoint: EndpointKey | null }
  | { type: "PIN_PLACED"; lat: number; lon: number }
  | { type: "SWAP" }
  | { type: "SET_SCOPE"; scope: CameraScope }
  | { type: "SET_MAX_EXTRA"; minutes: number }
  | { type: "SET_RELATIVE"; factor: number }
  | { type: "TOGGLE_ADVANCED" }
  | { type: "TOGGLE_CAMERAS" }
  | { type: "SET_UNITS"; units: Units }
  | { type: "RELABEL_ENDPOINT"; endpoint: EndpointKey; lat: number; lon: number; label: string }
  | { type: "PLAN_START" }
  | { type: "PLAN_SUCCESS"; sequence: number; result: PlanResponse }
  | { type: "PLAN_ERROR"; sequence: number; error: { code: string; message: string } }
  | { type: "PLAN_CANCEL" }
  | { type: "SELECT_ROUTE"; routeId: string }
  | { type: "CLEAR_TRIP" }
  | { type: "TOGGLE_SHEET" };

export const emptyEndpoint: EndpointState = { text: "", candidates: [], confirmed: null, searching: false, error: null };

export const initialPlannerState: PlannerState = {
  origin: { ...emptyEndpoint },
  destination: { ...emptyEndpoint },
  pinMode: null,
  scope: "all_alpr",
  maxExtraMinutes: 10,
  relativeLimit: 1.5,
  showAdvanced: false,
  showCameras: true,
  units: "km",
  request: { status: "idle", error: null, sequence: 0 },
  result: null,
  selectedRouteId: null,
  sheetExpanded: true,
};

export function pinCandidate(lat: number, lon: number): GeocodeCandidate {
  return { label: `Map pin ${lat.toFixed(5)}, ${lon.toFixed(5)}`, lat, lon, source: "map_pin", category: "pin", importance: null, inside_service_boundary: true };
}

function invalidateResult(state: PlannerState): PlannerState {
  // Changing an endpoint makes any displayed route stale; drop it rather than show a mismatch.
  return { ...state, result: null, selectedRouteId: null, request: { ...state.request, status: "idle", error: null } };
}

export function plannerReducer(state: PlannerState, action: PlannerAction): PlannerState {
  switch (action.type) {
    case "SET_TEXT":
      return { ...state, [action.endpoint]: { ...state[action.endpoint], text: action.text, error: null } };
    case "SEARCH_START":
      return { ...state, [action.endpoint]: { ...state[action.endpoint], searching: true, error: null, candidates: [] } };
    case "SEARCH_RESULT":
      return { ...state, [action.endpoint]: { ...state[action.endpoint], searching: false, candidates: action.candidates, error: action.candidates.length === 0 ? { code: "NO_MATCH", message: "No address match. Try a more complete address, coordinates, or a map pin." } : null } };
    case "SEARCH_ERROR":
      return { ...state, [action.endpoint]: { ...state[action.endpoint], searching: false, candidates: [], error: action.error } };
    case "CONFIRM_CANDIDATE":
      return invalidateResult({ ...state, pinMode: null, [action.endpoint]: { ...state[action.endpoint], confirmed: action.candidate, candidates: [], error: null, text: action.candidate.label } });
    case "CLEAR_ENDPOINT":
      return invalidateResult({ ...state, [action.endpoint]: { ...emptyEndpoint } });
    case "SET_PIN_MODE":
      return { ...state, pinMode: action.endpoint };
    case "PIN_PLACED": {
      if (!state.pinMode) return state;
      const candidate = pinCandidate(action.lat, action.lon);
      return invalidateResult({ ...state, pinMode: null, [state.pinMode]: { ...emptyEndpoint, confirmed: candidate, text: candidate.label } });
    }
    case "SWAP":
      return invalidateResult({ ...state, origin: state.destination, destination: state.origin, pinMode: null });
    case "SET_SCOPE":
      return { ...state, scope: action.scope };
    case "SET_MAX_EXTRA":
      return { ...state, maxExtraMinutes: Math.max(0, Math.min(120, Math.round(action.minutes))) };
    case "SET_RELATIVE":
      return { ...state, relativeLimit: Math.max(1, Math.min(3, action.factor)) };
    case "TOGGLE_ADVANCED":
      return { ...state, showAdvanced: !state.showAdvanced };
    case "TOGGLE_CAMERAS":
      return { ...state, showCameras: !state.showCameras };
    case "SET_UNITS":
      return { ...state, units: action.units };
    case "RELABEL_ENDPOINT": {
      // Only relabel the pin that is still confirmed at these coordinates; a late reverse lookup for a replaced pin is ignored.
      const confirmed = state[action.endpoint].confirmed;
      if (!confirmed || (confirmed.source !== "map_pin" && confirmed.source !== "device_location") || confirmed.lat !== action.lat || confirmed.lon !== action.lon) return state;
      const relabelled = { ...confirmed, label: action.label };
      return { ...state, [action.endpoint]: { ...state[action.endpoint], confirmed: relabelled, text: action.label } };
    }
    case "PLAN_START":
      return { ...state, request: { status: "loading", error: null, sequence: state.request.sequence + 1 }, result: null, selectedRouteId: null };
    case "PLAN_SUCCESS":
      if (action.sequence !== state.request.sequence || state.request.status !== "loading") return state; // late or cancelled response
      return { ...state, request: { ...state.request, status: "success", error: null }, result: action.result, selectedRouteId: action.result.options[0]?.route_id ?? null };
    case "PLAN_ERROR":
      if (action.sequence !== state.request.sequence || state.request.status !== "loading") return state;
      return { ...state, request: { ...state.request, status: "error", error: action.error }, result: null, selectedRouteId: null };
    case "PLAN_CANCEL":
      if (state.request.status !== "loading") return state;
      // An explicit cancelled state: nothing is kept, and a late answer to the cancelled request is discarded by the sequence bump.
      return { ...state, request: { ...state.request, status: "cancelled", error: null, sequence: state.request.sequence + 1 }, result: null, selectedRouteId: null };
    case "SELECT_ROUTE":
      return { ...state, selectedRouteId: action.routeId };
    case "CLEAR_TRIP":
      return { ...initialPlannerState, scope: state.scope, showCameras: state.showCameras, units: state.units, sheetExpanded: state.sheetExpanded, request: { status: "idle", error: null, sequence: state.request.sequence + 1 } };
    case "TOGGLE_SHEET":
      return { ...state, sheetExpanded: !state.sheetExpanded };
    default:
      return state;
  }
}

export function selectedRoute(state: PlannerState) {
  if (!state.result) return null;
  return state.result.options.find((o) => o.route_id === state.selectedRouteId) ?? state.result.options[0] ?? null;
}

export function canPlan(state: PlannerState): boolean {
  return Boolean(state.origin.confirmed && state.destination.confirmed && state.request.status !== "loading");
}
