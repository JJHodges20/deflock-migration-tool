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

export type EncounterStatus = "associated" | "nearby_unresolved" | "no_longer_mapped" | "outside_envelope" | "beyond_radius" | "excluded_scope";

export interface AssociationOut {
  method: string;
  radius_m: number;
  graph_version: string;
  nearest_way_id: number | null;
  nearest_road_names: string[];
  nearest_distance_m: number | null;
  route_way_id: number | null;
  route_road_names: string[];
  route_way_distance_m: number | null;
  candidates_within_radius: number;
  same_road: boolean;
  ambiguous: boolean;
  grade_separated: boolean;
}

export interface EncounterOut {
  source_key: string;
  lat: number;
  lon: number;
  status: EncounterStatus;
  reason: string;
  distance_m: number;
  position_m: number | null;
  position_fraction: number | null;
  pass_count: number;
  site_group_id: string;
  manufacturer: string | null;
  is_flock: boolean;
  lifecycle_state: string;
  direction_raw: string | null;
  direction_conflict: boolean;
  heading_relation: string | null;
  in_envelope: boolean;
  source_url: string;
  source_timestamp: string | null;
  check_date: string | null;
  association: AssociationOut | null;
}

export interface AssessmentOut {
  status: "complete" | "partial" | "not_assessed";
  counting_method_version: string;
  radius_m: number;
  scope: string;
  snapshot_id: string | null;
  graph_version: string | null;
  coverage_fraction: number | null;
  matched_record_count: number | null;
  uncertain_record_count: number | null;
  sensitivity: { radius_m: number; records_within: number }[];
  encounters: EncounterOut[];
  warnings: string[];
  meaning: string;
}

