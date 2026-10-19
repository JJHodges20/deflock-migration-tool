"""Typed loading and validation of the YAML configuration files.

Everything fails loudly at startup: a missing boundary file or a privacy flag set to true in
production stops the service instead of silently degrading.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from deflockmigration.core.settings import Settings
from deflockmigration.geospatial.boundaries import Boundary, load_boundary


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServiceBoundaryConfig(_Strict):
    id: str
    file: Path
    source: str
    retrieved_at: str
    source_layer_last_edit: str | None = None
    area_km2: float | None = None
    geometry_notes: list[str] = Field(default_factory=list)
    purpose: str | None = None


class EnvelopeConfig(_Strict):
    id: str
    file: Path
    based_on: str
    buffer_m: int
    buffer_method: str | None = None
    bbox_wsen: list[float]
    area_km2: float | None = None
    purpose: str | None = None
    review_note: str | None = None


class CameraSourceConfig(_Strict):
    adapter: Literal["overpass_bounded"]
    endpoint: str
    query_file: Path
    query_bbox_swne: list[float]
    refresh_interval_hours: float = 6
    min_pause_after_429_seconds: int = 30
    user_agent: str | None = None
    later_adapter: str | None = None


class RoutingGraphConfig(_Strict):
    id: str
    extract_url: str
    extract_data_timestamp: str
    extract_sha256: str | None = None
    engine_image: str
    coverage_note: str | None = None
    rebuild_cadence: str | None = None


class BasemapConfig(_Strict):
    id: str
    file: Path
    build: str | None = None
    bbox_wsen: list[float]
    max_zoom: int = 15
    attribution: str = "Protomaps © OpenStreetMap"


class GeocoderConfig(_Strict):
    provider: Literal["self_hosted_nominatim_colorado", "none"]
    external_fallback: Literal["none"] = "none"


class RegionConfig(_Strict):
    region_id: str
    display_name: str
    config_version: int
    service_boundary: ServiceBoundaryConfig
    camera_data_envelope: EnvelopeConfig
    camera_source: CameraSourceConfig
    routing_graph: RoutingGraphConfig
    basemap: BasemapConfig
    geocoder: GeocoderConfig


class CameraSourceProvider(_Strict):
    adapter: Literal["overpass_bounded"]
    endpoint: str
    timeout_seconds: int = 180
    pause_after_rate_limit_seconds: int = 30
    max_attempts: int = 3
    backoff_seconds: int = 5


class RoutingProviderConfig(_Strict):
    provider: Literal["valhalla"]
    image: str
    alternates: int = 2
    max_exclude_locations: int = 50
    max_exclude_polygons_length_m: int = 10000


class GeocodingProviderConfig(_Strict):
    provider: Literal["nominatim_local", "none"]
    search_limit: int = 5
    countrycodes: str = "us"


class BasemapProviderConfig(_Strict):
    provider: Literal["pmtiles_local"]
    path: str
    fonts_path: str
    sprite_path: str
    attribution: str


class ProvidersConfig(_Strict):
    camera_source: CameraSourceProvider
    routing: RoutingProviderConfig
    geocoding: GeocodingProviderConfig
    basemap: BasemapProviderConfig


class ProfileConfig(_Strict):
    label: str
    description: str
    max_extra_seconds: int | None = None
    max_relative_factor: float | None = None


class SearchBudgetConfig(_Strict):
    max_routing_calls_per_trip: int = 8
    planning_deadline_seconds: int = 20


class AvoidanceConfig(_Strict):
    """Candidate-generation knobs (decision 0001 D5). Factors are artificial search costs, never travel time."""

    penalty_factor: float = Field(default=10.0, ge=1.0)          # engine minimum is 1 (no penalty)
    penalty_escalation: float = Field(default=4.0, gt=1.0)       # multiply the factor between penalized requests
    penalty_factor_max: float = Field(default=160.0, ge=1.0)
    penalty_segment_half_length_m: float = Field(default=60.0, ge=5.0)  # route geometry penalized on each side of a pass
    endpoint_margin_m: float = Field(default=100.0, ge=0.0)      # encounters this close to the start or end are unavoidable
    max_exclusions_per_request: int = Field(default=50, ge=1, le=50)  # engine limit (error 157 above 50)

    @model_validator(mode="after")
    def _ordered(self) -> AvoidanceConfig:
        if self.penalty_factor_max < self.penalty_factor:
            raise ValueError("penalty_factor_max must be >= penalty_factor")
        return self


class RouteProfilesConfig(_Strict):
    profiles: dict[str, ProfileConfig]
    search_budget: SearchBudgetConfig
    avoidance: AvoidanceConfig = Field(default_factory=AvoidanceConfig)

    @model_validator(mode="after")
    def _require_standard(self) -> RouteProfilesConfig:
        if "standard" not in self.profiles:
            raise ValueError("route_profiles.yaml must define a 'standard' profile")
        for name, profile in self.profiles.items():
            if name != "standard" and (profile.max_extra_seconds is None or profile.max_relative_factor is None):
                raise ValueError(f"profile '{name}' needs max_extra_seconds and max_relative_factor")
        return self


class SnapshotValidationConfig(_Strict):
    min_element_count: int = 1
    max_count_drop_fraction: float = 0.5
    stale_after_hours: int = 48
    unresolved_disappearance: Literal["retain_as_uncertain", "drop"] = "retain_as_uncertain"
    retain_missing_hours: int = 72


class RetentionConfig(_Strict):
    keep_superseded_snapshots: int = 30
    keep_quarantined_snapshots: int = 10
    max_diff_keys_stored: int = 500


class ProximityConfig(_Strict):
    candidate_radius_m: int = 50
    sensitivity_radii_m: list[int] = Field(default_factory=lambda: [25, 50, 100])


class DataQualityConfig(_Strict):
    snapshot_validation: SnapshotValidationConfig
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    proximity: ProximityConfig


class PrivacyConfig(_Strict):
    log_request_bodies: bool = False
    log_query_strings: bool = False
    persist_trips: bool = False
    external_geocoder_enabled: bool = False
    external_tiles_enabled: bool = False
    analytics_enabled: bool = False


class AppConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    region: RegionConfig
    providers: ProvidersConfig
    route_profiles: RouteProfilesConfig
    data_quality: DataQualityConfig
    privacy: PrivacyConfig
    service_boundary: Boundary
    envelope: Boundary
    camera_query_text: str


class ConfigError(RuntimeError):
    pass


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"configuration file not found: {path}")
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ConfigError(f"configuration file is not a mapping: {path}")
    return data


def _parse(model: type[BaseModel], data: dict, path: Path):
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid configuration in {path}: {exc}") from exc


def load_app_config(settings: Settings) -> AppConfig:
    region_path = settings.resolve(settings.region_config)
    region = _parse(RegionConfig, _read_yaml(region_path), region_path)
    providers_path = settings.resolve(settings.providers_config)
    providers = _parse(ProvidersConfig, _read_yaml(providers_path), providers_path)
    profiles_path = settings.resolve(settings.route_profiles_config)
    profiles = _parse(RouteProfilesConfig, _read_yaml(profiles_path), profiles_path)
    quality_path = settings.resolve(settings.data_quality_config)
    quality = _parse(DataQualityConfig, _read_yaml(quality_path), quality_path)
    privacy_path = settings.resolve(settings.privacy_config)
    privacy = _parse(PrivacyConfig, _read_yaml(privacy_path), privacy_path)

    if settings.app_env == "production":
        for flag, value in privacy.model_dump().items():
            if value:
                raise ConfigError(f"privacy flag '{flag}' must be false in production")

    boundary_path = settings.resolve(region.service_boundary.file)
    envelope_path = settings.resolve(region.camera_data_envelope.file)
    query_path = settings.resolve(region.camera_source.query_file)
    for path in (boundary_path, envelope_path, query_path):
        if not path.exists():
            raise ConfigError(f"referenced data file not found: {path}")

    service_boundary = load_boundary(boundary_path, expected_id=region.service_boundary.id)
    envelope = load_boundary(envelope_path, expected_id=region.camera_data_envelope.id)
    if not envelope.geometry.contains(service_boundary.geometry):
        raise ConfigError("camera-data envelope does not contain the service boundary")
    query_text = query_path.read_text(encoding="utf-8")
    if "bbox:" not in query_text:
        raise ConfigError("camera source query must be a fixed bounded query ([bbox:...])")

    return AppConfig(
        region=region,
        providers=providers,
        route_profiles=profiles,
        data_quality=quality,
        privacy=privacy,
        service_boundary=service_boundary,
        envelope=envelope,
        camera_query_text=query_text,
    )
