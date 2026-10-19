"""Integration tests against a real PostGIS database (set DEFLOCK_TEST_DATABASE_URL).

Covers the M2 matrix with a mocked Overpass transport: promotion, identical-snapshot skip,
record versions across snapshots, node/way identity, lifecycle change, vanished records carried as
"no longer mapped", reappearance, retention expiry, envelope flag, quarantine and operator review,
pruning, concurrent sync, and failure retention of the last good snapshot.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import os

import httpx
import pytest
from sqlalchemy import text

from deflockmigration.application.review import ReviewError, accept_snapshot, list_snapshots, reject_snapshot
from deflockmigration.data_sources.overpass import OverpassClient
from deflockmigration.ingestion.normalize import normalize_elements
from deflockmigration.ingestion.sync import _lock_key, run_sync
from deflockmigration.storage.db import make_engine, make_session_factory
from deflockmigration.storage.models import Base
from deflockmigration.storage.repositories import CameraRepository, SnapshotRepository

pytestmark = pytest.mark.integration
TEST_URL = os.environ.get("DEFLOCK_TEST_DATABASE_URL")
FAR_RECORD = {"type": "node", "id": 999999999, "lat": 39.0, "lon": -98.0, "version": 1, "timestamp": "2026-10-16T00:00:00Z",
              "tags": {"man_made": "surveillance", "surveillance:type": "ALPR", "manufacturer": "Flock Safety"}}


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


def _elements(fixture: dict) -> list[dict]:
    elements = [{k: v for k, v in e.items() if not k.startswith("_")} for e in fixture["elements"]]
    return sorted(elements, key=lambda e: e["id"])


def _payload(elements: list[dict], base: str) -> dict:
    return {"version": 0.6, "generator": "Overpass API test", "osm3s": {"timestamp_osm_base": base}, "elements": elements}


def _client(responses):
    calls = iter(responses)

    def handler(request):
        status, body = next(calls)
        return httpx.Response(status, content=body, headers={"content-type": "application/json" if status == 200 else "text/html"})

    return OverpassClient("http://overpass.test/api/interpreter", user_agent="test", transport=httpx.MockTransport(handler), sleep=lambda s: None)


def _run(config, session_factory, payload, tmp_path, clock=None, trigger="scheduled"):
    kwargs = {"snapshot_dir": tmp_path, "trigger": trigger}
    if clock:
        kwargs["clock"] = clock
    return run_sync(config, session_factory, _client([(200, json.dumps(payload).encode())]), **kwargs)


def _expected_in_envelope_alpr(config, elements: list[dict]) -> int:
    return sum(1 for r in normalize_elements(elements) if r.is_alpr and config.envelope.contains(r.lat, r.lon))


def _with_quality(config, **updates):
    validation = config.data_quality.snapshot_validation.model_copy(update=updates)
    return config.model_copy(update={"data_quality": config.data_quality.model_copy(update={"snapshot_validation": validation})})


def _with_retention(config, **updates):
    retention = config.data_quality.retention.model_copy(update=updates)
    return config.model_copy(update={"data_quality": config.data_quality.model_copy(update={"retention": retention})})


def test_inventory_lifecycle(app_config, overpass_fixture_payload, session_factory, tmp_path):
    base = _elements(overpass_fixture_payload)
    keys = [f"osm:{e['type']}:{e['id']}" for e in base]
    missing_keys, bumped_key, changed_key = keys[:3], keys[3], keys[4]

    # A: first snapshot
    a = _run(app_config, session_factory, _payload(base, "2026-10-15T20:00:00Z"), tmp_path)
    assert a.status == "succeeded" and a.added == len(base) and a.carried == 0
    with session_factory() as s:
        active = SnapshotRepository(s).get_active(app_config.region.region_id)
        assert active.snapshot_id == a.snapshot_id
        # The envelope flag is counted against the configured envelope: under the Denver pilot configuration part of the
        # M0 sample lies outside the 20 km envelope, while the statewide envelope contains all of it (step B adds a
        # record outside both).
        assert active.in_envelope_alpr_count == _expected_in_envelope_alpr(app_config, base)
        assert active.alpr_count == sum(1 for r in normalize_elements(base) if r.is_alpr)
        assert SnapshotRepository(s).diff_for(a.snapshot_id).added_count == len(base)

    # identical payload -> same snapshot, nothing new
    again = _run(app_config, session_factory, _payload(base, "2026-10-15T20:00:00Z"), tmp_path)
    assert again.status == "succeeded" and again.snapshot_id == a.snapshot_id and "identical" in again.message

    # B: three records vanish, one version bump, one lifecycle change (also a new version), one new record outside the envelope
    b_elements = []
    for e in base[3:]:
        e = copy.deepcopy(e)
        key = f"osm:{e['type']}:{e['id']}"
        if key == bumped_key:
            e["version"] += 1
        if key == changed_key:
            e["version"] += 1
            e["tags"]["removed:surveillance:type"] = e["tags"].pop("surveillance:type")
        b_elements.append(e)
    b_elements.append(FAR_RECORD)
    b = _run(app_config, session_factory, _payload(b_elements, "2026-10-16T02:00:00Z"), tmp_path)
    assert b.status == "succeeded"
    assert (b.added, b.changed, b.no_longer_present, b.carried) == (1, 2, 3, 3)
    with session_factory() as s:
        repo = CameraRepository(s)
        rows = repo.rows_by_key(b.snapshot_id)
        for key in missing_keys:
            assert rows[key]["lifecycle_state"] == "no_longer_mapped" and rows[key]["missing_since"] is not None
            assert rows[key]["last_seen_snapshot_id"] == a.snapshot_id
            assert "retained as uncertain" in " ".join(rows[key]["parse_warnings"])
        assert rows[changed_key]["lifecycle_state"] == "removed" and rows[changed_key]["is_alpr"]
        far = rows["osm:node:999999999"]
        assert far["in_envelope"] is False and far["is_alpr"] and far["is_flock"]
        snapshot = SnapshotRepository(s).get_active(app_config.region.region_id)
        assert snapshot.snapshot_id == b.snapshot_id
        assert snapshot.no_longer_mapped_count == 3
        assert snapshot.in_envelope_alpr_count == _expected_in_envelope_alpr(app_config, b_elements)  # the far record is ALPR but outside the envelope
        assert repo.count(b.snapshot_id, alpr_only=True) == snapshot.alpr_count  # present_only excludes carried rows
        history = repo.history(bumped_key)
        assert [h["snapshot_id"] for h in history] == [b.snapshot_id, a.snapshot_id]
        assert history[0]["source_version"] == history[1]["source_version"] + 1
        diff = SnapshotRepository(s).diff_for(b.snapshot_id)
        assert (diff.added_count, diff.changed_count, diff.missing_count, diff.carried_count, diff.expired_count) == (1, 2, 3, 3, 0)
        assert sorted(diff.missing_keys) == sorted(missing_keys)
        # carried (uncertain) records still appear in the overlay query with their flag
        overlay = {r["source_key"]: r for r in repo.in_bbox(b.snapshot_id, -105.4, 39.4, -104.3, 40.2, flock_only=False)}
        assert overlay[missing_keys[0]]["lifecycle_state"] == "no_longer_mapped"

    # C: one of the three reappears
    c_elements = b_elements + [copy.deepcopy(base[0])]
    c = _run(app_config, session_factory, _payload(c_elements, "2026-10-16T08:00:00Z"), tmp_path)
    assert c.status == "succeeded" and c.carried == 2
    with session_factory() as s:
        diff = SnapshotRepository(s).diff_for(c.snapshot_id)
        assert diff.reappeared_count == 1 and diff.carried_count == 2 and diff.missing_count == 0
        rows = CameraRepository(s).rows_by_key(c.snapshot_id)
        assert rows[missing_keys[0]]["lifecycle_state"] == "mapped" and rows[missing_keys[0]]["missing_since"] is None

    # D: retention expiry drops the two still-missing records
    later = lambda: dt.datetime.now(dt.UTC) + dt.timedelta(hours=100)  # noqa: E731
    d = _run(app_config, session_factory, _payload(c_elements, "2026-10-16T14:00:00Z"), tmp_path, clock=later)
    assert d.status == "succeeded" and d.carried == 0
    with session_factory() as s:
        diff = SnapshotRepository(s).diff_for(d.snapshot_id)
        assert diff.expired_count == 2
        assert set(CameraRepository(s).rows_by_key(d.snapshot_id)) == {f"osm:{e['type']}:{e['id']}" for e in c_elements}

    # Quarantine: a near-empty result is never published; operator review decides
    tiny = _payload(c_elements[:2], "2026-10-16T20:00:00Z")
    q = _run(app_config, session_factory, tiny, tmp_path, clock=later)
    assert q.status == "quarantined"
    with session_factory() as s:
        assert SnapshotRepository(s).get_active(app_config.region.region_id).snapshot_id == d.snapshot_id
    pending = list_snapshots(session_factory, app_config.region.region_id, states=["quarantined"])
    assert [p.snapshot_id for p in pending] == [q.snapshot_id] and "dropped" in pending[0].quarantine_reason
    with pytest.raises(ReviewError):
        reject_snapshot(session_factory, app_config.region.region_id, q.snapshot_id, "   ")
    reject_snapshot(session_factory, app_config.region.region_id, q.snapshot_id, "upstream returned a partial result")
    with pytest.raises(ReviewError):
        accept_snapshot(session_factory, app_config.region.region_id, q.snapshot_id, "already rejected")
    q2 = _run(app_config, session_factory, _payload(c_elements[:3], "2026-10-16T21:00:00Z"), tmp_path, clock=later)
    assert q2.status == "quarantined"
    accept_snapshot(session_factory, app_config.region.region_id, q2.snapshot_id, "corroborated: mass retirement confirmed in OSM history")
    with session_factory() as s:
        repo = SnapshotRepository(s)
        assert repo.get_active(app_config.region.region_id).snapshot_id == q2.snapshot_id
        assert repo.get(d.snapshot_id).promotion_state == "superseded"
        assert repo.get(q.snapshot_id).promotion_state == "rejected" and repo.get(q.snapshot_id).review_note.startswith("rejected:")
        assert s.execute(text("SELECT count(*) FROM sync_jobs WHERE trigger='review'")).scalar() == 2

    # E: growth back to the full set is publishable; pruning keeps the configured history only
    pruning_config = _with_retention(app_config, keep_superseded_snapshots=1, keep_quarantined_snapshots=1)
    e = _run(pruning_config, session_factory, _payload(c_elements, "2026-10-17T02:00:00Z"), tmp_path, clock=later)
    assert e.status == "succeeded" and e.pruned >= 1
    with session_factory() as s:
        repo = SnapshotRepository(s)
        assert len(repo.list(app_config.region.region_id, states=["superseded"], limit=100)) == 1
        assert len(repo.list(app_config.region.region_id, states=["quarantined", "rejected"], limit=100)) == 1
        assert repo.get_active(app_config.region.region_id).snapshot_id == e.snapshot_id
    assert not (tmp_path / f"{a.snapshot_id}.json").exists()
    assert (tmp_path / f"{e.snapshot_id}.json").exists()

    # Concurrent sync: a second runner is skipped while the region lock is held
    with session_factory() as holder:
        holder.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _lock_key(app_config.region.region_id)})
        skipped = _run(app_config, session_factory, _payload(c_elements, "2026-10-17T03:00:00Z"), tmp_path)
        assert skipped.status == "skipped"
        holder.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _lock_key(app_config.region.region_id)})

    # Failure: upstream errors keep the last good snapshot
    failed = run_sync(app_config, session_factory, _client([(502, b"<html>bad gateway</html>")] * 3), snapshot_dir=tmp_path)
    assert failed.status == "failed"
    with session_factory() as s:
        assert SnapshotRepository(s).get_active(app_config.region.region_id).snapshot_id == e.snapshot_id
        last_job = s.execute(text("SELECT status, message FROM sync_jobs ORDER BY id DESC LIMIT 1")).one()
        assert last_job.status == "failed" and "fetch failed" in last_job.message


def test_drop_policy_discards_vanished_records_immediately(app_config, overpass_fixture_payload, session_factory, tmp_path):
    config = _with_quality(app_config, unresolved_disappearance="drop")
    base = _elements(overpass_fixture_payload)
    first = _run(config, session_factory, _payload(base, "2026-10-18T00:00:00Z"), tmp_path)
    second = _run(config, session_factory, _payload(base[5:], "2026-10-18T06:00:00Z"), tmp_path)
    assert first.status == "succeeded" and second.status == "succeeded"
    assert second.no_longer_present == 5 and second.carried == 0
    with session_factory() as s:
        assert SnapshotRepository(s).diff_for(second.snapshot_id).expired_count == 5
