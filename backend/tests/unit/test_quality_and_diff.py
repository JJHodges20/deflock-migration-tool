from __future__ import annotations

from deflockmigration.core.config_loader import SnapshotValidationConfig
from deflockmigration.ingestion.diff import compute_diff
from deflockmigration.ingestion.quality import evaluate_snapshot

CFG = SnapshotValidationConfig(min_element_count=1, max_count_drop_fraction=0.5)


def test_empty_result_is_quarantined_not_zero_cameras():
    verdict = evaluate_snapshot(0, 0, 1500, CFG)
    assert not verdict.publishable and "below minimum" in verdict.quarantine_reason


def test_large_drop_is_quarantined_and_small_drop_is_not():
    assert not evaluate_snapshot(600, 600, 1540, CFG).publishable
    verdict = evaluate_snapshot(1400, 1400, 1540, CFG)
    assert verdict.publishable and verdict.report["alpr_drop_fraction_vs_previous"] == round(1 - 1400 / 1540, 4)


def test_first_snapshot_and_growth_are_publishable():
    assert evaluate_snapshot(10, 10, None, CFG).publishable
    assert evaluate_snapshot(2000, 2000, 1540, CFG).publishable


def test_diff_categories():
    previous_present = {"osm:node:1": 3, "osm:node:2": 1, "osm:way:2": 5, "osm:node:3": 2}
    previous_carried = {"osm:node:9", "osm:node:8"}
    current = {"osm:node:1": 4, "osm:node:2": 1, "osm:node:4": 1, "osm:node:9": 7}
    diff = compute_diff(previous_present, previous_carried, current)
    assert diff.added_keys == ["osm:node:4"]
    assert diff.changed == [{"key": "osm:node:1", "from_version": 3, "to_version": 4}]
    assert diff.missing_keys == ["osm:node:3", "osm:way:2"]
    assert diff.reappeared_keys == ["osm:node:9"]
    assert diff.still_missing_keys == ["osm:node:8"]
    assert diff.counts == {"added": 1, "changed": 1, "missing": 2, "reappeared": 1, "still_missing": 1}


def test_node_and_way_with_the_same_id_never_collide():
    diff = compute_diff({"osm:node:5": 1}, set(), {"osm:node:5": 1, "osm:way:5": 1})
    assert diff.added_keys == ["osm:way:5"] and diff.missing_keys == []
