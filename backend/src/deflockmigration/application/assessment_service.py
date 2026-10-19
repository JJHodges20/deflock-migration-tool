"""Wires Stage A (PostGIS proximity), the road-association cache, and the engine's locate/trace services
into the pure `assess_route` function. Degrades to `not_assessed` (never zero) when a dependency is missing.
"""

from __future__ import annotations

import logging

from deflockmigration.application.assess_route import assess_route
from deflockmigration.core.clock import Clock, utc_now
from deflockmigration.core.config_loader import AppConfig
from deflockmigration.core.errors import AppError
from deflockmigration.domain.assessment import COUNTING_METHOD_VERSION, AssessmentResult, RoadCandidate
from deflockmigration.domain.routes import CameraScope, EngineRoute
from deflockmigration.routing.provider import RoutingProvider
from deflockmigration.routing.road_locator import ValhallaRoadLocator
from deflockmigration.storage.association_cache import AssociationCache
from deflockmigration.storage.db import SessionFactory
from deflockmigration.storage.proximity_postgis import PostgisProximityIndex

log = logging.getLogger(__name__)


class AssessmentService:
    def __init__(self, config: AppConfig, session_factory: SessionFactory | None, routing: RoutingProvider, locator: ValhallaRoadLocator, *, clock: Clock = utc_now):
        self._config = config
        self._sf = session_factory
        self._routing = routing
        self._locator = locator
        self._clock = clock
        self._radius = int(config.data_quality.proximity.candidate_radius_m)
        self._radii = list(config.data_quality.proximity.sensitivity_radii_m)

    def graph_version(self) -> str | None:
        status = self._routing.status()
        if not status.available or not status.tileset_last_modified:
            return None
        return f"{self._config.region.routing_graph.id}@{status.tileset_last_modified}"

    def _cached_locate(self, graph_version: str):
        cache_hits: dict[str, list[RoadCandidate]] = {}
        pending: dict[tuple[float, float], str] = {}

        def locate(lat: float, lon: float, radius_m: float) -> list[RoadCandidate]:
            key = pending.get((lat, lon))
            if key and key in cache_hits:
                return cache_hits[key]
            candidates = self._locator.locate(lat, lon, radius_m)
            if key and self._sf is not None:
                try:
                    with self._sf() as session:
                        AssociationCache(session).put(key, graph_version, int(radius_m), candidates, self._clock())
                        session.commit()
                except Exception as exc:  # noqa: BLE001 - caching is best effort
                    log.warning("association cache write failed: %s", type(exc).__name__)
            return candidates

        return locate, cache_hits, pending

    def assess(self, route: EngineRoute, *, scope: CameraScope, snapshot_id: str | None) -> AssessmentResult:
        not_assessed = lambda msg: AssessmentResult("not_assessed", COUNTING_METHOD_VERSION, float(self._radius), scope.value, snapshot_id, None, None, None, None, warnings=[msg])  # noqa: E731
        if self._sf is None:
            return not_assessed("The camera inventory database is not configured; the route was not assessed.")
        if snapshot_id is None:
            return not_assessed("No validated camera snapshot is available; the route was not assessed.")
        graph_version = self.graph_version()
        if graph_version is None:
            return not_assessed("The routing graph is unavailable; road association was not attempted.")
        try:
            route_edges = self._locator.route_edges(route.shape)
        except AppError as exc:
            return not_assessed(f"Road association unavailable: {exc.message}")
        proximity = PostgisProximityIndex(self._sf, self._config.envelope.geojson_geometry())
        locate, cache_hits, pending = self._cached_locate(graph_version)
        # Pre-load cached candidates for the records near this route so repeated plans do not call the engine again.
        try:
            near = proximity.records_near(snapshot_id, route.shape, max(self._radii + [self._radius]))
            for record in near:
                pending[(record.lat, record.lon)] = record.source_key
            with self._sf() as session:
                cache_hits.update(AssociationCache(session).get_many([r.source_key for r in near], graph_version, self._radius))
        except Exception as exc:  # noqa: BLE001 - a failed proximity query means not assessed, never zero
            log.warning("proximity query failed: %s", type(exc).__name__)
            return not_assessed("The camera proximity query failed; the route was not assessed.")
        try:
            return assess_route(
                route, scope=scope, snapshot_id=snapshot_id, graph_version=graph_version, proximity=proximity,
                route_edges=route_edges, locate=locate, radius_m=float(self._radius), sensitivity_radii_m=self._radii,
            )
        except AppError as exc:
            return not_assessed(f"Road association unavailable: {exc.message}")
