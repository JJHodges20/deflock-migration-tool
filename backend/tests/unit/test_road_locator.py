from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from deflockmigration.core.errors import ROUTER_UNAVAILABLE, AppError
from deflockmigration.routing.road_locator import ValhallaRoadLocator

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _locator(handler):
    return ValhallaRoadLocator("http://valhalla.test:8002", transport=httpx.MockTransport(handler))


def test_locate_dedupes_per_way_and_sorts_by_distance():
    payload = json.loads((FIXTURES / "fixture_valhalla_locate_capitol_cameras.json").read_text(encoding="utf-8"))
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=payload)

    candidates = _locator(handler).locate(39.7400883, -104.9799239, 50)
    assert seen["costing"] == "auto" and seen["verbose"] is True and seen["locations"][0]["radius"] == 50
    assert candidates == sorted(candidates, key=lambda c: (c.distance_m, c.way_id))
    assert len({c.way_id for c in candidates}) == len(candidates)
    # The record sits at a corner: Pearl Street and East Colfax Avenue tie at 3.2 m (a real ambiguity case).
    nearest = [c for c in candidates if c.distance_m == pytest.approx(3.2)]
    assert {tuple(c.names) for c in nearest} >= {("Pearl Street",), ("East Colfax Avenue", "I 70 BUS", "US 40", "US 287")}
    assert all(c.distance_m <= 50 for c in candidates)
    assert any(c.road_class == "residential" and c.use == "road" for c in nearest)


def test_route_edges_parse_the_recorded_trace():
    fixture = json.loads((FIXTURES / "fixture_valhalla_trace_attributes_union_to_zoo.json").read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["shape_match"] == "edge_walk" and "edge.way_id" in body["filters"]["attributes"]
        return httpx.Response(200, json=fixture["trace"])

    shape = [(lat, lon) for lon, lat in fixture["route_geometry"]["coordinates"]]
    edges = _locator(handler).route_edges(shape)
    assert len(edges) == len(fixture["trace"]["edges"])
    assert edges[0].names == ["Wynkoop Street"] and edges[0].begin_shape_index == 0
    assert edges[-1].end_shape_index == len(shape) - 1
    assert all(e.begin_shape_index <= e.end_shape_index for e in edges)
    assert sum(e.length_m for e in edges) == pytest.approx(6423, rel=0.02)


def test_engine_errors_become_router_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(AppError) as exc:
        _locator(handler).locate(39.7, -104.9, 50)
    assert exc.value.code == ROUTER_UNAVAILABLE

    def failing(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(AppError):
        _locator(failing).route_edges([(39.7, -104.9), (39.71, -104.91)])
