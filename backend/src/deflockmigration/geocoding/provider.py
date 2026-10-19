"""Geocoder interface and the coordinate-pair shortcut that needs no provider at all."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from deflockmigration.core.errors import GEOCODER_NOT_CONFIGURED, AppError

COORDINATE_PAIR = re.compile(r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


@dataclass(frozen=True)
class GeocodeCandidate:
    label: str
    lat: float
    lon: float
    source: str  # coordinates | nominatim_local | map_pin
    category: str | None = None
    importance: float | None = None
    note: str | None = None


@dataclass(frozen=True)
class ReverseResult:
    label: str
    matched_lat: float
    matched_lon: float
    category: str | None
    source: str


@dataclass(frozen=True)
class GeocoderStatus:
    configured: bool
    available: bool
    provider: str
    data_updated: str | None = None
    message: str | None = None


class Geocoder(Protocol):
    name: str

    def search(self, query: str, *, limit: int, viewbox_wsen: tuple[float, float, float, float] | None) -> list[GeocodeCandidate]: ...

    def reverse(self, lat: float, lon: float) -> ReverseResult | None: ...

    def status(self) -> GeocoderStatus: ...


def parse_coordinate_pair(query: str) -> GeocodeCandidate | None:
    """Accept "lat, lon". A pair typed as "lon, lat" (first value beyond +/-90 while the second fits latitude)
    is interpreted the other way round and says so, instead of failing silently."""
    match = COORDINATE_PAIR.match(query)
    if not match:
        return None
    first, second = float(match.group(1)), float(match.group(2))
    if -90 <= first <= 90 and -180 <= second <= 180:
        return GeocodeCandidate(label=f"Coordinates {first:.5f}, {second:.5f}", lat=first, lon=second, source="coordinates", category="coordinates")
    if 90 < abs(first) <= 180 and -90 <= second <= 90:
        return GeocodeCandidate(
            label=f"Coordinates {second:.5f}, {first:.5f} (read as longitude, latitude)",
            lat=second,
            lon=first,
            source="coordinates",
            category="coordinates",
            note="The values looked like longitude, latitude and were swapped. Confirm the point on the map.",
        )
    return None


def dedupe_candidates(candidates: list[GeocodeCandidate]) -> list[GeocodeCandidate]:
    seen: set[tuple[float, float]] = set()
    unique: list[GeocodeCandidate] = []
    for candidate in candidates:
        key = (round(candidate.lat, 5), round(candidate.lon, 5))
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


class NullGeocoder:
    name = "none"

    def search(self, query: str, *, limit: int, viewbox_wsen=None) -> list[GeocodeCandidate]:
        raise AppError(GEOCODER_NOT_CONFIGURED, "Address search is not configured. Type coordinates or place a map pin.")

    def reverse(self, lat: float, lon: float) -> ReverseResult | None:
        raise AppError(GEOCODER_NOT_CONFIGURED, "Address lookup is not configured.")

    def status(self) -> GeocoderStatus:
        return GeocoderStatus(configured=False, available=False, provider="none", message="no geocoder configured")
