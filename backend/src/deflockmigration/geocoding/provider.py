"""Geocoder interface and the coordinate-pair shortcut that needs no provider at all."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from deflockmigration.core.errors import GEOCODER_NOT_CONFIGURED, AppError

COORDINATE_PAIR = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


@dataclass(frozen=True)
class GeocodeCandidate:
    label: str
    lat: float
    lon: float
    source: str  # coordinates | nominatim_local
    category: str | None = None
    importance: float | None = None


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

    def status(self) -> GeocoderStatus: ...


def parse_coordinate_pair(query: str) -> GeocodeCandidate | None:
    match = COORDINATE_PAIR.match(query)
    if not match:
        return None
    lat, lon = float(match.group(1)), float(match.group(2))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return GeocodeCandidate(label=f"Coordinates {lat:.5f}, {lon:.5f}", lat=lat, lon=lon, source="coordinates", category="coordinates")


class NullGeocoder:
    name = "none"

    def search(self, query: str, *, limit: int, viewbox_wsen=None) -> list[GeocodeCandidate]:
        raise AppError(GEOCODER_NOT_CONFIGURED, "Address search is not configured. Type coordinates or place a map pin.")

    def status(self) -> GeocoderStatus:
        return GeocoderStatus(configured=False, available=False, provider="none", message="no geocoder configured")
