"""Deterministic synthetic road network for the M5 tests (roadmap section 16: synthetic routing fixtures are
mandatory). Test code only; production never imports it.

Nodes live on a metric plane around a downtown Denver origin (so the real service boundary accepts them);
edges carry physical travel times. The engine answers the way the real one does:

- path finding minimises time x penalty factor over edges that are not excluded;
- hard exclusions remove the road nearest to each exclusion point in both directions;
- the reported duration is always the physical time, never the penalized cost (decision 0001 D5);
- alternates are k-shortest simple paths when enabled, or none (like an engine that finds no alternate).

It also answers the locate and route_edges questions the M4 assessment asks, so a whole plan runs end to end
without a network.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, replace

from shapely.geometry.base import BaseGeometry

from deflockmigration.application.assess_route import assess_route
from deflockmigration.core.errors import NO_DRIVABLE_ROUTE, AppError
from deflockmigration.domain.assessment import CameraNearRoute, RoadCandidate, RouteEdge
from deflockmigration.domain.routes import AvoidanceRequest, EngineRoute, LatLon, Maneuver, RouterStatus
from deflockmigration.geospatial.metric import point_segment_m
from deflockmigration.geospatial.proximity import MemoryProximityIndex

LAT0, LON0 = 39.7400, -104.9900
M_PER_DEG_LAT = 111320.0
M_PER_DEG_LON = 111320.0 * math.cos(math.radians(LAT0))
SHAPE_STEP_M = 25.0


def to_latlon(x_m: float, y_m: float) -> tuple[float, float]:
    return (LAT0 + y_m / M_PER_DEG_LAT, LON0 + x_m / M_PER_DEG_LON)


def camera(key: str, x_m: float, y_m: float, **overrides) -> CameraNearRoute:
    lat, lon = to_latlon(x_m, y_m)
    base = dict(source_key=key, lat=lat, lon=lon, is_alpr=True, is_flock=True, manufacturer="flock_safety", lifecycle_state="mapped", direction_raw=None,
                direction_parsed_deg=None, direction_conflict=False, in_envelope=True, operator=None, source_timestamp=None, check_date=None, distance_m=0.0)
    base.update(overrides)
    return CameraNearRoute(**base)


@dataclass(frozen=True)
class Street:
    way_id: int
    names: tuple[str, ...]


@dataclass(frozen=True)
class DirectedEdge:
    index: int
    a: str
    b: str
    time_s: float
    street: Street


class SyntheticGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, tuple[float, float]] = {}
        self.edges: list[DirectedEdge] = []

    def node(self, name: str, x_m: float, y_m: float) -> None:
        self.nodes[name] = (x_m, y_m)

    @staticmethod
    def street(way_id: int, *names: str) -> Street:
        return Street(way_id, tuple(names))

    def connect(self, a: str, b: str, time_s: float, street: Street, *, oneway: bool = False) -> None:
        self.edges.append(DirectedEdge(len(self.edges), a, b, time_s, street))
        if not oneway:
            self.edges.append(DirectedEdge(len(self.edges), b, a, time_s, street))

    def length_m(self, a: str, b: str) -> float:
        (x1, y1), (x2, y2) = self.nodes[a], self.nodes[b]
        return math.hypot(x2 - x1, y2 - y1)

    def latlon(self, name: str) -> tuple[float, float]:
        return to_latlon(*self.nodes[name])

    def reverse_of(self, edge: DirectedEdge) -> DirectedEdge | None:
        return next((e for e in self.edges if e.a == edge.b and e.b == edge.a and e.street == edge.street), None)


class SyntheticEngine:
    """Implements the RoutingProvider protocol plus the locate/route_edges services used by the assessment."""

    def __init__(self, graph: SyntheticGraph, *, alternates_mode: str = "none", fail_exclusions: bool = False, match_tolerance_m: float = 15.0):
        self.graph = graph
        self.alternates_mode = alternates_mode
        self.fail_exclusions = fail_exclusions
        self.tolerance = match_tolerance_m
        self.calls: list[dict] = []
        self._paths_by_key: dict[str, tuple[list[DirectedEdge], list[int]]] = {}

    # ----- RoutingProvider ----------------------------------------------------------------------------------

    def status(self) -> RouterStatus:
        return RouterStatus(available=True, version="synthetic", tileset_last_modified="2026-01-01T00:00:00Z", has_tiles=True, has_admins=True, has_timezones=True)

    def baseline_candidates(self, origin: LatLon, destination: LatLon, *, alternates: int, request_id: str) -> list[EngineRoute]:
        return self._solve(origin, destination, alternates, {}, set(), "primary", "alternate", kind="baseline")

    def avoiding_candidates(self, origin: LatLon, destination: LatLon, *, alternates: int, request_id: str, avoidance: AvoidanceRequest) -> list[EngineRoute]:
        factors = self._match_penalties(avoidance.penalties)
        excluded = self._match_exclusions(avoidance.exclusions)
        if excluded and self.fail_exclusions:
            self.calls.append({"kind": avoidance.kind, "factors": factors, "excluded": sorted(excluded), "routes": [], "error": "no_path"})
            raise AppError(NO_DRIVABLE_ROUTE, "No drivable route was found between these points.", details={"engine_error_code": 171})
        return self._solve(origin, destination, alternates, factors, excluded, avoidance.kind, avoidance.kind, kind=avoidance.kind)

    # ----- assessment services ------------------------------------------------------------------------------

    def route_edges(self, shape: list[tuple[float, float]]) -> list[RouteEdge]:
        key = ";".join(f"{lat:.5f},{lon:.5f}" for lat, lon in shape)
        path, node_indices = self._paths_by_key[key]
        edges: list[RouteEdge] = []
        for i, edge in enumerate(path):
            (x1, y1), (x2, y2) = self.graph.nodes[edge.a], self.graph.nodes[edge.b]
            heading = (math.degrees(math.atan2(x2 - x1, y2 - y1)) + 360.0) % 360.0
            edges.append(RouteEdge(edge.street.way_id, list(edge.street.names), node_indices[i], node_indices[i + 1], "residential", "road", False, False, heading, heading, self.graph.length_m(edge.a, edge.b)))
        return edges

    def locate(self, lat: float, lon: float, radius_m: float) -> list[RoadCandidate]:
        best: dict[int, RoadCandidate] = {}
        for edge in self.graph.edges:
            distance = point_segment_m((lat, lon), self.graph.latlon(edge.a), self.graph.latlon(edge.b))[0]
            if distance > radius_m:
                continue
            way = edge.street.way_id
            if way not in best or distance < best[way].distance_m:
                best[way] = RoadCandidate(way, list(edge.street.names), round(distance, 1), "residential", "road", False, False)
        return sorted(best.values(), key=lambda c: (c.distance_m, c.way_id))

    # ----- internals ----------------------------------------------------------------------------------------

    def _nearest_node(self, point: LatLon) -> str:
        return min(self.graph.nodes, key=lambda n: (point.lat - self.graph.latlon(n)[0]) ** 2 + (point.lon - self.graph.latlon(n)[1]) ** 2)

    def _nearest_edge(self, lat: float, lon: float) -> tuple[DirectedEdge | None, float]:
        best, best_d = None, float("inf")
        for edge in self.graph.edges:
            d = point_segment_m((lat, lon), self.graph.latlon(edge.a), self.graph.latlon(edge.b))[0]
            if d < best_d:
                best, best_d = edge, d
        return best, best_d

    def _match_penalties(self, penalties) -> dict[int, float]:
        factors: dict[int, float] = {}
        for segment in penalties:
            for lat, lon in segment.points:
                edge, d = self._nearest_edge(lat, lon)
                if edge is None or d > self.tolerance:
                    continue
                for e in (edge, self.graph.reverse_of(edge)):
                    if e is not None:
                        factors[e.index] = max(factors.get(e.index, 1.0), float(segment.factor))
        return factors

    def _match_exclusions(self, exclusions) -> set[int]:
        excluded: set[int] = set()
        for point in exclusions:
            edge, d = self._nearest_edge(point.lat, point.lon)
            if edge is None or d > self.tolerance:
                continue
            excluded.add(edge.index)
            rev = self.graph.reverse_of(edge)
            if rev is not None:
                excluded.add(rev.index)
        return excluded

    def _dijkstra(self, src: str, dst: str, factors: dict[int, float], excluded: set[int], banned_nodes: set[str], banned_edges: set[int]) -> tuple[list[DirectedEdge], float] | None:
        dist: dict[str, float] = {src: 0.0}
        prev: dict[str, DirectedEdge] = {}
        heap: list[tuple[float, str]] = [(0.0, src)]
        done: set[str] = set()
        while heap:
            d, node = heapq.heappop(heap)
            if node in done:
                continue
            done.add(node)
            if node == dst:
                break
            for edge in self.graph.edges:
                if edge.a != node or edge.index in excluded or edge.index in banned_edges or edge.b in banned_nodes:
                    continue
                nd = d + edge.time_s * factors.get(edge.index, 1.0)
                if nd < dist.get(edge.b, float("inf")):
                    dist[edge.b] = nd
                    prev[edge.b] = edge
                    heapq.heappush(heap, (nd, edge.b))
        if dst not in dist:
            return None
        path: list[DirectedEdge] = []
        node = dst
        while node != src:
            edge = prev[node]
            path.append(edge)
            node = edge.a
        path.reverse()
        return path, dist[dst]

    def _k_shortest(self, src: str, dst: str, k: int, factors: dict[int, float], excluded: set[int]) -> list[tuple[list[DirectedEdge], float]]:
        """Yen's algorithm on the penalized cost; deterministic for a fixed graph."""
        first = self._dijkstra(src, dst, factors, excluded, set(), set())
        if first is None:
            return []
        accepted = [first]
        candidates: list[tuple[float, int, list[DirectedEdge]]] = []
        counter = 0
        while len(accepted) < k:
            last_path, _ = accepted[-1]
            for i in range(len(last_path)):
                spur_node = last_path[i].a
                root = last_path[:i]
                banned_edges = {p[0][i].index for p in accepted if p[0][:i] == root and len(p[0]) > i}
                banned_nodes = {e.a for e in root}
                spur = self._dijkstra(spur_node, dst, factors, excluded, banned_nodes, banned_edges)
                if spur is None:
                    continue
                total = root + spur[0]
                cost = sum(e.time_s * factors.get(e.index, 1.0) for e in total)
                if any(p[0] == total for p in accepted) or any(c[2] == total for c in candidates):
                    continue
                counter += 1
                heapq.heappush(candidates, (cost, counter, total))
            if not candidates:
                break
            cost, _, path = heapq.heappop(candidates)
            accepted.append((path, cost))
        return accepted

    def _solve(self, origin: LatLon, destination: LatLon, alternates: int, factors: dict[int, float], excluded: set[int], source: str, alt_source: str, *, kind: str) -> list[EngineRoute]:
        src, dst = self._nearest_node(origin), self._nearest_node(destination)
        k = 1 + (max(0, alternates) if self.alternates_mode == "yen" else 0)
        paths = self._k_shortest(src, dst, k, factors, excluded)
        if not paths:
            self.calls.append({"kind": kind, "factors": factors, "excluded": sorted(excluded), "routes": [], "error": "no_path"})
            raise AppError(NO_DRIVABLE_ROUTE, "No drivable route was found between these points.", details={"engine_error_code": 171})
        routes = [self._route(path, source if i == 0 else alt_source, i) for i, (path, _) in enumerate(paths)]
        self.calls.append({
            "kind": kind, "factors": factors, "excluded": sorted(excluded),
            "routes": [{"physical_s": r.duration_s, "penalized_cost": cost, "nodes": [path[0].a, *[e.b for e in path]]} for r, (path, cost) in zip(routes, paths)],
        })
        return routes

    def _route(self, path: list[DirectedEdge], source: str, index: int) -> EngineRoute:
        shape: list[tuple[float, float]] = [self.graph.latlon(path[0].a)]
        node_indices = [0]
        maneuvers: list[Maneuver] = []
        for i, edge in enumerate(path):
            (x1, y1), (x2, y2) = self.graph.nodes[edge.a], self.graph.nodes[edge.b]
            length = self.graph.length_m(edge.a, edge.b)
            steps = max(1, int(length // SHAPE_STEP_M))
            begin = len(shape) - 1
            for s in range(1, steps + 1):
                t = s / steps
                shape.append(to_latlon(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
            end = len(shape) - 1
            node_indices.append(end)
            name = " / ".join(edge.street.names)
            maneuvers.append(Maneuver(f"{'Drive' if i == 0 else 'Continue'} along {name}", 1 if i == 0 else 8, length, edge.time_s, begin, end, list(edge.street.names)))
        last = len(shape) - 1
        maneuvers.append(Maneuver("You have arrived at your destination.", 4, 0.0, 0.0, last, last))
        route = EngineRoute(
            engine_route_id=f"{source}-{index}",
            shape=shape,
            duration_s=sum(e.time_s for e in path),  # physical time only, never the penalized cost
            length_m=sum(self.graph.length_m(e.a, e.b) for e in path),
            maneuvers=maneuvers,
            has_highway=False,
            has_toll=False,
            source=source,
        )
        self._paths_by_key[route.encoded_shape_key()] = (path, node_indices)
        return replace(route)


def make_assessor(engine: SyntheticEngine, records: list[CameraNearRoute], envelope: BaseGeometry | None = None, *, graph_version: str = "synthetic@1"):
    proximity = MemoryProximityIndex(records, envelope)

    def assess(route: EngineRoute, scope, snapshot_id):
        return assess_route(route, scope=scope, snapshot_id=snapshot_id, graph_version=graph_version, proximity=proximity, route_edges=engine.route_edges(route.shape), locate=engine.locate)

    return assess
