"""Self-hosted Nominatim adapter (approved provider, decision 0001 D10).

Never points at the public OSMF service. Submit-only search, no autocomplete, bounded result count,
and reverse lookup for labelling map pins. Queries stay on the Compose network.
"""

from __future__ import annotations

import logging

import httpx

from deflockmigration.core.errors import GEOCODER_UNAVAILABLE, AppError
from deflockmigration.geocoding.provider import GeocodeCandidate, GeocoderStatus, ReverseResult, dedupe_candidates

log = logging.getLogger(__name__)
PUBLIC_HOSTS = ("nominatim.openstreetmap.org",)


class NominatimLocalGeocoder:
    name = "nominatim_local"

    def __init__(self, base_url: str, *, user_agent: str, timeout: float = 5.0, countrycodes: str = "us", transport: httpx.BaseTransport | None = None):
        if any(host in base_url for host in PUBLIC_HOSTS):
            raise ValueError("the public Nominatim service is not an approved provider; configure a self-hosted instance")
        self._base = base_url.rstrip("/")
        self._countrycodes = countrycodes
        self._client = httpx.Client(timeout=timeout, transport=transport, headers={"User-Agent": user_agent})

    def close(self) -> None:
        self._client.close()

    def status(self) -> GeocoderStatus:
        try:
            resp = self._client.get(f"{self._base}/status", params={"format": "json"})
        except httpx.HTTPError as exc:
            return GeocoderStatus(configured=True, available=False, provider=self.name, message=f"geocoder unreachable: {type(exc).__name__}")
        if resp.status_code != 200:
            return GeocoderStatus(configured=True, available=False, provider=self.name, message=f"geocoder status HTTP {resp.status_code}")
        data = resp.json()
        return GeocoderStatus(configured=True, available=data.get("status") == 0, provider=self.name, data_updated=data.get("data_updated"), message=data.get("message"))

    def _get(self, path: str, params: dict):
        try:
            resp = self._client.get(f"{self._base}{path}", params=params)
        except httpx.HTTPError as exc:
            raise AppError(GEOCODER_UNAVAILABLE, "Address lookup is temporarily unavailable.", details={"cause": type(exc).__name__}) from exc
        if resp.status_code != 200:
            raise AppError(GEOCODER_UNAVAILABLE, "Address lookup returned an error.", details={"http_status": resp.status_code})
        try:
            return resp.json()
        except ValueError as exc:
            raise AppError(GEOCODER_UNAVAILABLE, "Address lookup returned an unexpected payload.") from exc

    def search(self, query: str, *, limit: int, viewbox_wsen=None) -> list[GeocodeCandidate]:
        params = {"q": query, "format": "jsonv2", "limit": max(1, min(limit, 10)), "countrycodes": self._countrycodes, "addressdetails": 0, "dedupe": 1}
        if viewbox_wsen:
            west, south, east, north = viewbox_wsen
            params["viewbox"] = f"{west},{south},{east},{north}"
            params["bounded"] = 0
        results = self._get("/search", params)
        if not isinstance(results, list):
            raise AppError(GEOCODER_UNAVAILABLE, "Address lookup returned an unexpected payload.")
        candidates: list[GeocodeCandidate] = []
        for item in results:
            try:
                candidates.append(GeocodeCandidate(
                    label=str(item.get("display_name") or item.get("name") or "Unnamed place"),
                    lat=float(item["lat"]),
                    lon=float(item["lon"]),
                    source=self.name,
                    category=item.get("addresstype") or item.get("type"),
                    importance=float(item["importance"]) if item.get("importance") is not None else None,
                ))
            except (KeyError, TypeError, ValueError):
                log.warning("skipping malformed geocoder result")
        return dedupe_candidates(candidates)

    def reverse(self, lat: float, lon: float) -> ReverseResult | None:
        data = self._get("/reverse", {"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 18, "addressdetails": 0})
        if not isinstance(data, dict) or data.get("error"):
            return None
        try:
            return ReverseResult(
                label=str(data.get("display_name") or data.get("name") or "Unnamed place"),
                matched_lat=float(data["lat"]),
                matched_lon=float(data["lon"]),
                category=data.get("addresstype") or data.get("type"),
                source=self.name,
            )
        except (KeyError, TypeError, ValueError):
            return None
