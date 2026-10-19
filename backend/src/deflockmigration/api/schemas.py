"""Request and response contracts (roadmap sections 7 and 14)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from deflockmigration.domain.routes import CameraScope, RouteProfile

MANEUVER_TYPE_NAMES = {
    0: "none", 1: "start", 2: "start_right", 3: "start_left", 4: "destination", 5: "destination_right",
    6: "destination_left", 7: "becomes", 8: "continue", 9: "slight_right", 10: "right", 11: "sharp_right",
    12: "uturn_right", 13: "uturn_left", 14: "sharp_left", 15: "left", 16: "slight_left", 17: "ramp_straight",
    18: "ramp_right", 19: "ramp_left", 20: "exit_right", 21: "exit_left", 22: "stay_straight", 23: "stay_right",
    24: "stay_left", 25: "merge", 26: "roundabout_enter", 27: "roundabout_exit", 28: "ferry_enter", 29: "ferry_exit",
    37: "merge_right", 38: "merge_left", 39: "elevator_enter", 40: "steps_enter", 41: "escalator_enter",
    42: "building_enter", 43: "building_exit",
}

DISCLAIMER = (
    "Routes are advisory and planned while stationary. Road signs, access restrictions, closures, and actual conditions "
    "take precedence. Camera counts describe mapped OpenStreetMap records, not physical devices; unmapped or mislocated "
    "cameras may still be present. No route is surveillance-free and no recording-free journey is promised."
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LatLonIn(_Strict):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class DetourLimitsIn(_Strict):
    max_extra_seconds: int = Field(default=600, ge=0, le=7200)
    max_relative_factor: float = Field(default=1.5, ge=1.0, le=3.0)


class PlanRequest(_Strict):
    origin: LatLonIn
    destination: LatLonIn
    region_id: str = Field(default="denver", max_length=40)
    profiles: list[RouteProfile] = Field(default_factory=lambda: [RouteProfile.STANDARD], max_length=3)
    camera_scope: CameraScope = CameraScope.ALL_ALPR
    detour_limits: DetourLimitsIn | None = None
    units: Literal["km", "mi"] = "km"


class ManeuverOut(BaseModel):
    instruction: str
    verbal_pre_transition_instruction: str | None = None
    street_names: list[str]
    begin_street_names: list[str]
    length_meters: float
    time_seconds: float
    type: int
    type_name: str
    begin_shape_index: int
    end_shape_index: int
    roundabout_exit_count: int | None = None
    toll: bool
    highway: bool


class RouteOptionOut(BaseModel):
    route_id: str
    profiles: list[str]
    geometry: dict[str, Any]
    estimated_duration_seconds: float
    length_meters: float
    extra_duration_seconds: float
    extra_distance_meters: float
    origin_snap_distance_meters: float
    destination_snap_distance_meters: float
    matched_camera_record_count: int | None
    uncertain_nearby_camera_count: int | None
    counting_method_version: str | None
    camera_scope: str
    camera_snapshot_id: str | None
    camera_source_as_of: str | None
    camera_downloaded_at: str | None
    road_graph_version: str
    assessment_coverage_status: str
    search_status: str
    warnings: list[str]
    maneuvers: list[ManeuverOut]
    has_highway: bool
    has_toll: bool
    engine_candidate: str


class PlanResponse(BaseModel):
    request_id: str
    region_id: str
    reference_duration_seconds: float
    candidates_evaluated: int
    search_status: str
    assessment_coverage_status: str
    warnings: list[str]
    options: list[RouteOptionOut]
    disclaimer: str


class GeocodeRequest(_Strict):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=10)


class GeocodeCandidateOut(BaseModel):
    label: str
    lat: float
    lon: float
    source: str
    category: str | None
    importance: float | None
    note: str | None = None
    inside_service_boundary: bool


class GeocodeResponse(BaseModel):
    query_kind: Literal["coordinates", "search"]
    provider: str
    candidates: list[GeocodeCandidateOut]


class ReverseGeocodeRequest(_Strict):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class ReverseGeocodeResponse(BaseModel):
    provider: str
    found: bool
    label: str | None
    category: str | None
    matched_lat: float | None
    matched_lon: float | None
    inside_service_boundary: bool


class ProfileOut(BaseModel):
    label: str
    description: str
    max_extra_seconds: int | None
    max_relative_factor: float | None


class RegionResponse(BaseModel):
    region_id: str
    display_name: str
    config_version: int
    service_boundary: dict[str, Any]
    camera_data_envelope: dict[str, Any]
    routing_graph: dict[str, Any]
    basemap: dict[str, Any]
    capabilities: dict[str, Any]
    profiles: dict[str, ProfileOut]
    camera_scopes: list[str]
    attributions: list[str]
    disclaimer: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    error: ErrorBody
    request_id: str
