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
}

export function EndpointInput({ endpoint, label, state, pinModeActive, geocoderConfigured, onTextChange, onSearch, onConfirm, onClear, onTogglePinMode }: Props) {
  const inputId = `${endpoint}-input`;
  const placeholder = geocoderConfigured ? "Address, place, or lat, lon" : "lat, lon (address search not configured)";
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
          aria-describedby={`${endpoint}-status`}
          style={{ flex: 1 }}
        />
        <button type="submit" className="btn" disabled={state.searching || state.text.trim().length === 0}>
          {state.searching ? "Searching…" : "Search"}
        </button>
      </form>
      <div className="row">
        <button type="button" className={`btn btn-small${pinModeActive ? " btn-active" : ""}`} onClick={onTogglePinMode} aria-pressed={pinModeActive}>
          {pinModeActive ? "Click the map to place the pin" : "Use map pin"}
        </button>
        {(state.confirmed || state.text) && (
          <button type="button" className="btn btn-small" onClick={onClear}>
            Clear
          </button>
        )}
      </div>
      <div id={`${endpoint}-status`} aria-live="polite">
        {state.confirmed && (
          <div className="confirmed">
            <strong>Confirmed:</strong> {state.confirmed.label}
            {!state.confirmed.inside_service_boundary && <div className="notice notice-warn">This point is outside the Denver pilot area; planning will not work from here.</div>}
          </div>
        )}
        {state.error && <div className={`notice ${state.error.code === "NO_MATCH" ? "notice-info" : "notice-error"}`}>{state.error.message}</div>}
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
