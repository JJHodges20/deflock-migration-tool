// Hand-maintained mirror of backend/src/deflockmigration/api/schemas.py.
// A contract test on the backend pins these field names; update both sides together.

import type { Feature, Geometry, Point } from "geojson";

export type LatLon = { lat: number; lon: number };
export type RouteProfileName = "standard" | "balanced" | "fewest_mapped";
export type CameraScope = "all_alpr" | "flock_only";

export interface ManeuverOut {
  instruction: string;
  verbal_pre_transition_instruction: string | null;
  street_names: string[];
  begin_street_names: string[];
  length_meters: number;
  time_seconds: number;
  type: number;
  type_name: string;
  begin_shape_index: number;
  end_shape_index: number;
  roundabout_exit_count: number | null;
  toll: boolean;
  highway: boolean;
}

export interface RouteOptionOut {
  route_id: string;
  profiles: RouteProfileName[];
  geometry: { type: "LineString"; coordinates: [number, number][] };
  estimated_duration_seconds: number;
  length_meters: number;
  extra_duration_seconds: number;
  extra_distance_meters: number;
  matched_camera_record_count: number | null;
  uncertain_nearby_camera_count: number | null;
  counting_method_version: string | null;
  camera_scope: CameraScope;
  camera_snapshot_id: string | null;
  camera_source_as_of: string | null;
  camera_downloaded_at: string | null;
  road_graph_version: string;
  assessment_coverage_status: "not_assessed" | "complete" | "partial";
  search_status: string;
  warnings: string[];
  maneuvers: ManeuverOut[];
  has_highway: boolean;
  has_toll: boolean;
  engine_candidate: string;
}

export interface PlanRequest {
  origin: LatLon;
  destination: LatLon;
  region_id: string;
  profiles: RouteProfileName[];
  camera_scope: CameraScope;
  detour_limits?: { max_extra_seconds: number; max_relative_factor: number };
  units: "km" | "mi";
}

export interface PlanResponse {
  request_id: string;
  region_id: string;
  reference_duration_seconds: number;
  candidates_evaluated: number;
  search_status: string;
  assessment_coverage_status: "not_assessed" | "complete" | "partial";
  warnings: string[];
  options: RouteOptionOut[];
  disclaimer: string;
}

export interface GeocodeCandidate {
  label: string;
  lat: number;
  lon: number;
  source: string;
  category: string | null;
  importance: number | null;
  inside_service_boundary: boolean;
}

export interface GeocodeResponse {
  query_kind: "coordinates" | "search";
  provider: string;
  candidates: GeocodeCandidate[];
}

export interface ProfileOut {
  label: string;
  description: string;
  max_extra_seconds: number | null;
  max_relative_factor: number | null;
}

export interface RegionResponse {
  region_id: string;
  display_name: string;
  config_version: number;
  service_boundary: { id: string; geometry: Geometry; bbox_wsen: number[]; source: string; retrieved_at: string };
  camera_data_envelope: { id: string; bbox_wsen: number[]; buffer_m: number; meaning: string };
  routing_graph: { id: string; extract_data_timestamp: string; engine_image: string };
  basemap: { path: string; fonts_path: string; sprite_path: string; attribution: string; bbox_wsen: number[]; max_zoom: number };
  capabilities: { geocoder_configured: boolean; geocoder_provider: string; routing_provider: string; camera_source_adapter: string; camera_assessment: string; coordinate_input: boolean; map_pins: boolean };
  profiles: Record<RouteProfileName, ProfileOut>;
  camera_scopes: CameraScope[];
  attributions: string[];
  disclaimer: string;
}

export interface DataHealth {
  region_id: string;
  service_boundary_id: string;
  envelope_id: string;
  config_version: number;
  camera_source: Record<string, unknown>;
  snapshot: {
    snapshot_id: string;
    timestamp_osm_base: string | null;
    downloaded_at: string;
    promoted_at: string | null;
    element_count: number;
    record_count: number;
    alpr_count: number;
    flock_count: number;
    unknown_manufacturer_count: number;
    parser_version: string;
    quality: Record<string, unknown>;
    counts_meaning: string;
  } | null;
  last_sync: Record<string, unknown> | null;
  last_failure: Record<string, unknown> | null;
  staleness: { age_hours?: number | null; stale_after_hours?: number; is_stale?: boolean; message?: string };
  router: { available: boolean; version: string | null; tileset_last_modified: string | null; has_tiles: boolean | null; graph_id: string; extract_data_timestamp: string; message: string | null };
  geocoder: { configured: boolean; available: boolean; provider: string; data_updated: string | null; message: string | null };
  basemap: { id: string; attribution: string; max_zoom: number };
  database: { available: boolean; message?: string };
  generated_at: string;
}

export interface CameraFeatureProperties {
  source_key: string;
  source_version: number | null;
  source_timestamp: string | null;
  manufacturer: string | null;
  is_flock: boolean;
  operator: string | null;
  direction_raw: string | null;
  camera_direction_raw: string | null;
  direction_conflict: boolean;
  lifecycle_state: string;
  check_date: string | null;
  geometry_quality: string;
}

export interface CamerasResponse {
  type: "FeatureCollection";
  features: Feature<Point, CameraFeatureProperties>[];
  snapshot: { snapshot_id: string; timestamp_osm_base: string | null; downloaded_at: string; scope: CameraScope; truncated: boolean; counts_meaning: string };
}

export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown> };
  request_id: string;
}
