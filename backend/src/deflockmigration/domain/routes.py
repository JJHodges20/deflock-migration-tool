"""Routing domain objects shared by adapters, use cases, and the API."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class RouteProfile(StrEnum):
    STANDARD = "standard"
    BALANCED = "balanced"
    FEWEST_MAPPED = "fewest_mapped"


class CameraScope(StrEnum):
    ALL_ALPR = "all_alpr"
    FLOCK_ONLY = "flock_only"


class AssessmentCoverage(StrEnum):
    NOT_ASSESSED = "not_assessed"
    COMPLETE = "complete"
    PARTIAL = "partial"


@dataclass(frozen=True)
class LatLon:
    lat: float
    lon: float


@dataclass(frozen=True)
class Maneuver:
    instruction: str
    type: int
    length_m: float
    time_s: float
    begin_shape_index: int
    end_shape_index: int
    street_names: list[str] = field(default_factory=list)
    begin_street_names: list[str] = field(default_factory=list)
    verbal_pre_transition_instruction: str | None = None
    roundabout_exit_count: int | None = None
    toll: bool = False
    highway: bool = False


@dataclass(frozen=True)
class EngineRoute:
    """A single road-valid path produced by the routing engine, untouched by camera logic."""

    engine_route_id: str
    shape: list[tuple[float, float]]  # (lat, lon)
    duration_s: float
    length_m: float
    maneuvers: list[Maneuver]
    has_highway: bool
    has_toll: bool
    warnings: list[str] = field(default_factory=list)
    source: str = "primary"  # primary | alternate

    def encoded_shape_key(self) -> str:
        """Stable identity for duplicate suppression (geometry only)."""
        return ";".join(f"{lat:.5f},{lon:.5f}" for lat, lon in self.shape)


@dataclass(frozen=True)
class RouterStatus:
    available: bool
    version: str | None = None
    tileset_last_modified: str | None = None
    has_tiles: bool | None = None
    has_admins: bool | None = None
    has_timezones: bool | None = None
    message: str | None = None
