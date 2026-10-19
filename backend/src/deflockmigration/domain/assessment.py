"""Encounter assessment domain objects (roadmap section 9).

Vocabulary: an *encounter* is a mapped camera record near a route. It is *associated* when the road the
record most plausibly sits on is a road the route actually traverses; otherwise it stays *uncertain*.
Counts describe mapped records, never physical devices, people, or plates.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum

COUNTING_METHOD_VERSION = "assess-1.0"


class EncounterStatus(StrEnum):
    ASSOCIATED = "associated"                  # counted: route traverses the record's nearest road within the radius
    NEARBY_UNRESOLVED = "nearby_unresolved"    # uncertain: near the route but on a different or ambiguous road
    NO_LONGER_MAPPED = "no_longer_mapped"      # uncertain: carried record absent from the latest source query
    OUTSIDE_ENVELOPE = "outside_envelope"      # uncertain: outside the assessed data area
    BEYOND_RADIUS = "beyond_radius"            # listed for sensitivity only (within the largest radius, not the counting radius)
    EXCLUDED_SCOPE = "excluded_scope"          # listed for transparency; not in the selected camera scope


UNCERTAIN_STATUSES = {EncounterStatus.NEARBY_UNRESOLVED, EncounterStatus.NO_LONGER_MAPPED, EncounterStatus.OUTSIDE_ENVELOPE}


@dataclass(frozen=True)
class CameraNearRoute:
    """A camera record within the largest sensitivity radius of a route (Stage A input)."""

    source_key: str
    lat: float
    lon: float
    is_alpr: bool
    is_flock: bool
    manufacturer: str | None
    lifecycle_state: str
    direction_raw: str | None
    direction_parsed_deg: float | None
    direction_conflict: bool
    in_envelope: bool
    operator: str | None
    source_timestamp: dt.datetime | None
    check_date: str | None
    distance_m: float


@dataclass(frozen=True)
class RoadCandidate:
    """A drivable road near a camera, from the routing graph (one entry per OSM way, nearest sub-edge)."""

    way_id: int
    names: list[str]
    distance_m: float
    road_class: str | None
    use: str | None
    bridge: bool
    tunnel: bool
    correlated_lat: float | None = None
    correlated_lon: float | None = None
    side_of_street: str | None = None


def road_key(names: list[str], way_id: int) -> tuple:
    """Identity of a road for association: its name set when named, otherwise the way id.
    OpenStreetMap splits one street into consecutive ways; those segments share a key."""
    cleaned = sorted({n.strip().lower() for n in names if n and n.strip()})
    return ("names", *cleaned) if cleaned else ("way", way_id)


AMBIGUITY_MARGIN_M = 10.0


def is_ambiguous(candidates: list["RoadCandidate"]) -> bool:
    """True when a *different* road is within AMBIGUITY_MARGIN_M of being as close as the nearest one."""
    if not candidates:
        return False
    nearest = candidates[0]
    keys = {road_key(c.names, c.way_id) for c in candidates if c.distance_m <= nearest.distance_m + AMBIGUITY_MARGIN_M}
    return len(keys) > 1


@dataclass(frozen=True)
class RouteEdge:
    """One traversed edge of the route, from the engine's edge attributes."""

    way_id: int
    names: list[str]
    begin_shape_index: int
    end_shape_index: int
    road_class: str | None
    use: str | None
    bridge: bool
    tunnel: bool
    begin_heading: float | None
    end_heading: float | None
    length_m: float


@dataclass(frozen=True)
class Association:
    method: str
    radius_m: float
    graph_version: str
    nearest_way_id: int | None
    nearest_road_names: list[str]
    nearest_distance_m: float | None
    route_way_id: int | None
    route_road_names: list[str]
    route_way_distance_m: float | None
    candidates_within_radius: int
    same_road: bool
    ambiguous: bool
    grade_separated: bool
    reason: str


@dataclass(frozen=True)
class Encounter:
    source_key: str
    lat: float
    lon: float
    status: EncounterStatus
    distance_m: float
    position_fraction: float | None
    position_m: float | None
    pass_count: int
    site_group_id: str
    manufacturer: str | None
    is_flock: bool
    lifecycle_state: str
    direction_raw: str | None
    direction_conflict: bool
    heading_relation: str | None
    in_envelope: bool
    source_url: str
    association: Association | None
    reason: str
    source_timestamp: str | None = None  # last edit of the record in the source (ISO 8601), for camera details
    check_date: str | None = None        # contributor-supplied check date tag, raw


@dataclass(frozen=True)
class SensitivityCount:
    radius_m: int
    records_within: int


@dataclass(frozen=True)
class AssessmentResult:
    status: str  # complete | partial | not_assessed
    counting_method_version: str
    radius_m: float
    scope: str
    snapshot_id: str | None
    graph_version: str | None
    matched_record_count: int | None
    uncertain_record_count: int | None
    coverage_fraction: float | None
    encounters: list[Encounter] = field(default_factory=list)
    sensitivity: list[SensitivityCount] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
