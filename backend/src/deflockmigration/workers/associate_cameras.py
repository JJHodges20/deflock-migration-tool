"""Setup/maintenance job: precompute nearest-road candidates for every in-envelope ALPR record of the active
snapshot on the current routing-graph version, so route assessments rarely need live locate calls.
Also prunes cache rows that belong to other graph versions (associations are graph-version specific).

  docker compose run --rm camera-sync deflock-associate-cameras
"""

from __future__ import annotations

import argparse
import sys
import time

from sqlalchemy import text

from deflockmigration.core.clock import utc_now
from deflockmigration.core.config_loader import load_app_config
from deflockmigration.core.logging import configure_logging
from deflockmigration.core.settings import Settings
from deflockmigration.routing.road_locator import ValhallaRoadLocator
from deflockmigration.routing.valhalla import ValhallaProvider
from deflockmigration.storage.association_cache import AssociationCache
from deflockmigration.storage.db import make_engine, make_session_factory
from deflockmigration.storage.repositories import SnapshotRepository


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Precompute camera road associations for the active snapshot")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many new associations (0 = all)")
    parser.add_argument("--no-prune", action="store_true", help="keep cache rows of other graph versions")
    parser.add_argument("--recompute", action="store_true", help="drop the cached rows of the current graph and radius first, then recompute all of them")
    args = parser.parse_args(argv)

    settings = Settings()
    configure_logging(settings.log_level)
    if not settings.database_url:
        print("DEFLOCK_DATABASE_URL is required", file=sys.stderr)
        return 2
    config = load_app_config(settings)
    radius = int(config.data_quality.proximity.candidate_radius_m)
    session_factory = make_session_factory(make_engine(settings.database_url))
    routing = ValhallaProvider(settings.valhalla_url)
    status = routing.status()
    if not status.available or not status.tileset_last_modified:
        print("routing engine unavailable; cannot associate", file=sys.stderr)
        return 1
    graph_version = f"{config.region.routing_graph.id}@{status.tileset_last_modified}"
    locator = ValhallaRoadLocator(settings.valhalla_url)

    with session_factory() as session:
        snapshot = SnapshotRepository(session).get_active(config.region.region_id)
        if snapshot is None:
            print("no active camera snapshot", file=sys.stderr)
            return 1
        rows = session.execute(
            text("SELECT source_key, ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lon FROM camera_records WHERE snapshot_id = :sid AND is_alpr = TRUE AND in_envelope = TRUE AND lifecycle_state <> 'no_longer_mapped' ORDER BY source_key"),
            {"sid": snapshot.snapshot_id},
        ).mappings().all()
        cache = AssociationCache(session)
        cleared = cache.clear_for(graph_version, radius) if args.recompute else 0
        existing = cache.get_many([r["source_key"] for r in rows], graph_version, radius)
        pruned = 0 if args.no_prune else cache.prune_other_graphs(graph_version)
        session.commit()

    todo = [r for r in rows if r["source_key"] not in existing]
    if args.limit:
        todo = todo[: args.limit]
    print(f"graph {graph_version}: {len(rows)} in-envelope ALPR records, {len(existing)} cached, {len(todo)} to compute, {cleared} rows cleared for recompute, {pruned} rows of other graphs pruned")
    started = time.perf_counter()
    done = failed = 0
    for row in todo:
        try:
            candidates = locator.locate(row["lat"], row["lon"], radius)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"locate failed for a record: {type(exc).__name__}", file=sys.stderr)
            continue
        with session_factory() as session:
            AssociationCache(session).put(row["source_key"], graph_version, radius, candidates, utc_now())
            session.commit()
        done += 1
        if done % 200 == 0:
            print(f"  {done}/{len(todo)} associated ({time.perf_counter() - started:.0f} s)")
    print(f"associated {done} records, {failed} failures, {time.perf_counter() - started:.1f} s")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
