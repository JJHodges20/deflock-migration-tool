"""Valhalla adapter (pinned build 3.9.1). Only documented request options are used:
locations, costing=auto, units, alternates, id. Legality options stay at engine defaults.
"""

from __future__ import annotations

import datetime as dt
import logging

import httpx

from deflockmigration.core.errors import NO_DRIVABLE_ROUTE, ROUTER_UNAVAILABLE, AppError
from deflockmigration.domain.routes import EngineRoute, LatLon, Maneuver, RouterStatus
from deflockmigration.geospatial.polyline import decode_polyline6

log = logging.getLogger(__name__)

# Valhalla error codes that mean "the graph has no legal path for these inputs" rather than an outage.
NO_PATH_CODES = {170, 171, 442, 443, 444}


class ValhallaProvider:
    def __init__(self, base_url: str, *, connect_timeout: float = 2.0, read_timeout: float = 10.0, transport: httpx.BaseTransport | None = None):
        self._base = base_url.rstrip("/")
        self._timeout = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=5.0, pool=5.0)
        self._client = httpx.Client(timeout=self._timeout, transport=transport, headers={"User-Agent": "DeFlockMigration-api"})

    def close(self) -> None:
        self._client.close()

    def status(self) -> RouterStatus:
        try:
            resp = self._client.post(f"{self._base}/status", json={"verbose": True})
        except httpx.HTTPError as exc:
            return RouterStatus(available=False, message=f"router unreachable: {type(exc).__name__}")
        if resp.status_code != 200:
            return RouterStatus(available=False, message=f"router status HTTP {resp.status_code}")
        data = resp.json()
        modified = data.get("tileset_last_modified")
        modified_iso = dt.datetime.fromtimestamp(modified, dt.UTC).isoformat().replace("+00:00", "Z") if modified else None
        has_tiles = data.get("has_tiles")
        return RouterStatus(
            available=bool(has_tiles) if has_tiles is not None else True,
            version=data.get("version"),
            tileset_last_modified=modified_iso,
            has_tiles=has_tiles,
            has_admins=data.get("has_admins"),
            has_timezones=data.get("has_timezones"),
        )

    def baseline_candidates(self, origin: LatLon, destination: LatLon, *, alternates: int, request_id: str) -> list[EngineRoute]:
        body = {
            "locations": [{"lat": origin.lat, "lon": origin.lon}, {"lat": destination.lat, "lon": destination.lon}],
            "costing": "auto",
            "units": "kilometers",
            "alternates": max(0, alternates),
            "id": request_id,
        }
        try:
            resp = self._client.post(f"{self._base}/route", json=body)
        except httpx.TimeoutException as exc:
            raise AppError(ROUTER_UNAVAILABLE, "The routing engine did not answer in time.", details={"cause": type(exc).__name__}) from exc
        except httpx.HTTPError as exc:
            raise AppError(ROUTER_UNAVAILABLE, "The routing engine is not reachable.", details={"cause": type(exc).__name__}) from exc

        if resp.status_code == 200:
            payload = resp.json()
            routes = [self._parse_trip(payload.get("trip") or {}, payload.get("warnings") or [], "primary", 0)]
            for index, alt in enumerate(payload.get("alternates") or [], start=1):
                routes.append(self._parse_trip(alt.get("trip") or {}, alt.get("warnings") or [], "alternate", index))
            return routes

        try:
            error = resp.json()
        except ValueError:
            error = {}
        code = error.get("error_code")
        if resp.status_code == 400 and code in NO_PATH_CODES:
            raise AppError(NO_DRIVABLE_ROUTE, "No drivable route was found between these points.", details={"engine_error_code": code})
        log.warning("router returned HTTP %s engine_error_code=%s", resp.status_code, code)
        raise AppError(ROUTER_UNAVAILABLE, "The routing engine rejected the request.", details={"engine_error_code": code, "http_status": resp.status_code})

    @staticmethod
    def _parse_trip(trip: dict, warnings: list, source: str, index: int) -> EngineRoute:
        legs = trip.get("legs") or []
        if not legs:
            raise AppError(ROUTER_UNAVAILABLE, "The routing engine returned no legs.")
        leg = legs[0]
        shape = decode_polyline6(leg.get("shape", ""))
        summary = trip.get("summary") or {}
        units = trip.get("units", "kilometers")
        length_factor = 1000.0 if units == "kilometers" else 1609.344
        maneuvers = [
            Maneuver(
                instruction=m.get("instruction") or "",
                type=int(m.get("type", 0)),
                length_m=float(m.get("length", 0.0)) * length_factor,
                time_s=float(m.get("time", 0.0)),
                begin_shape_index=int(m.get("begin_shape_index", 0)),
                end_shape_index=int(m.get("end_shape_index", 0)),
                street_names=list(m.get("street_names") or []),
                begin_street_names=list(m.get("begin_street_names") or []),
                verbal_pre_transition_instruction=m.get("verbal_pre_transition_instruction"),
                roundabout_exit_count=m.get("roundabout_exit_count"),
                toll=bool(m.get("toll", False)),
                highway=bool(m.get("highway", False)),
            )
            for m in (leg.get("maneuvers") or [])
        ]
        warning_texts = [str(w.get("text") if isinstance(w, dict) else w) for w in warnings]
        return EngineRoute(
            engine_route_id=f"{source}-{index}",
            shape=shape,
            duration_s=float(summary.get("time", 0.0)),
            length_m=float(summary.get("length", 0.0)) * length_factor,
            maneuvers=maneuvers,
            has_highway=bool(summary.get("has_highway", False)),
            has_toll=bool(summary.get("has_toll", False)),
            warnings=warning_texts,
            source=source,
        )
