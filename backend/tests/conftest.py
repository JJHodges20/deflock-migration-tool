"""Shared test fixtures. Everything here is explicitly a fixture; production code never imports it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from deflockmigration.api.app import create_app
from deflockmigration.core.config_loader import AppConfig, load_app_config
from deflockmigration.core.errors import NO_DRIVABLE_ROUTE, ROUTER_UNAVAILABLE, AppError
from deflockmigration.core.settings import Settings
from deflockmigration.domain.routes import EngineRoute, LatLon, Maneuver, RouterStatus
from deflockmigration.geocoding.provider import NullGeocoder
from deflockmigration.geospatial.polyline import decode_polyline6

FIXTURES = Path(__file__).parent / "fixtures"


def find_project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "configs" / "regions" / "denver.yaml").exists():
            return parent
    raise RuntimeError("project root with configs/ not found")


@pytest.fixture(scope="session")
def project_root() -> Path:
    return find_project_root()


@pytest.fixture(scope="session")
def settings(project_root: Path) -> Settings:
    return Settings(app_env="test", project_root=project_root, database_url=None, geocoder_url=None, valhalla_url="http://valhalla.invalid:8002")


@pytest.fixture(scope="session")
def app_config(settings: Settings) -> AppConfig:
    return load_app_config(settings)


@pytest.fixture(scope="session")
def valhalla_fixture_payload() -> dict:
    return json.loads((FIXTURES / "fixture_valhalla_route_with_alternates.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def overpass_fixture_payload() -> dict:
    return json.loads((FIXTURES / "fixture_overpass_alpr_sample.json").read_text(encoding="utf-8"))


def route_from_trip(trip: dict, source: str, index: int) -> EngineRoute:
    leg = trip["legs"][0]
    shape = decode_polyline6(leg["shape"])
    maneuvers = [
        Maneuver(
            instruction=m.get("instruction", ""),
            type=m.get("type", 0),
            length_m=m.get("length", 0.0) * 1000,
            time_s=m.get("time", 0.0),
            begin_shape_index=m.get("begin_shape_index", 0),
            end_shape_index=m.get("end_shape_index", 0),
            street_names=m.get("street_names", []),
        )
        for m in leg["maneuvers"]
    ]
    return EngineRoute(
        engine_route_id=f"{source}-{index}",
        shape=shape,
        duration_s=trip["summary"]["time"],
        length_m=trip["summary"]["length"] * 1000,
        maneuvers=maneuvers,
        has_highway=trip["summary"].get("has_highway", False),
        has_toll=trip["summary"].get("has_toll", False),
        source=source,
    )


class FakeRoutingProvider:
    """Serves the real M0 Valhalla fixture (primary slower than its alternates) without a network."""

    def __init__(self, payload: dict, *, mode: str = "ok"):
        self.payload = payload
        self.mode = mode
        self.calls: list[dict] = []

    def baseline_candidates(self, origin: LatLon, destination: LatLon, *, alternates: int, request_id: str) -> list[EngineRoute]:
        self.calls.append({"alternates": alternates, "request_id": request_id})
        if self.mode == "unavailable":
            raise AppError(ROUTER_UNAVAILABLE, "The routing engine is not reachable.")
        if self.mode == "no_route":
            raise AppError(NO_DRIVABLE_ROUTE, "No drivable route was found between these points.")
        routes = [route_from_trip(self.payload["trip"], "primary", 0)]
        for i, alt in enumerate(self.payload.get("alternates", [])[:alternates], start=1):
            routes.append(route_from_trip(alt["trip"], "alternate", i))
        return routes

    def avoiding_candidates(self, origin: LatLon, destination: LatLon, *, alternates: int, request_id: str, avoidance) -> list[EngineRoute]:
        """The fixture has no other geometry to offer, so penalized and excluded requests return the same routes
        (what a real engine does when nothing cheaper exists); the search must converge on that."""
        self.calls.append({"alternates": alternates, "request_id": request_id, "avoidance": avoidance.kind, "penalties": len(avoidance.penalties), "exclusions": len(avoidance.exclusions)})
        if self.mode != "ok":
            raise AppError(ROUTER_UNAVAILABLE, "The routing engine is not reachable.")
        routes = [route_from_trip(self.payload["trip"], avoidance.kind, 0)]
        for i, alt in enumerate(self.payload.get("alternates", [])[:alternates], start=1):
            routes.append(route_from_trip(alt["trip"], avoidance.kind, i))
        return routes

    def status(self) -> RouterStatus:
        return RouterStatus(available=self.mode == "ok", version="fixture-3.9.1", has_tiles=True, has_admins=True, has_timezones=True)


@pytest.fixture
def fake_routing(valhalla_fixture_payload: dict) -> FakeRoutingProvider:
    return FakeRoutingProvider(valhalla_fixture_payload)


@pytest.fixture
def client(settings: Settings, app_config: AppConfig, fake_routing: FakeRoutingProvider) -> TestClient:
    app = create_app(settings, config=app_config, routing=fake_routing, geocoder=NullGeocoder(), session_factory=None)
    return TestClient(app, raise_server_exceptions=False)
