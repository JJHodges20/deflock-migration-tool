"""Operator CLI: list, accept, or reject quarantined camera snapshots.

Examples (inside the Compose stack):
  docker compose run --rm camera-sync deflock-snapshot-review list
  docker compose run --rm camera-sync deflock-snapshot-review accept <snapshot_id> --note "corroborated against OSM history"
  docker compose run --rm camera-sync deflock-snapshot-review reject <snapshot_id> --note "upstream outage"
"""

from __future__ import annotations

import argparse
import sys

from deflockmigration.application.review import ReviewError, accept_snapshot, list_snapshots, reject_snapshot, rollback_snapshot
from deflockmigration.core.config_loader import load_app_config
from deflockmigration.core.logging import configure_logging
from deflockmigration.core.settings import Settings
from deflockmigration.storage.db import make_engine, make_session_factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review quarantined DeFlockMigration camera snapshots")
    sub = parser.add_subparsers(dest="command", required=True)
    lst = sub.add_parser("list", help="list recent snapshots (quarantined first)")
    lst.add_argument("--all", action="store_true", help="include active, superseded, and rejected snapshots")
    acc = sub.add_parser("accept", help="promote a quarantined snapshot after corroboration")
    acc.add_argument("snapshot_id")
    acc.add_argument("--note", required=True)
    rej = sub.add_parser("reject", help="mark a quarantined snapshot as rejected")
    rej.add_argument("snapshot_id")
    rej.add_argument("--note", required=True)
    rb = sub.add_parser("rollback", help="make a previously active snapshot active again (default: the one the active snapshot replaced)")
    rb.add_argument("snapshot_id", nargs="?", default=None)
    rb.add_argument("--note", required=True)
    args = parser.parse_args(argv)

    settings = Settings()
    configure_logging(settings.log_level)
    if not settings.database_url:
        print("DEFLOCK_DATABASE_URL is required", file=sys.stderr)
        return 2
    config = load_app_config(settings)
    region_id = config.region.region_id
    session_factory = make_session_factory(make_engine(settings.database_url))
    try:
        if args.command == "list":
            items = list_snapshots(session_factory, region_id, states=None if args.all else ["quarantined", "active"], limit=30)
            if not items:
                print("no snapshots")
            for item in items:
                reason = f" reason: {item.quarantine_reason}" if item.quarantine_reason else ""
                note = f" note: {item.review_note}" if item.review_note else ""
                print(f"{item.promotion_state:11} {item.snapshot_id} created {item.created_at} elements={item.element_count} alpr={item.alpr_count}{reason}{note}")
        elif args.command == "accept":
            print(accept_snapshot(session_factory, region_id, args.snapshot_id, args.note))
        elif args.command == "rollback":
            print(rollback_snapshot(session_factory, region_id, args.snapshot_id, args.note))
        else:
            print(reject_snapshot(session_factory, region_id, args.snapshot_id, args.note))
    except ReviewError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
