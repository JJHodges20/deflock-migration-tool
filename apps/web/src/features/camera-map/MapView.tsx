"use client";

import { LngLatBounds, Map as MapLibreMap, Marker, NavigationControl, Popup, addProtocol, type GeoJSONSource, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { layers, namedFlavor } from "@protomaps/basemaps";
import { Protocol } from "pmtiles";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import type { CameraScope, GeocodeCandidate, RegionResponse, RouteOptionOut } from "@/lib/api/types";
import { clampBbox } from "@/lib/format";

interface Props {
  region: RegionResponse | null;
  route: RouteOptionOut | null;
  origin: GeocodeCandidate | null;
  destination: GeocodeCandidate | null;
  pinMode: boolean;
  showCameras: boolean;
  scope: CameraScope;
  onPinPlaced: (lat: number, lon: number) => void;
  onStatus: (status: "ready" | "failed") => void;
}

const CAMERA_MIN_ZOOM = 11;
const MAX_BBOX_DEGREES = 0.6;
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
  const rows: [string, unknown][] = [
    ["Manufacturer", properties.manufacturer ?? "unknown"],
    ["Flock scope", properties.is_flock ? "yes" : "no"],
    ["Operator", properties.operator ?? "unknown"],
    ["Mapped direction", properties.direction_raw ?? "none"],
    ["Lifecycle", properties.lifecycle_state],
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
  const note = document.createElement("p");
  note.textContent = "Mapped record, not a field-verified device. Direction is where contributors believe it points.";
  root.append(dl, note);
  return root;
}

export function MapView({ region, route, origin, destination, pinMode, showCameras, scope, onPinPlaced, onStatus }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markersRef = useRef<{ origin?: Marker; destination?: Marker }>({});
  const pinModeRef = useRef(pinMode);
  const onPinPlacedRef = useRef(onPinPlaced);
  const cameraAbortRef = useRef<AbortController | null>(null);
  const [loaded, setLoaded] = useState(false);
  pinModeRef.current = pinMode;
  onPinPlacedRef.current = onPinPlaced;

  // Create the map once the region (and therefore the basemap paths) is known.
  useEffect(() => {
    if (!region || !containerRef.current || mapRef.current) return;
    if (!webglAvailable()) {
      onStatus("failed");
      return;
    }
    try {
      if (!protocolRegistered) {
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
        map.addSource("route", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addLayer({ id: "route-casing", type: "line", source: "route", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#ffffff", "line-width": 9 } });
        map.addLayer({ id: "route-line", type: "line", source: "route", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#1f5f8b", "line-width": 5 } });
        map.addSource("cameras", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addLayer({
          id: "cameras-circle",
          type: "circle",
          source: "cameras",
          paint: { "circle-radius": 6, "circle-color": ["case", ["==", ["get", "is_flock"], true], "#b3261e", "#c77a00"], "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.5 },
        });
        map.on("click", "cameras-circle", (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          new Popup({ closeButton: true, maxWidth: "320px" }).setLngLat(event.lngLat).setDOMContent(popupElement(feature.properties as Record<string, unknown>)).addTo(map);
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
        // Missing optional sprites or tiles outside the extract are not fatal; log to the console only.
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

  // Route geometry.
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

  // Origin / destination markers.
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
      if (!showCameras || map.getZoom() < CAMERA_MIN_ZOOM) {
        source.setData({ type: "FeatureCollection", features: [] });
        return;
      }
      const b = map.getBounds();
      const bbox = clampBbox([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], MAX_BBOX_DEGREES);
      const controller = new AbortController();
      cameraAbortRef.current = controller;
      try {
        const data = await api.cameras(bbox, scope, controller.signal);
        if (!controller.signal.aborted) source.setData({ type: "FeatureCollection", features: data.features });
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          source.setData({ type: "FeatureCollection", features: [] });
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

  return <div ref={containerRef} className="map-container" role="application" aria-label="Map of the Denver pilot area" data-testid="map" />;
}
