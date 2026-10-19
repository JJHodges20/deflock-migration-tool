"""Data Health's scheduler block derives the next sync the same way the worker does (M7 gate: scheduled sync only
runs while the local service runs; reopening catches up politely)."""

from __future__ import annotations

import datetime as dt

from deflockmigration.application.data_health import schedule_view
from deflockmigration.core.clock import isoformat_z

NOW = dt.datetime(2026, 10, 19, 12, 0, tzinfo=dt.UTC)
COMMON = dict(overdue_grace_hours=1.0, cooldown_minutes=30, last_trigger="scheduled")


def test_on_schedule_with_cooldown_elapsed():
    fresh = schedule_view(NOW - dt.timedelta(hours=1), 6, NOW, **COMMON)
    assert fresh["state"] == "on schedule" and fresh["overdue"] is False
    assert fresh["due_in_seconds"] == 5 * 3600 and fresh["next_due_at"] == isoformat_z(NOW + dt.timedelta(hours=5))
    assert fresh["cooldown_remaining_seconds"] == 0 and fresh["runs_only_while_stack_is_up"] is True
    assert fresh["interval_hours"] == 6 and fresh["manual_refresh_cooldown_minutes"] == 30 and fresh["last_trigger"] == "scheduled"


def test_cooldown_remaining_right_after_a_download():
    recent = schedule_view(NOW - dt.timedelta(minutes=10), 6, NOW, **COMMON)
    assert recent["cooldown_remaining_seconds"] == 20 * 60 and recent["state"] == "on schedule"


def test_due_within_grace_then_overdue():
    due = schedule_view(NOW - dt.timedelta(hours=6, minutes=30), 6, NOW, **COMMON)
    assert due["state"].startswith("due now") and due["overdue"] is False and due["due_in_seconds"] == 0
    overdue = schedule_view(NOW - dt.timedelta(hours=8), 6, NOW, **COMMON)
    assert overdue["overdue"] is True and overdue["state"].startswith("overdue")


def test_no_snapshot_yet_means_sync_as_soon_as_the_worker_runs():
    none = schedule_view(None, 6, NOW, **COMMON)
    assert none["overdue"] is True and none["next_due_at"] is None and "no snapshot yet" in none["state"]
