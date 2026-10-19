"use client";

import type { GeocodeCandidate } from "@/lib/api/types";
import type { EndpointKey, EndpointState } from "./plannerReducer";

interface Props {
  endpoint: EndpointKey;
  label: string;
  state: EndpointState;
  pinModeActive: boolean;
  geocoderConfigured: boolean;
  onTextChange: (text: string) => void;
  onSearch: () => void;
  onConfirm: (candidate: GeocodeCandidate) => void;
  onClear: () => void;
  onTogglePinMode: () => void;
  onUseLocation?: () => void; // optional one-shot device location (roadmap section 12); only after this deliberate action
  locating?: boolean;
}

export function EndpointInput({ endpoint, label, state, pinModeActive, geocoderConfigured, onTextChange, onSearch, onConfirm, onClear, onTogglePinMode, onUseLocation, locating = false }: Props) {
  const inputId = `${endpoint}-input`;
  const placeholder = geocoderConfigured ? "Address, place, or lat, lon" : "lat, lon (address search not configured)";
  const canLocate = Boolean(onUseLocation); // the planner decides support after mount, so server and client HTML match
  return (
    <div className="field" data-testid={`${endpoint}-field`}>
      <label htmlFor={inputId}>{label}</label>
      <form
        className="row"
        onSubmit={(event) => {
          event.preventDefault();
          onSearch();
        }}
      >
        <input
          id={inputId}
          className="input"
          type="text"
          autoComplete="off"
          spellCheck={false}
          placeholder={placeholder}
          value={state.text}
          onChange={(event) => onTextChange(event.target.value)}
          aria-describedby={`${endpoint}-status ${endpoint}-help`}
          style={{ flex: 1 }}
        />
        <button type="submit" className="btn" disabled={state.searching || state.text.trim().length === 0}>
          {state.searching ? "Searching…" : "Search"}
        </button>
      </form>
      <span id={`${endpoint}-help`} className="visually-hidden">
        Type an address, a place name, or coordinates as latitude, longitude, then press Search and confirm a match. Searches run only when you submit them.
      </span>
      <div className="row">
        <button type="button" className={`btn btn-small${pinModeActive ? " btn-active" : ""}`} onClick={onTogglePinMode} aria-pressed={pinModeActive}>
          {pinModeActive ? "Click the map to place the pin" : "Use map pin"}
        </button>
        {canLocate && (
          <button type="button" className="btn btn-small" onClick={onUseLocation} disabled={locating} data-testid={`${endpoint}-use-location`} aria-describedby={`${endpoint}-location-note`}>
            {locating ? "Locating…" : "Use my location"}
          </button>
        )}
        {(state.confirmed || state.text) && (
          <button type="button" className="btn btn-small" onClick={onClear}>
            Clear
          </button>
        )}
      </div>
      {canLocate && (
        <span id={`${endpoint}-location-note`} className="disclaimer">
          Asks the browser for your position once, only when you press the button; the app never tracks you.
        </span>
      )}
      <div id={`${endpoint}-status`} aria-live="polite">
        {state.confirmed && (
          <div className="confirmed">
            <strong>Confirmed:</strong> {state.confirmed.label}
            {!state.confirmed.inside_service_boundary && <div className="notice notice-warn">This point is outside the Denver pilot area; planning will not work from here.</div>}
          </div>
        )}
        {state.error && (
          <div className={`notice ${state.error.code === "NO_MATCH" ? "notice-info" : "notice-error"}`} role={state.error.code === "NO_MATCH" ? "status" : "alert"}>
            {state.error.message}
          </div>
        )}
        {state.candidates.length > 0 && (
          <fieldset>
            <legend>{state.candidates.length === 1 ? "Confirm this match" : "Choose a match"}</legend>
            <ul className="candidates">
              {state.candidates.map((candidate, index) => (
                <li key={`${candidate.lat},${candidate.lon},${index}`} className="candidate">
                  <input
                    type="radio"
                    id={`${endpoint}-candidate-${index}`}
                    name={`${endpoint}-candidate`}
                    onChange={() => onConfirm(candidate)}
                  />
                  <label htmlFor={`${endpoint}-candidate-${index}`}>
                    {candidate.label}
                    {candidate.category && candidate.category !== "coordinates" && <span className="desc"> {candidate.category}</span>}
                    {!candidate.inside_service_boundary && <span className="desc"> (outside the pilot area)</span>}
                    {candidate.note && <span className="desc"> {candidate.note}</span>}
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>
        )}
      </div>
    </div>
  );
}
