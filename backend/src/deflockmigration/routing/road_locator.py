"""Valhalla adapter for road association inputs: nearest drivable roads around a point (`/locate`) and the
edges a route traverses (`/trace_attributes` with edge_walk). Only documented request options are used.
"""

from __future__ import annotations

import logging

import httpx

from deflockmigration.core.errors import ROUTER_UNAVAILABLE, AppError
from deflockmigration.domain.assessment import RoadCandidate, RouteEdge

log = logging.getLogger(__name__)
TRACE_ATTRIBUTES = [
    "edge.way_id", "edge.names", "edge.length", "edge.road_class", "edge.use", "edge.bridge", "edge.tunnel",
    "edge.begin_heading", "edge.end_heading", "edge.begin_shape_index", "edge.end_shape_index",
]


class ValhallaRoadLocator:
    def __init__(self, base_url: str, *, connect_timeout: float = 2.0, read_timeout: float = 10.0, transport: httpx.BaseTransport | None = None):
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(timeout=httpx.Timeout(connect=connect_timeout, read=read_timeout, write=5.0, pool=5.0), transport=transport, headers={"User-Agent": "DeFlockMigration-api"})

    def close(self) -> None:
        self._client.close()

    def _post(self, path: str, body: dict, what: str):
        try:
            resp = self._client.post(f"{self._base}{path}", json=body)
        except httpx.HTTPError as exc:
            raise AppError(ROUTER_UNAVAILABLE, f"The routing engine could not answer the {what} request.", details={"cause": type(exc).__name__}) from exc
        if resp.status_code != 200:
            raise AppError(ROUTER_UNAVAILABLE, f"The routing engine rejected the {what} request.", details={"http_status": resp.status_code})
        return resp.json()

    def locate(self, lat: float, lon: float, radius_m: float) -> list[RoadCandidate]:
        """Drivable roads (auto costing) within `radius_m` of a point: one candidate per OSM way, nearest sub-edge."""
        data = self._post("/locate", {"locations": [{"lat": lat, "lon": lon, "radius": int(round(radius_m))}], "costing": "auto", "verbose": True}, "locate")
        if not isinstance(data, list) or not data:
            return []
        best: dict[int, RoadCandidate] = {}
        for edge in data[0].get("edges") or []:
            info = edge.get("edge_info") or {}
            attrs = edge.get("edge") or {}
            classification = attrs.get("classification") or {}
            way_id = info.get("way_id")
            if way_id is None:
                continue
            candidate = RoadCandidate(
                way_id=int(way_id),
                names=[str(n) for n in (info.get("names") or [])],
                distance_m=float(edge.get("distance", 0.0)),
                road_class=classification.get("classification"),
                use=classification.get("use"),
                bridge=bool(attrs.get("bridge", False)),
                tunnel=bool(attrs.get("tunnel", False)),
                correlated_lat=edge.get("correlated_lat"),
                correlated_lon=edge.get("correlated_lon"),
                side_of_street=edge.get("side_of_street"),
            )
            if way_id not in best or candidate.distance_m < best[way_id].distance_m:
                best[way_id] = candidate
        return sorted((c for c in best.values() if c.distance_m <= radius_m), key=lambda c: (c.distance_m, c.way_id))

    def route_edges(self, shape: list[tuple[float, float]]) -> list[RouteEdge]:
        """Edges traversed by the engine's own route shape (edge_walk map matching)."""
        body = {"shape": [{"lat": lat, "lon": lon} for lat, lon in shape], "costing": "auto", "shape_match": "edge_walk", "filters": {"attributes": TRACE_ATTRIBUTES, "action": "include"}}
        data = self._post("/trace_attributes", body, "trace_attributes")
        edges: list[RouteEdge] = []
        for e in data.get("edges") or []:
            if e.get("way_id") is None:
                continue
            edges.append(RouteEdge(
                way_id=int(e["way_id"]),
                names=[str(n) for n in (e.get("names") or [])],
                begin_shape_index=int(e.get("begin_shape_index", 0)),
                end_shape_index=int(e.get("end_shape_index", 0)),
                road_class=e.get("road_class"),
                use=e.get("use"),
                bridge=bool(e.get("bridge", False)),
                tunnel=bool(e.get("tunnel", False)),
                begin_heading=float(e["begin_heading"]) if e.get("begin_heading") is not None else None,
                end_heading=float(e["end_heading"]) if e.get("end_heading") is not None else None,
                length_m=float(e.get("length", 0.0)) * 1000.0,
            ))
        return edges
