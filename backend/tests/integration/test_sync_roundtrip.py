"""Integration test against a real PostGIS database (set DEFLOCK_TEST_DATABASE_URL).

Runs the sync end to end with a mocked Overpass transport: promotion, identical-snapshot skip,
quarantine on a large drop, failure retention, and the bbox query used by the map overlay.
"""

from __future__ import annotations

import copy
import json
import os

import httpx
import pytest
from sqlalchemy import text

from deflockmigration.data_sources.overpass import OverpassClient
from deflockmigration.ingestion.sync import run_sync
from deflockmigration.storage.db import make_engine, make_session_factory
from deflockmigration.storage.models import Base
from deflockmigration.storage.repositories import CameraRepository, SnapshotRepository

pytestmark = pytest.mark.integration
TEST_URL = os.environ.get("DEFLOCK_TEST_DATABASE_URL")


@pytest.fixture(scope="module")
def session_factory():
    if not TEST_URL:
        pytest.skip("DEFLOCK_TEST_DATABASE_URL not set")
    engine = make_engine(TEST_URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_camera_records_geom_test ON camera_records USING GIST (geom)"))
    yield make_session_factory(engine)
    Base.metadata.drop_all(engine)
    engine.dispose()


def _payload_from_fixture(fixture: dict, *, keep: int | None = None) -> dict:
    elements = [{k: v for k, v in e.items() if not k.startswith("_")} for e in fixture["elements"]]
    if keep is not None:
        elements = elements[:keep]
    return {"version": 0.6, "generator": "Overpass API test", "osm3s": {"timestamp_osm_base": "2026-10-15T20:18:00Z"}, "elements": elements}


def _client(responses):
    calls = iter(responses)

    def handler(request):
        status, body = next(calls)
        return httpx.Response(status, content=body, headers={"content-type": "application/json" if status == 200 else "text/html"})

    return OverpassClient("http://overpass.test/api/interpreter", user_agent="test", transport=httpx.MockTransport(handler), sleep=lambda s: None)


def test_sync_lifecycle(app_config, overpass_fixture_payload, session_factory, tmp_path):
    full = _payload_from_fixture(overpass_fixture_payload)
    first = run_sync(app_config, session_factory, _client([(200, json.dumps(full).encode())]), snapshot_dir=tmp_path, trigger="setup")
    assert first.status == "succeeded" and first.snapshot_id and first.added == len(full["elements"])
    with session_factory() as s:
        active = SnapshotRepository(s).get_active("denver")
        assert active.snapshot_id == first.snapshot_id and active.alpr_count > 0
        rows = CameraRepository(s).in_bbox(active.snapshot_id, -105.4, 39.4, -104.3, 40.2, flock_only=False)
        assert rows and all(r["is_alpr"] for r in rows)
        flock_rows = CameraRepository(s).in_bbox(active.snapshot_id, -105.4, 39.4, -104.3, 40.2, flock_only=True)
        assert 0 < len(flock_rows) <= len(rows)

    again = run_sync(app_config, session_factory, _client([(200, json.dumps(full).encode())]), snapshot_dir=tmp_path)
    assert again.status == "succeeded" and again.snapshot_id == first.snapshot_id and "identical" in again.message

    tiny = copy.deepcopy(_payload_from_fixture(overpass_fixture_payload, keep=2))
    tiny["osm3s"]["timestamp_osm_base"] = "2026-10-16T02:00:00Z"
    quarantined = run_sync(app_config, session_factory, _client([(200, json.dumps(tiny).encode())]), snapshot_dir=tmp_path)
    assert quarantined.status == "quarantined"
    with session_factory() as s:
        assert SnapshotRepository(s).get_active("denver").snapshot_id == first.snapshot_id
        assert SnapshotRepository(s).get(quarantined.snapshot_id).promotion_state == "quarantined"

    failed = run_sync(app_config, session_factory, _client([(502, b"<html>bad gateway</html>")] * 3), snapshot_dir=tmp_path)
    assert failed.status == "failed"
    with session_factory() as s:
        assert SnapshotRepository(s).get_active("denver").snapshot_id == first.snapshot_id
        last_job = s.execute(text("SELECT status, message FROM sync_jobs ORDER BY id DESC LIMIT 1")).one()
        assert last_job.status == "failed" and "fetch failed" in last_job.message
