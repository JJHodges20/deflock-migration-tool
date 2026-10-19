# Operations runbook (Denver pilot, v1.0 release candidate)

Everything here was executed on the pilot machine (Windows 11, Docker Desktop with about 8.3 GB allocated) before it was written down. Every command runs inside containers; nothing is installed on the host. No command here touches a person's trip: the only data this system keeps is public OpenStreetMap camera records, public road data, and job history.

## 1. Everyday operation

| Need | Command |
|---|---|
| Start everything | `docker compose up` (or `-d` to detach) |
| Stop everything, keep all data | `docker compose down` (volumes stay; never use `-v` casually, it deletes the graph, the geocoder import, and the camera history) |
| Check the stack end to end, including a restart | `powershell -ExecutionPolicy Bypass -File scripts\smoke_test.ps1 -CheckRestart` |
| See the operating state without a terminal | the **Data health** panel in the app: snapshot, freshness, scheduler, source policy, snapshot history, graph, geocoder, service metrics |

## 2. The single scheduler

- One `camera-sync` container is the only scheduler. It queries the public Overpass instance for the fixed Denver envelope every 6 hours **while the stack is up**. No sync runs when the stack is down.
- On start it reads the active snapshot's download time and waits for the remainder of the interval instead of querying again (`seconds_until_due`), so repeated `docker compose up` cycles do not hammer the shared instance. A stack that was down for a day catches up with **one** query.
- Concurrent runs coalesce: a region lock lets exactly one sync run; a second runner reports "skipped" and the running sync's result applies.
- Data Health shows the next due time, whether the scheduler is overdue (interval plus a one-hour grace), and the last trigger. "Overdue" with the stack up means the worker container is not running: `docker compose ps camera-sync`, `docker compose logs camera-sync`.

Provider policy as implemented: one request at a time, an identifying User-Agent, a 180 s query timeout, a 30 s pause after HTTP 429/406, bounded retries with backoff on 502/503/504, detection of HTML challenge pages and error remarks, no endpoint rotation. Before any public rollout the ingestion must move to the Geofabrik extract plus diffs (decision 0001 D7).

## 3. Manual refresh and its cooldown

```powershell
powershell -ExecutionPolicy Bypass -File scripts\sync_cameras.ps1          # respects the shared 30 min cooldown
powershell -ExecutionPolicy Bypass -File scripts\sync_cameras.ps1 -Force   # queries now anyway
```

A refresh within 30 minutes of the active snapshot's download is skipped and recorded as a `skipped` sync job (visible in Data Health), so repeated clicks by several operators cost the public instance nothing. `-Force` is for a known upstream change you want to pick up immediately. The scheduled worker is never subject to the cooldown.

## 4. What a sync can do, and what it never does

| Outcome | What happened | What stays active |
|---|---|---|
| `succeeded` | validated snapshot promoted atomically; diff stored; old snapshots pruned by the retention policy | the new snapshot |
| `succeeded` (identical) | the source answered with the same content as a stored snapshot | unchanged |
| `quarantined` | empty result or a drop of more than 50 % in ALPR records; review required | the last good snapshot |
| `failed` | outage, rate limit after retries, HTML page, malformed or truncated JSON, error remark | the last good snapshot |
| `skipped` | region lock held by another run, or manual cooldown | unchanged |

A failure never overwrites good data: the raw file is written first, rows are inserted under the new snapshot id, and promotion is the last step of one transaction. The M2 and M7 integration matrices prove outage, rate limit, truncated response, concurrent runs, and quarantine paths against a real PostGIS database.

## 5. Reviewing a quarantined snapshot

```powershell
powershell -ExecutionPolicy Bypass -File scripts\review_snapshot.ps1 list
powershell -ExecutionPolicy Bypass -File scripts\review_snapshot.ps1 accept <snapshot_id> -Note "what you corroborated"
powershell -ExecutionPolicy Bypass -File scripts\review_snapshot.ps1 reject <snapshot_id> -Note "why"
```

Accepting promotes the snapshot; rejecting keeps the last good one. Both actions are recorded as `review` jobs with the note.