export interface RouteOptionOut {
  route_id: string;
  profiles: RouteProfileName[];
  geometry: { type: "LineString"; coordinates: [number, number][] };
  estimated_duration_seconds: number;
  length_meters: number;
  extra_duration_seconds: number;
  extra_distance_meters: number;
  origin_snap_distance_meters: number;
  destination_snap_distance_meters: number;
  matched_camera_record_count: number | null;
  uncertain_nearby_camera_count: number | null;
  exposure_count: number | null;
  generated_by: string;
  detour_bound_seconds: number | null;
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
  assessment: AssessmentOut | null;
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

export type ProfileOutcomeKind = "improved" | "same_as_standard" | "not_assessed";
export type SearchStatus = "completed" | "budget_exhausted" | "partial" | "not_run";

export interface ProfileOutcomeOut {
  profile: RouteProfileName;
  outcome: ProfileOutcomeKind;
  message: string;
  max_extra_seconds: number | null;
  max_relative_factor: number | null;
  bound_seconds: number | null;
  best_exposure_count: number | null;
  route_id: string | null;
}

export interface SearchOut {
  status: SearchStatus;
  method_version: string;
  routing_calls_used: number;
  routing_calls_budget: number;
  planning_deadline_seconds: number;
  elapsed_seconds: number;
  candidates_generated: number;
  candidates_assessed: number;
  iterations: number;
  notes: string[];
  profile_outcomes: ProfileOutcomeOut[];
  meaning: string;
}

export interface PlanResponse {
  request_id: string;
  region_id: string;
  reference_duration_seconds: number;
  candidates_evaluated: number;
  search_status: SearchStatus;
  assessment_coverage_status: "not_assessed" | "complete" | "partial";
  warnings: string[];
  options: RouteOptionOut[];
  search: SearchOut;
  disclaimer: string;
}

export interface GeocodeCandidate {
  label: string;
  lat: number;
  lon: number;
  source: string;
  category: string | null;
  importance: number | null;
  note?: string | null;
  inside_service_boundary: boolean;
}

export interface GeocodeResponse {
  query_kind: "coordinates" | "search";
  provider: string;
  candidates: GeocodeCandidate[];
}

export interface ReverseGeocodeResponse {
  provider: string;
  found: boolean;
  label: string | null;
  category: string | null;
  matched_lat: number | null;
  matched_lon: number | null;
  inside_service_boundary: boolean;
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

export interface SyncJobView {
  status: string;
  trigger: string;
  started_at: string;
  finished_at: string | null;
  snapshot_id: string | null;
  http_status: number | null;
  attempts: number;
  added: number | null;
  changed: number | null;
  no_longer_present: number | null;
  message: string | null;
}

export interface SnapshotDiffView {
  added: number;
  changed: number;
  missing: number;
  reappeared: number;
  carried: number;
  expired: number;
}

export interface SchedulerView {
  interval_hours: number;
  manual_refresh_cooldown_minutes: number;
  last_trigger: string | null;
  runs_only_while_stack_is_up: boolean;
  note: string;
  next_due_at: string | null;
  due_in_seconds: number;
  overdue: boolean;
  cooldown_remaining_seconds: number;
  state: string;
}

export interface ProviderPolicyView {
  endpoint: string;
  query: string;
  one_request_at_a_time: boolean;
  refresh_interval_hours: number;
  identifies_application: boolean;
  timeout_seconds: number;
  pause_after_rate_limit_seconds: number;
  max_attempts: number;
  backoff_seconds: number;
  no_endpoint_rotation: boolean;
}

export interface SnapshotDiffHistoryItem {
  snapshot_id: string;
  previous_snapshot_id: string | null;
  snapshot_state: string;
  source_as_of: string | null;
  downloaded_at: string | null;
  promoted_at: string | null;
  added: number;
  changed: number;
  missing: number;
  reappeared: number;
  carried: number;
  expired: number;
  alpr_count: number;
  in_envelope_alpr_count: number;
  review_note: string | null;
}

export interface DiffHistoryResponse {
  region_id: string;
  diffs: SnapshotDiffHistoryItem[];
  meaning: string;
}

export interface RequestMetrics {
  count: number;
  rejected_4xx: number;
  errors_5xx: number;
  samples: number;
  p50_ms: number | null;
  p95_ms: number | null;
  max_ms: number | null;
}

export interface ServiceMetrics {
  uptime_seconds: number;
  requests: Record<string, RequestMetrics>;
  plans: { count: number; by_search_status: Record<string, number>; options_returned: Record<string, number>; routing_calls_total: number; errors_by_code: Record<string, number>; elapsed_p50_ms: number | null; elapsed_p95_ms: number | null; elapsed_max_ms: number | null };
  meaning: string;
  process: { version: string; rss_mb: number | null };
  storage: { available: boolean; message?: string; snapshots_by_state?: Record<string, number>; camera_record_rows?: number; snapshot_diff_rows?: number; association_cache_rows?: number; sync_job_rows?: number; raw_snapshot_bytes?: number; database_bytes?: number };
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
    in_envelope_alpr_count: number;
    no_longer_mapped_count: number;
    previous_active_snapshot_id: string | null;
    parser_version: string;
    quality: Record<string, unknown>;
    review_note: string | null;
    diff: SnapshotDiffView | null;
    counts_meaning: string;
  } | null;
  inventory: {
    retain_missing_hours: number;
    unresolved_disappearance: string;
    keep_superseded_snapshots: number;
    keep_quarantined_snapshots: number;
    pending_review: { snapshot_id: string; created_at: string; reason: string | null; alpr_count: number }[];
    retained_snapshots?: number;
  };
  last_sync: SyncJobView | null;
  last_failure: SyncJobView | null;
  recent_syncs: SyncJobView[];
  staleness: { age_hours?: number | null; stale_after_hours?: number; is_stale?: boolean; message?: string };
  scheduler?: SchedulerView;
  provider_policy?: ProviderPolicyView;
  router: { available: boolean; version: string | null; tileset_last_modified: string | null; has_tiles: boolean | null; graph_id: string; extract_data_timestamp: string; rebuild_cadence?: string | null; message: string | null };
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
  lifecycle_evidence: string | null;
  uncertain: boolean;
  check_date: string | null;
  geometry_quality: string;
  in_envelope: boolean;
  missing_since: string | null;
  source_url: string;
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
