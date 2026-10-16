"""Normalization of OSM elements into camera records (decision 0001 D8).

- ALPR typing comes from the plain `surveillance:type` key (plus documented aliases).
- Flock scope comes from `manufacturer`; brand/operator values are evidence only.
- Lifecycle-prefixed keys are parsed even though the M0 snapshot held none.
- Direction tags are stored raw; conflicts are flagged; nothing here excludes a camera.
"""

from __future__ import annotations

import datetime as dt
import re

from deflockmigration.domain.cameras import LifecycleState, NormalizedCamera

LIFECYCLE_PREFIXES = {
    "removed": LifecycleState.REMOVED,
    "was": LifecycleState.WAS,
    "destroyed": LifecycleState.DESTROYED,
    "disused": LifecycleState.DISUSED,
    "abandoned": LifecycleState.DISUSED,
    "demolished": LifecycleState.DESTROYED,
    "planned": LifecycleState.PLANNED,
    "proposed": LifecycleState.PLANNED,
    "construction": LifecycleState.PLANNED,
}
ALPR_VALUES = ("alpr", "anpr", "license_plate_scanner", "license plate")
CARDINALS = {
    "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5, "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5,
    "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5, "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5,
}
NUMERIC = re.compile(r"^-?\d+(?:\.\d+)?$")


def normalize_manufacturer(raw: str | None) -> str | None:
    if not raw:
        return None
    key = re.sub(r"[^a-z0-9]+", " ", raw.lower()).strip()
    if "flock" in key:
        return "flock_safety"
    if "axon" in key:
        return "axon"
    if "motorola" in key or "vigilant" in key:
        return "motorola_solutions"
    if "genetec" in key:
        return "genetec"
    if "axis" in key:
        return "axis_communications"
    if "leonardo" in key or "elsag" in key:
        return "leonardo"
    if "neology" in key:
        return "neology"
    if "rekor" in key:
        return "rekor"
    return key.replace(" ", "_") or None


def _alpr_typing(tags: dict[str, str]) -> tuple[bool, str, LifecycleState, str | None]:
    """Return (is_alpr, evidence, lifecycle_state, lifecycle_evidence)."""
    lifecycle = LifecycleState.MAPPED
    lifecycle_evidence = None
    for key, value in tags.items():
        prefix, _, rest = key.partition(":")
        if prefix in LIFECYCLE_PREFIXES and rest in ("surveillance:type", "man_made", "surveillance"):
            lifecycle = LIFECYCLE_PREFIXES[prefix]
            lifecycle_evidence = f"{key}={value}"
    plain = tags.get("surveillance:type", "").lower()
    if any(v in plain for v in ALPR_VALUES):
        return True, f"surveillance:type={tags['surveillance:type']}", lifecycle, lifecycle_evidence
    if lifecycle is not LifecycleState.MAPPED and lifecycle_evidence and any(v in lifecycle_evidence.lower() for v in ALPR_VALUES):
        return True, lifecycle_evidence, lifecycle, lifecycle_evidence
    for alias_key in ("camera:type", "surveillance"):
        value = tags.get(alias_key, "").lower()
        if any(v in value for v in ALPR_VALUES):
            return True, f"alias {alias_key}={tags[alias_key]}", lifecycle, lifecycle_evidence
    return False, "no ALPR typing", lifecycle, lifecycle_evidence


def parse_direction(raw: str | None) -> tuple[float | None, str | None]:
    """Return (degrees, warning). Ranges and multi-values give None with a warning."""
    if raw is None:
        return None, None
    value = raw.strip()
    if NUMERIC.match(value):
        deg = float(value) % 360.0
        return deg, None
    if value.upper() in CARDINALS:
        return float(CARDINALS[value.upper()]), None
    if ";" in value:
        return None, f"multi-valued direction '{value}'"
    if "-" in value:
        return None, f"range direction '{value}'"
    return None, f"unparsed direction '{value}'"


def normalize_element(element: dict) -> NormalizedCamera | None:
    """Return a record for a node element, or None for non-node elements without a usable point."""
    etype = element.get("type")
    eid = element.get("id")
    tags: dict[str, str] = {str(k): str(v) for k, v in (element.get("tags") or {}).items()}
    warnings: list[str] = []
    if etype == "node" and "lat" in element and "lon" in element:
        lat, lon, quality = float(element["lat"]), float(element["lon"]), "point"
    elif element.get("center"):
        lat, lon, quality = float(element["center"]["lat"]), float(element["center"]["lon"]), "representative_point"
        warnings.append("non-point geometry; representative point used")
    elif element.get("geometry"):
        pts = [(g["lat"], g["lon"]) for g in element["geometry"] if "lat" in g]
        if not pts:
            return None
        lat = sum(p[0] for p in pts) / len(pts)
        lon = sum(p[1] for p in pts) / len(pts)
        quality = "representative_point"
        warnings.append("non-point geometry; vertex mean used")
    else:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    is_alpr, evidence, lifecycle, lifecycle_evidence = _alpr_typing(tags)
    manufacturer_raw = tags.get("manufacturer")
    manufacturer_norm = normalize_manufacturer(manufacturer_raw)
    is_flock = manufacturer_norm == "flock_safety"
    if not manufacturer_raw and any("flock" in tags.get(k, "").lower() for k in ("brand", "operator", "name")):
        warnings.append("Flock branding without a manufacturer tag; not counted as Flock scope")
    if not is_alpr and any("flock" in tags.get(k, "").lower() for k in ("manufacturer", "brand", "operator")):
        warnings.append("Flock-branded device without ALPR typing; excluded from encounter counts")
    direction_raw = tags.get("direction")
    camera_direction_raw = tags.get("camera:direction")
    deg, warn = parse_direction(direction_raw)
    if warn:
        warnings.append(warn)
    if deg is None and camera_direction_raw:
        deg, warn2 = parse_direction(camera_direction_raw)
        if warn2:
            warnings.append(warn2)
    conflict = bool(direction_raw and camera_direction_raw and direction_raw.strip() != camera_direction_raw.strip())
    if conflict:
        warnings.append("direction and camera:direction disagree")
    timestamp = element.get("timestamp")
    parsed_ts = None
    if timestamp:
        try:
            parsed_ts = dt.datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        except ValueError:
            warnings.append("unparseable source timestamp")
    return NormalizedCamera(
        source_key=f"osm:{etype}:{eid}",
        source_type=str(etype),
        source_id=int(eid),
        source_version=int(element["version"]) if element.get("version") is not None else None,
        source_timestamp=parsed_ts,
        lat=lat,
        lon=lon,
        geometry_quality=quality,
        raw_tags=tags,
        is_alpr=is_alpr,
        alpr_evidence=evidence,
        manufacturer_raw=manufacturer_raw,
        manufacturer_normalized=manufacturer_norm,
        is_flock=is_flock,
        operator=tags.get("operator"),
        direction_raw=direction_raw,
        camera_direction_raw=camera_direction_raw,
        direction_parsed_deg=deg,
        direction_conflict=conflict,
        lifecycle_state=lifecycle,
        lifecycle_evidence=lifecycle_evidence,
        check_date=tags.get("check_date") or tags.get("survey:date"),
        parse_warnings=warnings,
    )


def normalize_elements(elements: list[dict]) -> list[NormalizedCamera]:
    records: list[NormalizedCamera] = []
    seen: set[str] = set()
    for element in elements:
        record = normalize_element(element)
        if record is None or record.source_key in seen:
            continue
        seen.add(record.source_key)
        records.append(record)
    return records
