"""M7 resilience matrix on the real test database: manual-refresh cooldown and force, rollback without deletion,
per-request snapshot pinning across a promotion, a truncated upstream response, and the diff history.

Fixtures and helpers are shared with the M2 round-trip module; this module gets its own database lifecycle.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from deflockmigration.application.review import ReviewError, rollback_snapshot
from deflockmigration.ingestion.sync import run_sync
from deflockmigration.storage.proximity_postgis import PostgisProximityIndex
from deflockmigration.storage.repositories import CameraRepository, SnapshotRepository
from tests.integration.test_sync_roundtrip import _client, _elements, _payload, _run, session_factory  # noqa: F401 - fixture import

pytestmark = pytest.mark.integration


def test_manual_refresh_cooldown_and_force(app_config, overpass_fixture_payload, session_factory, tmp_path):
    """Operator refreshes share a cooldown (a job row records the skip); --force bypasses it; the scheduler is never subject to it."""
    base = _elements(overpass_fixture_payload)
    first = _run(app_config, session_factory, _payload(base, "2026-10-20T00:00:00Z"), tmp_path, trigger="setup")
    assert first.status == "succeeded"
    skipped = _run(app_config, session_factory, _payload(base[1:], "2026-10-20T00:10:00Z"), tmp_path, trigger="manual")
    assert skipped.status == "skipped" and "cooldown" in skipped.message and skipped.snapshot_id == first.snapshot_id
    with session_factory() as s:
        assert SnapshotRepository(s).get_active(app_config.region.region_id).snapshot_id == first.snapshot_id
        job = s.execute(text("SELECT status, trigger, snapshot_id FROM sync_jobs ORDER BY id DESC LIMIT 1")).one()
        assert (job.status, job.trigger, job.snapshot_id) == ("skipped", "manual", first.snapshot_id)
    forced = run_sync(app_config, session_factory, _client([(200, json.dumps(_payload(base[1:], "2026-10-20T00:10:00Z")).encode())]), snapshot_dir=tmp_path, trigger="manual", force=True)
    assert forced.status == "succeeded" and forced.snapshot_id != first.snapshot_id
    scheduled = _run(app_config, session_factory, _payload(base[2:], "2026-10-20T00:15:00Z"), tmp_path, trigger="scheduled")
    assert scheduled.status == "succeeded" and scheduled.snapshot_id != forced.snapshot_id


def test_rollback_restores_a_previously_active_snapshot_without_deleting_anything(app_config, overpass_fixture_payload, session_factory, tmp_path):
    base = _elements(overpass_fixture_payload)
    a = _run(app_config, session_factory, _payload(base, "2026-10-21T00:00:00Z"), tmp_path)
    b = _run(app_config, session_factory, _payload(base[3:], "2026-10-21T06:00:00Z"), tmp_path)
    assert a.status == "succeeded" and b.status == "succeeded"
    with pytest.raises(ReviewError):
        rollback_snapshot(session_factory, app_config.region.region_id, None, "   ")  # a note is required
    with pytest.raises(ReviewError):
        rollback_snapshot(session_factory, app_config.region.region_id, b.snapshot_id, "already active")
    with pytest.raises(ReviewError):
        rollback_snapshot(session_factory, app_config.region.region_id, "ovp-denver-00000000T000000Z-deadbeef", "unknown id")
    message = rollback_snapshot(session_factory, app_config.region.region_id, None, "the newer snapshot dropped a corridor; restoring the previous one")
    assert a.snapshot_id in message and "stays retained" in message
    with session_factory() as s:
        repo = SnapshotRepository(s)
        assert repo.get_active(app_config.region.region_id).snapshot_id == a.snapshot_id
        assert repo.get(b.snapshot_id).promotion_state == "superseded"
        assert repo.get(a.snapshot_id).review_note.startswith("rolled back to:")
        assert CameraRepository(s).count(a.snapshot_id, present_only=False) >= len(base)
        assert s.execute(text("SELECT count(*) FROM sync_jobs WHERE trigger='rollback'")).scalar() == 1
    # The rollback itself can be undone the same way, because nothing was deleted.
    rollback_snapshot(session_factory, app_config.region.region_id, b.snapshot_id, "restoring the newer snapshot after review")
    with session_factory() as s:
        assert SnapshotRepository(s).get_active(app_config.region.region_id).snapshot_id == b.snapshot_id


def test_pinned_snapshot_stays_assessable_while_a_newer_one_is_promoted(app_config, overpass_fixture_payload, session_factory, tmp_path):
    """Per-request version pinning (roadmap 8, step 10): a plan that started on snapshot A keeps A's records after B is promoted."""
    base = _elements(overpass_fixture_payload)
    dropped = {f"osm:{e['type']}:{e['id']}" for e in base[:5]}
    a = _run(app_config, session_factory, _payload(base, "2026-10-22T00:00:00Z"), tmp_path)
    assert a.status == "succeeded"
    with session_factory() as s:
        a_rows = CameraRepository(s).rows_by_key(a.snapshot_id)
    key, row = next((k, r) for k, r in a_rows.items() if k in dropped and r["is_alpr"])
    b = _run(app_config, session_factory, _payload(base[5:], "2026-10-22T06:00:00Z"), tmp_path)  # promoted "during" the request
    assert b.status == "succeeded"
    with session_factory() as s:
        assert SnapshotRepository(s).get_active(app_config.region.region_id).snapshot_id == b.snapshot_id
        assert CameraRepository(s).rows_by_key(a.snapshot_id).keys() == a_rows.keys()  # A is retained unchanged
    proximity = PostgisProximityIndex(session_factory, app_config.envelope.geojson_geometry())
    shape = [(row["lat"] - 0.0005, row["lon"]), (row["lat"] + 0.0005, row["lon"])]
    on_a = {r.source_key: r.lifecycle_state for r in proximity.records_near(a.snapshot_id, shape, 100)}
    on_b = {r.source_key: r.lifecycle_state for r in proximity.records_near(b.snapshot_id, shape, 100)}
    assert on_a[key] == "mapped"  # the pinned snapshot answers as it did when the request started
    assert on_b[key] == "no_longer_mapped"  # the newer snapshot carries the vanished record as uncertain


def test_truncated_response_keeps_the_active_snapshot(app_config, session_factory, tmp_path):
    with session_factory() as s:
        before = SnapshotRepository(s).get_active(app_config.region.region_id).snapshot_id
    truncated = b'{"version": 0.6, "osm3s": {"timestamp_osm_base": "2026-10-22T12:00:00Z"}, "elements": [{"type": "node", "id": 1'
    outcome = run_sync(app_config, session_factory, _client([(200, truncated)] * 3), snapshot_dir=tmp_path)
    assert outcome.status == "failed"
    with session_factory() as s:
        assert SnapshotRepository(s).get_active(app_config.region.region_id).snapshot_id == before
        assert s.execute(text("SELECT status FROM sync_jobs ORDER BY id DESC LIMIT 1")).scalar() == "failed"


def test_diff_history_lists_retained_snapshots_newest_first(app_config, session_factory):
    with session_factory() as s:
        pairs = SnapshotRepository(s).list_diffs(app_config.region.region_id, limit=5)
    assert len(pairs) >= 2 and all(diff.snapshot_id == snapshot.snapshot_id for diff, snapshot in pairs)
    created = [diff.created_at for diff, _ in pairs]
    assert created == sorted(created, reverse=True)