## 6. Rolling a snapshot back (no deletion)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\review_snapshot.ps1 rollback -Note "why"                 # back to the snapshot the active one replaced
powershell -ExecutionPolicy Bypass -File scripts\review_snapshot.ps1 rollback <snapshot_id> -Note "why"   # back to a specific retained snapshot
```

Only a previously active (superseded) snapshot with retained records can be restored. The replaced snapshot stays retained as superseded, so a rollback can itself be undone with another rollback. Nothing is deleted and the database is not touched beyond the promotion flags; the retention policy (30 superseded snapshots) bounds how far back you can go. A `rollback` job with the note appears in Data Health, and results already on someone's screen are marked outdated rather than changed.

## 7. Road data: rebuild and rollback

```powershell
powershell -ExecutionPolicy Bypass -File scripts\import_region.ps1          # download the latest extract, rebuild, validate, refresh associations
powershell -ExecutionPolicy Bypass -File scripts\import_region.ps1 -Force   # rebuild even if the extract is unchanged
powershell -ExecutionPolicy Bypass -File scripts\rollback_graph.ps1         # put the previous graph back
```

The rebuild runs inside the pinned Valhalla container into a staging directory; the active graph is replaced only after all stages succeed and tiles exist. The graph being replaced is kept in the volume as the last-good graph (`previous/`), so a rollback needs no download or rebuild. A running routing service keeps serving the files it already opened until it is restarted, so routes computed during a promotion are unaffected. After the restart the script validates the new graph through the running application (Data Health reports it and a reviewed public-landmark route succeeds) and refreshes the camera road-association cache for the new graph version; if validation fails it tells you to roll back. Measured on the pilot machine: Colorado graph build about 2.5 minutes with about 3 GB peak memory; the volume holds about 1.1 GB per graph, so keeping the previous graph roughly doubles it. The recommended cadence is weekly; do not run a rebuild while the geocoder is importing.

## 8. Version pinning and freshness

- Every route result carries the camera snapshot id, the source timestamp, the download time, the road-graph version, and the counting and search method versions. A request is assessed against the snapshot that was active when it started, even if a sync promotes a newer one meanwhile (M7 integration test).
- The planner polls Data Health every five minutes and when the tab becomes visible again. When a newer snapshot or a rebuilt graph appears, the result on screen is marked **outdated** and stays as computed; the person plans again to use the current data.
- Freshness policy (`configs/data_quality.yaml`): snapshot stale after 48 h; no-longer-mapped records retained as uncertain for 72 h; manual cooldown 30 min; scheduler overdue after the interval plus 1 h.

## 9. Metrics without trip data

`GET /api/v1/health/metrics` (also summarised in Data Health) reports, per declared route template, request counts, rejected (4xx) and failed (5xx) counts, and p50/p95/max latencies from a bounded in-memory reservoir; plan outcomes by search status, options returned, routing calls used, and plan latencies; API process memory; and public-data storage sizes (database bytes, raw snapshot bytes, row counts). Nothing in it is derived from a trip: no coordinates, addresses, shapes, bodies, or query strings are recorded, and the contract and browser tests assert their absence. The numbers live in the API process and vanish with it.

## 10. Disk and memory on the pilot machine (measured 2026-10-19)

| Volume | Holds | Size |
|---|---|---|
| `geocoder_db` | self-hosted Nominatim import of Colorado | 9.5 GB (import about 17 min, 5.2 GiB peak) |
| `valhalla_tiles` | routing graph (tiles, tar, databases) | 1.1 GB per graph |
| `basemap` | Protomaps extract, fonts, sprites | 102 MB |
| `camera_snapshots` | raw Overpass responses (about 1 MB each, pruned with retention) | 4.7 MB |
| `osm_extracts` | Geofabrik Colorado extract | about 385 MB |
| `pgdata` | PostGIS: snapshots, records, diffs, associations, jobs | tens of MB |

Memory limits in `compose.yaml`: database 1 GB, routing 2 GB, geocoder 6 GB, graph build 6 GB. The graph build and the geocoder import must not run at the same time.

## 11. Backups and restore

Only public data and job history exist, so a backup is optional. `docker compose exec db pg_dump -U deflock deflock > backup.sql` captures the inventory and history; the graph and the geocoder import are rebuildable from public downloads with `scripts\import_region.ps1` and a geocoder restart. Never back up or copy anything from a browser: there is nothing there.

## 12. Upgrading the code

1. `docker compose build`
2. `docker compose --profile setup run --rm db-migrate` (migrations are never applied silently)
3. `docker compose up -d`
4. `powershell -ExecutionPolicy Bypass -File scripts\smoke_test.ps1 -CheckRestart`

## 13. Release audit

`powershell -ExecutionPolicy Bypass -File scripts\audit.ps1 -Check all` runs the paid-key, egress, log, and restore checks against the running stack and prints the evidence; `-Check perf` stops and starts the stack to measure the cold start and then measures warm plan latencies. The network layout (an internal network for everything except the sync worker, the setup jobs, and the edge) is described in `docs/PRIVACY_AND_DATA_FLOW.md`; the audit results for this release are in `docs/AUDIT.md`.

## 14. If something goes wrong

| Symptom | Check | Action |
|---|---|---|
| Data Health: scheduler overdue | `docker compose ps camera-sync` | start the stack; or `scripts\sync_cameras.ps1` |
| Data Health: last failure `failed` with HTTP 429 | the shared instance is rate limiting | wait; the worker already paused 30 s and will retry at the next interval; do not add instances |
| Data Health: snapshot quarantined | `scripts\review_snapshot.ps1 list` | corroborate, then accept or reject |
| Route engine unavailable | `docker compose logs valhalla` | the graph may still be loading; after a failed rebuild run `scripts\rollback_graph.ps1` |
| Address search unavailable | `docker compose logs -f geocoder` | the first import takes about 17 minutes; if it was interrupted it starts over. Right after a restart the first searches can take several seconds while the database cache warms; the health check runs a real search every 30 s, and the API waits up to 15 s |
| Results look outdated | the notice names the newer snapshot or graph | plan again |
