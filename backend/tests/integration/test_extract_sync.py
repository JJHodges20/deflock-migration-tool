"""M10: the unchanged sync pipeline fed by the extract source, on PostGIS, with a fake replication server (no network)."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest
from sqlalchemy import text

from deflockmigration.domain.cameras import LifecycleState
from deflockmigration.ingestion.sync import run_sync
from deflockmigration.storage.db import make_engine, make_session_factory
from deflockmigration.storage.models import Base
from deflockmigration.storage.repositories import CameraRepository, SnapshotRepository

osmium = pytest.importorskip("osmium")

from tests.unit.test_extract_source import CAMERA, CHEYENNE, DENVER, PUEBLO, REPLICATION_URL, TS, FakeServer, State, make_source, write_pbf  # noqa: E402

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
    yield make_session_factory(engine)
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_extract_source_round_trip(app_config, session_factory, tmp_path):
    assert app_config.region.camera_source.adapter == "geofabrik_extract"
    seed = write_pbf(tmp_path / "pbf" / "colorado-latest.osm.pbf", sequence=4945, nodes=[(1, *DENVER, CAMERA), (2, *PUEBLO, CAMERA), (3, *CHEYENNE, CAMERA)])
    server = FakeServer({None: State(4945, TS), 4945: State(4945, TS)})
    source = make_source(tmp_path, server, seed=seed)
    snapshots_dir = tmp_path / "snapshots"

    # A: first snapshot, seeded from the graph extract; Cheyenne lies beyond the publisher's outline and so outside envelope v2
    a = run_sync(app_config, session_factory, source, snapshot_dir=snapshots_dir, trigger="setup")
    assert a.status == "succeeded" and a.snapshot_id.startswith("ext-colorado-20261018T202506Z-"), a
    assert (a.added, a.changed, a.no_longer_present, a.carried) == (3, 0, 0, 0)
    with session_factory() as s:
        snapshot = SnapshotRepository(s).get(a.snapshot_id)
        assert snapshot.source == "OpenStreetMap via Geofabrik extract and daily diffs" and snapshot.endpoint == REPLICATION_URL
        assert snapshot.timestamp_osm_base == TS and snapshot.generator.startswith("DeFlockMigration extract adapter")
        details = snapshot.source_details
        assert details["adapter"] == "geofabrik_extract" and details["replication_sequence"] == 4945
        assert details["update"]["status"] == "up_to_date" and details["update"]["seeded_from"] == str(seed) and details["extraction"]["nodes"] == 3
        assert snapshot.alpr_count == 3 and snapshot.flock_count == 3 and snapshot.in_envelope_alpr_count == 2
        rows = CameraRepository(s).rows_by_key(a.snapshot_id)
        assert rows["osm:node:1"]["in_envelope"] is True and rows["osm:node:3"]["in_envelope"] is False
        assert Path(snapshot.raw_path).exists() and b'"user"' not in Path(snapshot.raw_path).read_bytes()

    # nothing new on the server: identical data, the same snapshot stays active
    again = run_sync(app_config, session_factory, source, snapshot_dir=snapshots_dir)
    assert again.status == "succeeded" and again.snapshot_id == a.snapshot_id and "identical" in again.message

    # B: one change file removes Pueblo and adds a record; the removed one is carried as no longer mapped, judged against the current envelope
    later = TS + dt.timedelta(days=1)

    def apply(infile, outfile, start):
        assert start == 4946
        write_pbf(Path(outfile), sequence=4946, timestamp=later, nodes=[(1, *DENVER, CAMERA), (3, *CHEYENNE, CAMERA), (4, -105.0, 40.0, CAMERA)])
        return (4946, 4946)

    server.states = {None: State(4946, later), 4945: State(4945, TS), 4946: State(4946, later)}
    server.apply = apply
    b = run_sync(app_config, session_factory, source, snapshot_dir=snapshots_dir)
    assert b.status == "succeeded" and b.snapshot_id.startswith("ext-colorado-20261019T202506Z-"), b
    assert (b.added, b.changed, b.no_longer_present, b.carried) == (1, 0, 1, 1)
    with session_factory() as s:
        snapshot = SnapshotRepository(s).get(b.snapshot_id)
        assert snapshot.source_details["update"]["status"] == "updated" and snapshot.source_details["update"]["diffs_applied"] == 1
        assert snapshot.source_details["replication_sequence"] == 4946 and snapshot.previous_active_snapshot_id == a.snapshot_id
        rows = CameraRepository(s).rows_by_key(b.snapshot_id)
        assert rows["osm:node:2"]["lifecycle_state"] == str(LifecycleState.NO_LONGER_MAPPED) and rows["osm:node:2"]["in_envelope"] is True
        assert rows["osm:node:4"]["in_envelope"] is True and set(rows) == {"osm:node:1", "osm:node:2", "osm:node:3", "osm:node:4"}
        assert SnapshotRepository(s).get_active(app_config.region.region_id).snapshot_id == b.snapshot_id
