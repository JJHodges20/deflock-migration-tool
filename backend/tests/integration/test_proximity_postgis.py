"""PostGIS proximity and association-cache behaviour against the real test database.

The geography query must agree with the metric in-memory index to within a metre and must find records
by meters, never degrees; envelope coverage must be a length fraction in meters.
"""

from __future__ import annotations

import datetime as dt
import json
import os

import pytest
from shapely.geometry import box
from sqlalchemy import text

from deflockmigration.domain.assessment import CameraNearRoute, RoadCandidate
from deflockmigration.geospatial.proximity import MemoryProximityIndex
from deflockmigration.storage.association_cache import AssociationCache
from deflockmigration.storage.db import make_engine, make_session_factory
from deflockmigration.storage.models import Base, CameraRecord, CameraSnapshot
from deflockmigration.storage.proximity_postgis import PostgisProximityIndex

pytestmark = pytest.mark.integration
TEST_URL = os.environ.get("DEFLOCK_TEST_DATABASE_URL")
LAT0, LON0 = 39.7400, -104.9900


@pytest.fixture(scope="module")
def session_factory():
    if not TEST_URL:
        pytest.skip("DEFLOCK_TEST_DATABASE_URL not set")
    engine = make_engine(TEST_URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield make_session_factory(engine)
    Base.metadata.drop_all(engine)
    engine.dispose()


def offset(east_m: float, north_m: float) -> tuple[float, float]:
    import math

    return (LAT0 + north_m / 111320.0, LON0 + east_m / (111320.0 * math.cos(math.radians(LAT0))))


def _record(key: str, east: float, north: float, **kw) -> CameraNearRoute:
    lat, lon = offset(east, north)
    base = dict(source_key=key, lat=lat, lon=lon, is_alpr=True, is_flock=True, manufacturer="flock_safety", lifecycle_state="mapped", direction_raw=None,
                direction_parsed_deg=None, direction_conflict=False, in_envelope=True, operator=None, source_timestamp=None, check_date=None, distance_m=0.0)
    base.update(kw)
    return CameraNearRoute(**base)


def test_postgis_proximity_matches_metric_index_and_measures_meters(session_factory):
    now = dt.datetime.now(dt.UTC)
    records = [_record("osm:node:1", 500, 8), _record("osm:node:2", 900, 45), _record("osm:node:3", 1200, 90), _record("osm:node:4", 300, 400), _record("osm:node:5", 700, 20, is_alpr=False)]
    with session_factory() as s:
        s.add(CameraSnapshot(snapshot_id="prox-1", region_id="denver", source="test", endpoint="test", query_sha256="x", query_bbox="x", downloaded_at_start=now, downloaded_at_end=now, element_count=5, record_count=5, raw_sha256="x", raw_bytes=0, parser_version="t", promotion_state="active", created_at=now))
        s.flush()  # the models declare the foreign key without an ORM relationship, so insert the parent explicitly first
        for r in records:
            s.add(CameraRecord(snapshot_id="prox-1", source_key=r.source_key, source_type="node", source_id=int(r.source_key.split(":")[-1]), geom=f"SRID=4326;POINT({r.lon} {r.lat})", geometry_quality="point", raw_tags={}, is_alpr=r.is_alpr, alpr_evidence="t", is_flock=r.is_flock, manufacturer_normalized=r.manufacturer, lifecycle_state="mapped", parse_warnings=[], in_envelope=True))
        s.commit()
    shape = [offset(x, 0.0) for x in range(0, 2001, 50)]
    envelope = box(LON0 - 0.01, LAT0 - 0.01, offset(1000, 0)[1], LAT0 + 0.01)
    pg = PostgisProximityIndex(session_factory, json.loads(json.dumps(envelope.__geo_interface__)))
    mem = MemoryProximityIndex(records, envelope)
    pg_hits = {r.source_key: r.distance_m for r in pg.records_near("prox-1", shape, 100)}
    mem_hits = {r.source_key: r.distance_m for r in mem.records_near("prox-1", shape, 100)}
    assert set(pg_hits) == set(mem_hits) == {"osm:node:1", "osm:node:2", "osm:node:3"}  # 400 m away and non-ALPR are excluded
    for key in pg_hits:
        assert abs(pg_hits[key] - mem_hits[key]) < 1.0, key
    assert abs(pg_hits["osm:node:2"] - 45) < 1.0  # meters, not degrees
    coverage = pg.envelope_coverage(shape)
    assert abs(coverage - 0.5) < 0.02 and abs(mem.envelope_coverage(shape) - 0.5) < 0.02


def test_association_cache_roundtrip_and_graph_pruning(session_factory):
    candidates = [RoadCandidate(10, ["Main Street"], 4.0, "secondary", "road", False, False), RoadCandidate(11, ["Side Street"], 9.0, "residential", "road", False, False)]
    now = dt.datetime.now(dt.UTC)
    with session_factory() as s:
        cache = AssociationCache(s)
        cache.put("osm:node:1", "graph@a", 50, candidates, now)
        cache.put("osm:node:1", "graph@old", 50, candidates[:1], now)
        cache.put("osm:node:2", "graph@a", 50, [], now)
        s.commit()
        got = cache.get_many(["osm:node:1", "osm:node:2", "osm:node:9"], "graph@a", 50)
        assert set(got) == {"osm:node:1", "osm:node:2"} and got["osm:node:1"][0].names == ["Main Street"] and got["osm:node:2"] == []
        assert cache.count_for("graph@a", 50) == 2
        cache.put("osm:node:1", "graph@a", 50, candidates[:1], now)  # replace, not duplicate
        s.commit()
        assert cache.count_for("graph@a", 50) == 2 and len(cache.get_many(["osm:node:1"], "graph@a", 50)["osm:node:1"]) == 1
        assert cache.prune_other_graphs("graph@a") == 1 and cache.count_for("graph@old", 50) == 0
        s.commit()
        assert cache.clear_for("graph@a", 50) == 2 and cache.count_for("graph@a", 50) == 0  # recompute path drops only that graph/radius
        s.commit()
