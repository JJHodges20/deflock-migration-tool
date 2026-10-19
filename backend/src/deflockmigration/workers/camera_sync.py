"""Camera-sync worker: one scheduler for the fixed Denver region.

`--once` runs a single sync (setup job or manual refresh) and exits non-zero on failure or quarantine.
Without `--once` it loops every `refresh_interval_hours` from the region config while the container runs.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

import datetime as dt

from deflockmigration.core.clock import utc_now
from deflockmigration.core.config_loader import load_app_config
from deflockmigration.core.logging import configure_logging
from deflockmigration.core.settings import Settings
from deflockmigration.data_sources.overpass import OverpassClient
from deflockmigration.ingestion.sync import run_sync
from deflockmigration.storage.db import make_engine, make_session_factory
from deflockmigration.storage.repositories import SnapshotRepository

log = logging.getLogger("deflockmigration.worker")


def seconds_until_due(last_downloaded_at: dt.datetime | None, interval_seconds: float, now: dt.datetime) -> float:
    """Politeness on restart: if the active snapshot is younger than the interval, wait for the remainder
    instead of querying the public instance again on every `docker compose up`."""
    if last_downloaded_at is None:
        return 0.0
    age = (now - last_downloaded_at).total_seconds()
    return max(0.0, interval_seconds - age)


def _interruptible_sleep(seconds: float, stop: dict) -> None:
    waited = 0.0
    while waited < seconds and not stop["flag"]:
        step = min(30.0, seconds - waited)
        time.sleep(step)
        waited += step


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DeFlockMigration camera inventory sync")
    parser.add_argument("--once", action="store_true", help="run one sync and exit")
    parser.add_argument("--trigger", default=None, help="scheduled | manual | setup")
    parser.add_argument("--interval-hours", type=float, default=None, help="override the region refresh interval")
    parser.add_argument("--force", action="store_true", help="manual refresh: ignore the shared cooldown and query the public instance now")
    args = parser.parse_args(argv)

    settings = Settings()
    configure_logging(settings.log_level)
    if not settings.database_url:
        log.error("DEFLOCK_DATABASE_URL is required for the camera sync worker")
        return 2
    config = load_app_config(settings)
    session_factory = make_session_factory(make_engine(settings.database_url))
    source = config.providers.camera_source
    client = OverpassClient(
        config.region.camera_source.endpoint,
        user_agent=settings.user_agent,
        timeout_seconds=source.timeout_seconds,
        pause_after_rate_limit_seconds=max(source.pause_after_rate_limit_seconds, config.region.camera_source.min_pause_after_429_seconds),
        max_attempts=source.max_attempts,
        backoff_seconds=source.backoff_seconds,
    )
    trigger = args.trigger or ("setup" if args.once else "scheduled")
    interval_s = (args.interval_hours or config.region.camera_source.refresh_interval_hours) * 3600

    stop = {"flag": False}

    def _handle(signum, frame):  # noqa: ARG001
        stop["flag"] = True
        log.info("stop requested (signal %s)", signum)

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)

    try:
        if not args.once:
            with session_factory() as session:
                active = SnapshotRepository(session).get_active(config.region.region_id)
            delay = seconds_until_due(active.downloaded_at_end if active else None, interval_s, utc_now())
            if delay > 0:
                log.info("active snapshot is fresh; next scheduled sync in %.0f minutes", delay / 60)
                _interruptible_sleep(delay, stop)
                if stop["flag"]:
                    return 0
        while True:
            outcome = run_sync(config, session_factory, client, snapshot_dir=settings.snapshot_dir, trigger=trigger, force=args.force and args.once)
            log.info("sync outcome=%s snapshot=%s %s", outcome.status, outcome.snapshot_id, outcome.message)
            if args.once:
                return 0 if outcome.status in ("succeeded", "skipped") else 1
            trigger = "scheduled"
            _interruptible_sleep(interval_s, stop)
            if stop["flag"]:
                return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
