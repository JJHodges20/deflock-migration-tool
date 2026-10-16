"""Camera inventory domain objects. Counts describe mapped records, never physical devices."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum


class LifecycleState(StrEnum):
    MAPPED = "mapped"
    REMOVED = "removed"
    WAS = "was"
    DESTROYED = "destroyed"
    DISUSED = "disused"
    PLANNED = "planned"


@dataclass(frozen=True)
class NormalizedCamera:
    source_key: str  # osm:node:123
    source_type: str
    source_id: int
    source_version: int | None
    source_timestamp: dt.datetime | None
    lat: float
    lon: float
    geometry_quality: str  # point | representative_point
    raw_tags: dict[str, str]
    is_alpr: bool
    alpr_evidence: str
    manufacturer_raw: str | None
    manufacturer_normalized: str | None
    is_flock: bool
    operator: str | None
    direction_raw: str | None
    camera_direction_raw: str | None
    direction_parsed_deg: float | None
    direction_conflict: bool
    lifecycle_state: LifecycleState
    lifecycle_evidence: str | None
    check_date: str | None
    parse_warnings: list[str] = field(default_factory=list)
