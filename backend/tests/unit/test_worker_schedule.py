from __future__ import annotations

import datetime as dt

from deflockmigration.workers.camera_sync import seconds_until_due

NOW = dt.datetime(2026, 10, 15, 12, 0, tzinfo=dt.UTC)


def test_no_snapshot_means_sync_now():
    assert seconds_until_due(None, 6 * 3600, NOW) == 0.0


def test_fresh_snapshot_waits_for_the_remainder_of_the_interval():
    two_hours_ago = NOW - dt.timedelta(hours=2)
    assert seconds_until_due(two_hours_ago, 6 * 3600, NOW) == 4 * 3600


def test_old_snapshot_is_due_immediately():
    yesterday = NOW - dt.timedelta(days=1)
    assert seconds_until_due(yesterday, 6 * 3600, NOW) == 0.0
