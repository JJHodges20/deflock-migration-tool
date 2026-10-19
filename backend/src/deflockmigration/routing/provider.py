"""Routing provider interface. Adapters may only use documented, tested engine parameters."""

from __future__ import annotations

from typing import Protocol

from deflockmigration.domain.routes import AvoidanceRequest, EngineRoute, LatLon, RouterStatus


class RoutingProvider(Protocol):
    def baseline_candidates(self, origin: LatLon, destination: LatLon, *, alternates: int, request_id: str) -> list[EngineRoute]:
        """Return the engine's primary route plus up to `alternates` alternates with default costing."""

    def avoiding_candidates(self, origin: LatLon, destination: LatLon, *, alternates: int, request_id: str, avoidance: AvoidanceRequest) -> list[EngineRoute]:
        """Same as `baseline_candidates` but with the engine's documented soft penalties and/or hard point exclusions
        applied during path finding. Reported travel times must stay physical (decision 0001 D5)."""

    def status(self) -> RouterStatus:
        """Cheap readiness probe; must never raise."""
