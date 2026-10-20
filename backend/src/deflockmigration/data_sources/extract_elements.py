"""Camera records from a regional OpenStreetMap extract (M10).

Applies the same tag filters as the fixed Overpass query to every node, way, and relation of the extract and
returns elements shaped like the Overpass `out meta geom` output (type, id, coordinates or point geometry,
version, timestamp, tags) without contributor names or ids. The normalizer and the rest of the sync pipeline
stay unchanged, so both sources produce records the same way.

The extract is read with pyosmium: one pass with a key filter evaluated in C++ (only objects carrying one of
the filter keys reach Python), and a second pass only when ways or relations matched, to pick up the node
locations they need. On the Colorado extract (385 MB) this takes about five seconds and under 200 MB.
"""

from __future__ import annotations

import datetime as dt
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

FILTER_VERSION = "alpr-tag-filter-1.0"
LIFECYCLE_PREFIXES = ("disused", "removed", "was", "abandoned", "planned", "proposed", "construction", "demolished")
ALPR_VALUE_KEYS = ("surveillance:type", "camera:type", *[f"{prefix}:surveillance:type" for prefix in LIFECYCLE_PREFIXES])
FLOCK_VALUE_KEYS = ("manufacturer", "operator", "brand")
FILTER_KEYS = (*ALPR_VALUE_KEYS, *FLOCK_VALUE_KEYS)
FILTER_SPEC = (
    "union of nwr[surveillance:type~alpr,i], nwr[<prefix>:surveillance:type~alpr,i] for the lifecycle prefixes "
    "disused|removed|was|abandoned|planned|proposed|construction|demolished, nwr[manufacturer~flock,i], "
    "nwr[operator~flock,i], nwr[brand~flock,i], nwr[camera:type~alpr,i]; ways and relations carry their node "
    "points as geometry; contributor names and ids omitted"
)
_ALPR = re.compile("alpr", re.IGNORECASE)
_FLOCK = re.compile("flock", re.IGNORECASE)


def matches_camera_filter(tags: Mapping[str, str]) -> bool:
    """The Overpass query's filters applied to one element's tags (regex search, case-insensitive)."""
    for key in ALPR_VALUE_KEYS:
        value = tags.get(key)
        if value and _ALPR.search(value):
            return True
    for key in FLOCK_VALUE_KEYS:
        value = tags.get(key)
        if value and _FLOCK.search(value):
            return True
    return False


@dataclass(frozen=True)
class ExtractionStats:
    key_filtered_objects: int
    node_count: int
    way_count: int
    relation_count: int
    unlocated_count: int
    elapsed_seconds: float

    def as_dict(self) -> dict:
        return {
            "key_filtered_objects": self.key_filtered_objects,
            "nodes": self.node_count,
            "ways": self.way_count,
            "relations": self.relation_count,
            "unlocated": self.unlocated_count,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
        }


@dataclass(frozen=True)
class Extraction:
    elements: list[dict]
    stats: ExtractionStats
    data_timestamp: dt.datetime | None
    replication_sequence: int | None
    replication_url: str | None


def _timestamp(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _points(refs: list[int], locations: dict[int, tuple[float, float]]) -> list[dict]:
    return [{"lat": locations[ref][0], "lon": locations[ref][1]} for ref in refs if ref in locations]


def extract_camera_elements(path: Path) -> Extraction:
    """Read the extract once (twice when ways or relations matched) and return Overpass-shaped elements."""
    import osmium  # the C++ extension is needed only where extracts are processed (the sync worker)
    from osmium.replication.utils import get_replication_header

    started = time.monotonic()
    header = get_replication_header(str(path))
    key_filtered = 0
    nodes: list[dict] = []
    ways: dict[int, tuple[list[int], dict]] = {}
    relations: dict[int, tuple[list[tuple[str, int]], dict]] = {}
    unlocated = 0
    tracker = osmium.IdTracker()
    for obj in osmium.FileProcessor(str(path)).with_filter(osmium.filter.KeyFilter(*FILTER_KEYS)):
        key_filtered += 1
        tags = {tag.k: tag.v for tag in obj.tags}
        if not matches_camera_filter(tags):
            continue
        base = {"id": obj.id, "version": obj.version, "timestamp": _timestamp(obj.timestamp), "tags": tags}
        if obj.is_node():
            location = obj.location
            if not location.valid():
                unlocated += 1
                continue
            nodes.append({"type": "node", **base, "lat": round(location.lat, 7), "lon": round(location.lon, 7)})
        elif obj.is_way():
            ways[obj.id] = ([node.ref for node in obj.nodes], base)
            tracker.add_references(obj)
        elif obj.is_relation():
            relations[obj.id] = ([(member.type, member.ref) for member in obj.members], base)
            tracker.add_references(obj)

    locations: dict[int, tuple[float, float]] = {}
    member_ways: dict[int, list[int]] = {}
    if relations:
        tracker.complete_backward_references(str(path))
    if ways or relations:
        for obj in osmium.FileProcessor(str(path), osmium.osm.NODE | osmium.osm.WAY).with_filter(tracker.id_filter()):
            if obj.is_node():
                location = obj.location
                if location.valid():
                    locations[obj.id] = (round(location.lat, 7), round(location.lon, 7))
            elif obj.is_way():
                member_ways[obj.id] = [node.ref for node in obj.nodes]

    elements: list[dict] = sorted(nodes, key=lambda e: e["id"])
    for way_id in sorted(ways):
        refs, base = ways[way_id]
        points = _points(refs, locations)
        if not points:
            unlocated += 1
            continue
        elements.append({"type": "way", **base, "nodes": refs, "geometry": points})
    for relation_id in sorted(relations):
        members, base = relations[relation_id]
        points: list[dict] = []
        for member_type, ref in members:
            if member_type == "n" and ref in locations:
                points.append({"lat": locations[ref][0], "lon": locations[ref][1]})
            elif member_type == "w":
                points.extend(_points(member_ways.get(ref, []), locations))
        if not points:
            unlocated += 1
            continue
        elements.append({
            "type": "relation", **base,
            "members": [{"type": {"n": "node", "w": "way", "r": "relation"}[member_type], "ref": ref} for member_type, ref in members],
            "geometry": points,
        })
    stats = ExtractionStats(key_filtered, len(nodes), len([e for e in elements if e["type"] == "way"]),
                            len([e for e in elements if e["type"] == "relation"]), unlocated, time.monotonic() - started)
    return Extraction(elements, stats, header.timestamp, header.sequence, header.url)
