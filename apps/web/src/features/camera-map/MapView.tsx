"use client";

import { LngLatBounds, Map as MapLibreMap, Marker, NavigationControl, Popup, addProtocol, setWorkerUrl, type GeoJSONSource, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { layers, namedFlavor } from "@protomaps/basemaps";
import { Protocol } from "pmtiles";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import type { CameraScope, EncounterOut, GeocodeCandidate, RegionResponse, RouteOptionOut } from "@/lib/api/types";
import { clampBbox } from "@/lib/format";
import { emptySummary, summarizeCameraFeatures, type CameraSummary } from "./cameraSummary";

interface Props {
  region: RegionResponse | null;
  route: RouteOptionOut | null;
  options: RouteOptionOut[] | null;
  origin: GeocodeCandidate | null;
  destination: GeocodeCandidate | null;
  pinMode: boolean;
  showCameras: boolean;
  scope: CameraScope;
  highlightRange: [number, number] | null;
  encounters: EncounterOut[] | null;
  onPinPlaced: (lat: number, lon: number) => void;
  onStatus: (status: "ready" | "failed") => void;
}

const CAMERA_MIN_ZOOM = 11;
const MAX_BBOX_DEGREES = 0.6;
const OSM_URL_PREFIX = "https://www.openstreetmap.org/";
let protocolRegistered = false;

function webglAvailable(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function buildStyle(region: RegionResponse): StyleSpecification {
  const origin = window.location.origin;
  const dark = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  return {
    version: 8,
    glyphs: `${origin}${region.basemap.fonts_path}/{fontstack}/{range}.pbf`,
    sprite: `${origin}${region.basemap.sprite_path}`,
    sources: {
      protomaps: { type: "vector", url: `pmtiles://${origin}${region.basemap.path}`, attribution: region.basemap.attribution },
    },
    layers: layers("protomaps", namedFlavor(dark ? "dark" : "light"), { lang: "en" }),
  };
}

function popupElement(properties: Record<string, unknown>): HTMLElement {
  // Built with DOM APIs so source strings are never interpreted as HTML.
  const root = document.createElement("div");
  root.className = "camera-popup";
  const dl = document.createElement("dl");
  const uncertain = properties.uncertain === true;
  const rows: [string, unknown][] = [
    ["Status", uncertain ? `no longer mapped (since ${properties.missing_since ?? "unknown"}); retained as uncertain` : String(properties.lifecycle_state)],
    ["Manufacturer", properties.manufacturer ?? "unknown"],
    ["Flock scope", properties.is_flock ? "yes" : "no"],
    ["Operator", properties.operator ?? "unknown"],
    ["Mapped direction", properties.direction_raw ?? "none"],
    ["In assessed area", properties.in_envelope ? "yes" : "no (outside the data envelope)"],
    ["Last edited", properties.source_timestamp ?? "unknown"],
    ["Check date", properties.check_date ?? "none"],
    ["Source", properties.source_key],
  ];
  for (const [key, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = key;
    const dd = document.createElement("dd");
    dd.textContent = String(value);
    dl.append(dt, dd);
  }
  root.append(dl);
  const url = String(properties.source_url ?? "");
  if (url.startsWith(OSM_URL_PREFIX)) {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "View this record on OpenStreetMap";
    root.append(link);
  }
  const note = document.createElement("p");
  note.textContent = "Mapped record, not a field-verified device. Direction is where contributors believe it points.";
  root.append(note);
  return root;
}

function encounterPopup(properties: Record<string, unknown>): HTMLElement {
  const root = document.createElement("div");
  root.className = "camera-popup";
  const title = document.createElement("strong");
  title.textContent = `${properties.status_label ?? properties.status}`;
  const reason = document.createElement("p");
  reason.textContent = String(properties.reason ?? "");
  root.append(title, reason);
  const url = String(properties.source_url ?? "");
  if (url.startsWith(OSM_URL_PREFIX)) {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "View this record on OpenStreetMap";
    root.append(link);
  }
  return root;
}

export function MapView({ region, route, options, origin, destination, pinMode, showCameras, scope, highlightRange, encounters, onPinPlaced, onStatus }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markersRef = useRef<{ origin?: Marker; destination?: Marker }>({});
  const pinModeRef = useRef(pinMode);
  const onPinPlacedRef = useRef(onPinPlaced);
  const cameraAbortRef = useRef<AbortController | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [summary, setSummary] = useState<CameraSummary>(emptySummary);
  const [overlayState, setOverlayState] = useState<"hidden" | "zoom" | "ready" | "unavailable">("hidden");
  const [snapshotDate, setSnapshotDate] = useState<string | null>(null);
  pinModeRef.current = pinMode;
  onPinPlacedRef.current = onPinPlaced;

  useEffect(() => {
    if (!region || !containerRef.current || mapRef.current) return;
    if (!webglAvailable()) {
      onStatus("failed");
      return;
    }
    try {
      if (!protocolRegistered) {
        // Self-hosted worker (copied from the installed package at build time): MapLibre's own URL derivation
        // fails inside the production bundle, which leaves the map silently unloaded.
        setWorkerUrl(`${window.location.origin}/vendor/maplibre/maplibre-gl-worker.mjs`);
        const protocol = new Protocol();
        addProtocol("pmtiles", protocol.tile);
        protocolRegistered = true;
      }
      const [west, south, east, north] = region.service_boundary.bbox_wsen;
      const map = new MapLibreMap({
        container: containerRef.current,
        style: buildStyle(region),
        bounds: [west, south, east, north],
        fitBoundsOptions: { padding: 24 },
        maxBounds: [region.basemap.bbox_wsen[0] - 0.5, region.basemap.bbox_wsen[1] - 0.5, region.basemap.bbox_wsen[2] + 0.5, region.basemap.bbox_wsen[3] + 0.5],
        maxZoom: 18,
        attributionControl: { compact: false },
      });
      map.addControl(new NavigationControl({ showCompass: false }), "top-right");
      map.on("load", () => {
        map.addSource("service-boundary", { type: "geojson", data: { type: "Feature", properties: {}, geometry: region.service_boundary.geometry } });
        map.addLayer({ id: "service-boundary-line", type: "line", source: "service-boundary", paint: { "line-color": "#1f5f8b", "line-width": 2, "line-dasharray": [2, 2] } });
        // Unselected options: thin dashed grey, drawn under the selected route (pattern and width, not only colour).
        map.addSource("routes-other", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addLayer({ id: "routes-other-casing", type: "line", source: "routes-other", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#ffffff", "line-width": 6 } });
        map.addLayer({ id: "routes-other-line", type: "line", source: "routes-other", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#5b6b7a", "line-width": 3, "line-dasharray": [2, 2] } });
        map.addSource("route", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addLayer({ id: "route-casing", type: "line", source: "route", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#ffffff", "line-width": 9 } });
        map.addLayer({ id: "route-line", type: "line", source: "route", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#1f5f8b", "line-width": 5 } });
        map.addSource("maneuver-highlight", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addLayer({ id: "maneuver-highlight-line", type: "line", source: "maneuver-highlight", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#e8b400", "line-width": 8, "line-opacity": 0.9 } });
        map.addSource("cameras", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addLayer({
          id: "cameras-circle",
          type: "circle",
          source: "cameras",
          paint: {
            "circle-radius": ["case", ["==", ["get", "uncertain"], true], 5, 6],
            "circle-color": ["case", ["==", ["get", "is_flock"], true], "#b3261e", ["!=", ["get", "manufacturer"], null], "#c77a00", "#5b6b7a"],
            "circle-opacity": ["case", ["==", ["get", "uncertain"], true], 0.35, ["==", ["get", "in_envelope"], false], 0.5, 0.95],
            "circle-stroke-color": ["case", ["==", ["get", "uncertain"], true], "#1c2024", "#ffffff"],
            "circle-stroke-width": ["case", ["==", ["get", "in_envelope"], false], 0, 1.5],
          },
        });
        map.addSource("encounters", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addLayer({
          id: "encounters-ring",
          type: "circle",
          source: "encounters",
          paint: {
            "circle-radius": 11,
            "circle-color": "rgba(0,0,0,0)",
            "circle-stroke-width": ["case", ["==", ["get", "status"], "associated"], 3, 2],
            "circle-stroke-color": ["case", ["==", ["get", "status"], "associated"], "#b3261e", ["==", ["get", "status"], "beyond_radius"], "#8a949e", "#c77a00"],
            "circle-stroke-opacity": 0.95,
          },
        });
        map.on("click", "encounters-ring", (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          new Popup({ closeButton: true, maxWidth: "320px" }).setLngLat(event.lngLat).setDOMContent(encounterPopup(feature.properties as Record<string, unknown>)).addTo(map);
        });
        map.on("click", "cameras-circle", (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          new Popup({ closeButton: true, maxWidth: "340px" }).setLngLat(event.lngLat).setDOMContent(popupElement(feature.properties as Record<string, unknown>)).addTo(map);
        });
        map.on("mouseenter", "cameras-circle", () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "cameras-circle", () => {
          map.getCanvas().style.cursor = pinModeRef.current ? "crosshair" : "";
        });
        setLoaded(true);
        onStatus("ready");
      });
      map.on("error", (event) => {
        console.warn("map warning", event.error?.message ?? event);
      });
      map.on("click", (event) => {
        if (pinModeRef.current) {
          onPinPlacedRef.current(event.lngLat.lat, event.lngLat.lng);
        }
      });
      mapRef.current = map;
    } catch (error) {
      console.error("map initialisation failed", error);
      onStatus("failed");
    }
    return () => {
      mapRef.current?.remove();
      mapRef.current = null;
      setLoaded(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [region]);

  useEffect(() => {
    const map = mapRef.current;
    if (map) map.getCanvas().style.cursor = pinMode ? "crosshair" : "";
  }, [pinMode]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    const source = map.getSource("route") as GeoJSONSource | undefined;
    if (!source) return;
    if (route) {
      source.setData({ type: "Feature", properties: {}, geometry: route.geometry });
      const coords = route.geometry.coordinates;
      const bounds = coords.reduce((b, c) => b.extend(c as [number, number]), new LngLatBounds(coords[0] as [number, number], coords[0] as [number, number]));
      const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
      map.fitBounds(bounds, { padding: 48, duration: reduceMotion ? 0 : 600, maxZoom: 15 });
    } else {
      source.setData({ type: "FeatureCollection", features: [] });
    }
  }, [route, loaded]);

  // The other route options stay visible as dashed lines so a comparison is a comparison of paths, not of colours.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    const source = map.getSource("routes-other") as GeoJSONSource | undefined;
    if (!source) return;
    const others = (options ?? []).filter((option) => option.route_id !== route?.route_id);
    source.setData({ type: "FeatureCollection", features: others.map((option) => ({ type: "Feature", properties: { route_id: option.route_id, profiles: option.profiles.join(",") }, geometry: option.geometry })) });
  }, [options, route, loaded]);

  // Encounter rings for the selected route's assessment (counted = red, uncertain = orange, beyond radius = grey).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    const source = map.getSource("encounters") as GeoJSONSource | undefined;
    if (!source) return;
    const labels: Record<string, string> = { associated: "Counted", nearby_unresolved: "Uncertain", no_longer_mapped: "Uncertain (no longer mapped)", outside_envelope: "Uncertain (outside assessed area)", beyond_radius: "Beyond counting radius", excluded_scope: "Not in scope" };
    source.setData({
      type: "FeatureCollection",
      features: (encounters ?? [])
        .filter((e) => e.status !== "excluded_scope")
        .map((e) => ({ type: "Feature", geometry: { type: "Point", coordinates: [e.lon, e.lat] }, properties: { status: e.status, status_label: labels[e.status] ?? e.status, reason: e.reason, source_url: e.source_url } })),
    });
  }, [encounters, loaded]);

  // Highlight the maneuver the user points at in the directions list (instruction-to-geometry alignment).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    const source = map.getSource("maneuver-highlight") as GeoJSONSource | undefined;
    if (!source) return;
    if (route && highlightRange) {
      const [begin, end] = highlightRange;
      const coords = route.geometry.coordinates.slice(Math.max(0, begin), Math.min(route.geometry.coordinates.length, end + 1));
      source.setData(coords.length >= 2 ? { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: coords } } : { type: "FeatureCollection", features: [] });
    } else {
      source.setData({ type: "FeatureCollection", features: [] });
    }
  }, [route, highlightRange, loaded]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    const update = (key: "origin" | "destination", point: GeocodeCandidate | null, color: string) => {
      markersRef.current[key]?.remove();
      markersRef.current[key] = undefined;
      if (point) {
        markersRef.current[key] = new Marker({ color }).setLngLat([point.lon, point.lat]).addTo(map);
      }
    };
    update("origin", origin, "#1f5f8b");
    update("destination", destination, "#b3261e");
  }, [origin, destination, loaded]);

  // Camera overlay from the local snapshot, bounded to the viewport, never per pan when zoomed out.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    const source = map.getSource("cameras") as GeoJSONSource | undefined;
    if (!source) return;
    const refresh = async () => {
      cameraAbortRef.current?.abort();
      if (!showCameras) {
        source.setData({ type: "FeatureCollection", features: [] });
        setOverlayState("hidden");
        return;
      }
      if (map.getZoom() < CAMERA_MIN_ZOOM) {
        source.setData({ type: "FeatureCollection", features: [] });
        setOverlayState("zoom");
        return;
      }
      const b = map.getBounds();
      const bbox = clampBbox([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], MAX_BBOX_DEGREES);
      const controller = new AbortController();
      cameraAbortRef.current = controller;
      try {
        const data = await api.cameras(bbox, scope, controller.signal);
        if (controller.signal.aborted) return;
        source.setData({ type: "FeatureCollection", features: data.features });
        setSummary(summarizeCameraFeatures(data.features));
        setSnapshotDate(data.snapshot.timestamp_osm_base);
        setOverlayState("ready");
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          source.setData({ type: "FeatureCollection", features: [] });
          setOverlayState("unavailable");
        }
      }
    };
    void refresh();
    map.on("moveend", refresh);
    return () => {
      map.off("moveend", refresh);
      cameraAbortRef.current?.abort();
    };
  }, [showCameras, scope, loaded]);

  return (
    <>
      {/* Inline positioning wins over MapLibre's own `.maplibregl-map { position: relative }` rule, which would collapse the container's height. */}
      <div ref={containerRef} className="map-container" style={{ position: "absolute", inset: 0 }} role="application" aria-label="Map of the Denver pilot area" data-testid="map" />
      {overlayState !== "hidden" && (
        <div className="map-legend" role="status" data-testid="camera-legend">
          {overlayState === "zoom" && <span>Zoom in to see mapped cameras.</span>}
          {overlayState === "unavailable" && <span>Camera records are unavailable right now.</span>}
          {overlayState === "ready" && (
            <>
              <strong>{summary.total} mapped records in view</strong>
              <ul>
                <li><span className="swatch swatch-flock" /> Flock-tagged: {summary.flock}</li>
                <li><span className="swatch swatch-other" /> Other manufacturer: {summary.otherKnown}</li>
                <li><span className="swatch swatch-unknown" /> Manufacturer unknown: {summary.unknown}</li>
                <li><span className="swatch swatch-uncertain" /> No longer mapped, retained as uncertain: {summary.uncertain}</li>
                {summary.outsideEnvelope > 0 && <li>Outside the assessed area: {summary.outsideEnvelope}</li>}
              </ul>
              <span className="legend-note">Records, not devices. Snapshot data as of {snapshotDate ?? "unknown"}.</span>
            </>
          )}
        </div>
      )}
    </>
  );
}
