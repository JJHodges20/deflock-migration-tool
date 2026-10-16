"""Routing provider interface. Adapters may only use documented, tested engine parameters."""

from __future__ import annotations

from typing import Protocol

from deflockmigration.domain.routes import EngineRoute, LatLon, RouterStatus


class RoutingProvider(Protocol):
    def baseline_candidates(self, origin: LatLon, destination: LatLon, *, alternates: int, request_id: str) -> list[EngineRoute]:
        """Return the engine's primary route plus up to `alternates` alternates with default costing."""

    def status(self) -> RouterStatus:
        """Cheap readiness probe; must never raise."""
