from __future__ import annotations

import pytest

from deflockmigration.domain.routes import EngineRoute, Maneuver
from deflockmigration.geospatial.polyline import decode_polyline6, encode_polyline6, to_geojson_linestring
from deflockmigration.routing.candidates import choose_standard, dedupe, validate_maneuvers
from tests.conftest import route_from_trip


def test_polyline6_roundtrip():
    coords = [(39.753, -105.0002), (39.7531, -105.0001), (39.75, -104.95)]
    encoded = encode_polyline6(coords)
    assert decode_polyline6(encoded) == [(round(a, 6), round(b, 6)) for a, b in coords]
    assert to_geojson_linestring(coords)["coordinates"][0] == [-105.0002, 39.753]


def test_fixture_shape_decodes_to_denver(valhalla_fixture_payload):
    shape = decode_polyline6(valhalla_fixture_payload["trip"]["legs"][0]["shape"])
    assert len(shape) > 100
    assert all(39.6 < lat < 39.9 and -105.1 < lon < -104.8 for lat, lon in shape)


def _route(rid: str, duration: float, length: float, shape=None, maneuvers=None, source="primary") -> EngineRoute:
    return EngineRoute(
        engine_route_id=rid,
        shape=shape or [(39.0, -105.0), (39.1, -105.1)],
        duration_s=duration,
        length_m=length,
        maneuvers=maneuvers if maneuvers is not None else [Maneuver("Start", 1, 10, 1, 0, 1), Maneuver("Arrive", 4, 0, 0, 1, 1)],
        has_highway=False,
        has_toll=False,
        source=source,
    )


def test_choose_standard_prefers_fastest_reported_time_over_primary(valhalla_fixture_payload):
    primary = route_from_trip(valhalla_fixture_payload["trip"], "primary", 0)
    alternates = [route_from_trip(a["trip"], "alternate", i) for i, a in enumerate(valhalla_fixture_payload["alternates"], start=1)]
    standard = choose_standard([primary, *alternates])
    assert standard.source == "alternate"
    assert standard.duration_s < primary.duration_s


def test_choose_standard_tie_breaks_on_length_then_primary():
    a = _route("primary-0", 100, 2000)
    b = _route("alternate-1", 100, 1500, source="alternate")
    assert choose_standard([a, b]).engine_route_id == "alternate-1"
    c = _route("alternate-2", 100, 2000, source="alternate")
    assert choose_standard([a, c]).engine_route_id == "primary-0"
    with pytest.raises(ValueError):
        choose_standard([])


def test_dedupe_removes_identical_geometry():
    a = _route("a", 100, 1000)
    b = _route("b", 120, 1000)
    c = _route("c", 90, 900, shape=[(39.0, -105.0), (39.2, -105.2)])
    assert [r.engine_route_id for r in dedupe([a, b, c])] == ["a", "c"]


def test_validate_maneuvers_flags_problems():
    assert validate_maneuvers(_route("ok", 1, 1)) == []
    assert "no maneuvers" in validate_maneuvers(_route("empty", 1, 1, maneuvers=[]))
    bad = _route("bad", 1, 1, maneuvers=[Maneuver("", 8, 1, 1, 5, 6), Maneuver("x", 8, 1, 1, 2, 3)])
    problems = validate_maneuvers(bad)
    assert any("no instruction" in p for p in problems)
    assert any("decreases" in p for p in problems)
    assert any("not a start" in p for p in problems)
    assert any("not a destination" in p for p in problems)
