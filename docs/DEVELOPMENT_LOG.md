# Development log

Newest first. Every entry records what was executed, what was only inspected, and what remains unverified.

## 2026-10-16 / 2026-10-19 - M2: public camera inventory

### Built

- **Envelope check:** every record carries `in_envelope`; the snapshot counts ALPR records inside the camera-data envelope separately (`in_envelope_alpr_count`). Only those are assessed against routes later.
- **Vanished records:** a record present in the previous active snapshot but absent from a later successful same-scope query is carried into the new snapshot as `lifecycle_state = no_longer_mapped` with `missing_since` and `last_seen_snapshot_id`, counted separately, shown faded on the map, and dropped after `retain_missing_hours` (72 h). Lifecycle prefixes mapped by contributors (`removed:`, `was:`, `destroyed:`, `disused:`) stay distinct from this state. The `drop` policy variant is supported and tested.
- **Diff history:** each sync stores a `snapshot_diffs` row (added, changed, missing, reappeared, carried, expired counts plus bounded key lists); sync jobs keep the summary counts; Data Health shows the active snapshot's diff and the five most recent syncs.
- **Record history:** `GET /api/v1/cameras/record?source_key=osm:node:<id>` returns the current record and its versions across retained snapshots, plus the OpenStreetMap link, so a changed recommendation can be explained.
- **Retention:** after a successful sync the newest 30 superseded and 10 quarantined/rejected snapshots are kept; older ones, their records, diffs, and raw files are pruned.
- **Quarantine review:** `deflock-snapshot-review list|accept|reject` (wrapped by `scripts/review_snapshot.ps1`) records the operator decision and a note; accept promotes atomically, reject keeps the last good snapshot; both write a `review` sync-job row. Data Health lists pending reviews.
- **Overlay:** legend with per-view counts (Flock-tagged, other manufacturer, unknown, no longer mapped, outside the assessed area), distinct styling for uncertain and out-of-envelope records, popup with mapped status, assessed-area flag, and a link to the source record.
- **Schema:** migration 0002; `docs/DATA_DICTIONARY.md` documents every table and column.

### Verification (2026-10-19)

- Migration 0002 applied to the live database with `docker compose --profile setup run --rm db-migrate`; the api and worker were recreated on the rebuilt image.
- Backend in the container: 66 passed, including the integration matrix (`test_inventory_lifecycle`, `test_drop_policy_discards_vanished_records_immediately`) against the `deflock_test` PostGIS database.
- Frontend: type check clean; 17 Vitest tests passed (legend summary and Data Health panel tests added).
- Browser smoke (Playwright, three viewports): 9 passed.
- `scripts/smoke_test.ps1 -CheckRestart`: passed; the snapshot and graph survived the restart.
- Live inventory: the scheduled sync on the restart absorbed three days of real OpenStreetMap activity (14 added, 3 changed, 6 no longer present versus the 2026-10-16 snapshot). A manual sync then published `ovp-denver-20261019T144621Z-37c4cf74`: 1,548 ALPR records, 1,285 inside the envelope, 1,270 Flock, 155 manufacturer unknown, zero diff against the snapshot taken four minutes earlier; 6 snapshots retained. `GET /api/v1/cameras/record` returned a Flock record with 6 historical versions across the retained snapshots and its OpenStreetMap link; the overlay features carry `uncertain`, `in_envelope`, and `source_url`.
- Not demonstrated live: a carried "no longer mapped" record (no record vanished between the two M2-era syncs). The carry-over, reappearance, retention expiry, quarantine review, pruning, and concurrent-sync behaviours are proven by the integration matrix with mocked source responses.

### Gate check (roadmap M2)

- A real dated Denver-region snapshot loads and refreshes without per-route provider calls: yes (scheduled, manual, and setup triggers; routes never touch the source).
- Source errors preserve the last known good snapshot: yes (integration test; real 502 retries observed in the logs).
- Counts refer to mapped records only: yes (API `counts_meaning` fields, legend and Data Health wording, data dictionary).

### Observations

- Record counts in the UI and API distinguish "present in the source" (`alpr_count`), "inside the assessed area" (`in_envelope_alpr_count`), and "no longer mapped, retained as uncertain" (`no_longer_mapped_count`). None of them is a count of physical devices.
- The sync's per-record carry-over copies the previous row verbatim (tags, manufacturer, direction) so that an uncertain record keeps its evidence; only lifecycle, warnings, and the missing timestamps change.
- Migrations are never applied automatically at container start; `docker compose --profile setup run --rm db-migrate` is the documented step after a code update.

## 2026-10-15 / 2026-10-16 - M1: repository, contracts, Docker Compose stack, application shell

### Built

- Compose stack (`compose.yaml`): edge (nginx 1.28), web (Next.js 16.4.2 on Node 22), api (FastAPI on Python 3.13), camera-sync worker, db (PostGIS 16-3.4), valhalla (3.9.1), geocoder (Nominatim 5.3.2); setup profile jobs `db-migrate`, `osm-download`, `graph-build`, `basemap-extract`, `basemap-assets`, `camera-sync-once`; test profile `api-tests`, `web-tests`, `e2e`. Named volumes `pgdata`, `valhalla_tiles`, `osm_extracts`, `basemap`, `geocoder_db`, `camera_snapshots`. Only the edge is published, on 127.0.0.1:3000.
- Backend package `deflockmigration` with validated YAML configuration, redacted logging, five endpoints, Valhalla and self-hosted Nominatim adapters, policy-aware Overpass client, decision-0001 normalizer, Alembic migration 0001, atomic snapshot promotion with quarantine, scheduler worker, and three setup jobs.
- Frontend planner shell with coordinate entry, map pins, swap, preferences, route cards, engine directions, camera overlay, Data Health panel, disclaimers, and a map-failure fallback.
- Operator scripts `bootstrap.ps1`, `import_region.ps1`, `sync_cameras.ps1`, `smoke_test.ps1`; docs `USER_GUIDE.md`, `TEST_PLAN.md`, `PRIVACY_AND_DATA_FLOW.md`, `PROJECT_CONTEXT.md`, `IMPLEMENTATION_PLAN.md`; `CLAUDE.md`; CI workflow (not yet executed anywhere, no remote exists).

### Measured on the pilot machine (Docker Desktop, 8.29 GB allocated)

| Item | Result |
|---|---|
| Backend image | 469 MB; dependency layer cached across rebuilds |
| Web image | 340 MB (standalone Next.js output); multi-stage build about 1.5 minutes with cached dependencies |
| `db-migrate` | 85 s including the first PostGIS initialization |
| `osm-download` | 46 s job (27 s transfer of 384.8 MB, MD5 verified) |
| `graph-build` | 296 s total: time zones 35 s, admins 4 s, tiles 253 s, extract 1 s (slower than the M0 spike's 125 s because the web image was building at the same time) |
| `basemap-extract` + `basemap-assets` | 90.3 MB archive plus 1,046 asset files; under 1 minute together |
| `camera-sync-once` | 87 s; snapshot `ovp-denver-20261015T232105Z-ccc0b665`: 1,593 elements, 1,540 ALPR records, 1,263 Flock, 157 unknown manufacturer |
| `docker compose up -d` | all long-running services healthy in 42 s (db already running); geocoder import started in the background |
| Routing request through edge -> api -> valhalla | Union Station to Denver Zoo: 3 candidates evaluated, Standard = alternate-2 (618 s, 6.4 km, 9 maneuvers), camera counts null, coverage `not_assessed`, snapshot id attached |
| Camera overlay query (downtown bbox) | 26 records from the active snapshot |
| Basemap range request | HTTP 206, `Content-Range: bytes 0-1023/90280588`, fonts and sprite JSON served |

### Tests

- Backend on the host: 57 passed, 1 skipped (integration test without a database).
- Backend in the container (`api-tests`, including the PostGIS integration test against `deflock_test`): 58 passed.
- Frontend (`web-tests`): type check clean; 14 Vitest tests passed (format helpers, planner reducer, Planner shell with mocked fetch).
- Browser smoke (`e2e`, Playwright 1.64.1 in its container against `http://edge:3000`): 9 passed at 390, 768, and 1440 px: a coordinate-to-coordinate plan through edge -> api -> valhalla with directions and null camera counts, the outside-pilot-area state, and the Data Health panel.
- Compose smoke (`scripts/smoke_test.ps1 -CheckRestart`): all services healthy; data health, routing request, basemap range support, and fonts verified; after `docker compose restart` of db, valhalla, api, web, edge, and camera-sync, the same snapshot id and graph build date were still served.
- Clean-checkout bootstrap (2026-10-16, main stack paused, copy of the tracked tree in a scratch folder, `COMPOSE_PROJECT_NAME=deflockclean`, port 3001, `-SkipGeocoder`): `scripts\bootstrap.ps1` completed in **388 s** and its own smoke test passed. Step timings: Docker check, image build (fully cached), migrations on a fresh database, and extract download 54 s combined; routing graph 207 s (build 175 s inside the container); basemap extract 16 s; fonts and sprites 6 s; first camera snapshot 61 s; `docker compose up -d` 8 s; smoke test 36 s. The clean project was then removed with `down -v` and the main stack restarted; its snapshot, graph, and geocoder data were intact and address search was available.
- Address search through the edge after the geocoder import (16 min 13 s from "Creating database" to the completion marker): Union Station, Denver Zoo, and 1437 Bannock St resolved to the expected places inside the service boundary; a nonexistent street returned no candidates.

### Observations and decisions made during M1

- The worker queried Overpass immediately on every start even when a minutes-old snapshot was active (two snapshots were created two minutes apart during bring-up). Added a politeness rule: on start, if the active snapshot is younger than the refresh interval, wait for the remainder (`seconds_until_due`, unit-tested). Manual and setup runs (`--once`) are unaffected.
- The worker service inherits the API image's HTTP healthcheck, which it can never satisfy; the healthcheck is disabled for that service in Compose.
- Overpass returned HTTP 502 on the first attempt of the second sync as well; the client's retry handled it. 502s from the public instance are routine, not exceptional.
- maplibre-gl 6 ships no default export; the map uses named imports. `@types/geojson` is a direct dev dependency so the API types compile without relying on a transitive package.
- Nominatim's image entrypoint `chown`s `/nominatim`; the extract is mounted at `/pbf` to keep it read-only.
- The first browser-test run failed with HTTP 502 from the edge: nginx had resolved the `api` service name once at startup, and recreating the API container gave it a new address. The edge now uses Docker's embedded DNS resolver with per-request variables, so recreating `api` or `web` needs no edge restart (verified by recreating `api` and requesting through the edge immediately afterwards).
- The smoke script's basemap check first looked for `Accept-Ranges` on a 206 response; nginx sends that header only on full responses. The check now verifies `Content-Range` on the partial response. The script also reads `DEFLOCK_PORT` from `.env` instead of assuming 3000.
- `bootstrap.ps1 -SkipGeocoder` originally still started the geocoder through the final `docker compose up -d`; it now scales the geocoder to zero for that run only.
- Docker Desktop was shut down while the geocoder's first import was running. On the next engine start every service came back by itself within 20 s (`restart: unless-stopped`), the database, graph, basemap, and camera snapshots were intact, and the geocoder restarted its import from scratch because no completion marker existed yet. Once the marker exists, later starts serve immediately. The user guide now says so.

### Public-source calls made during M1

Geofabrik: 1 extract download (plus MD5). Protomaps: 1 regional extract (50 range requests) and 1 GitHub archive for fonts/sprites. Overpass: 2 fixed-region queries (setup job and the worker's first start). Registries: image pulls for nginx, postgis, node, python, playwright. No call carried a trip or an address.

### Known limitations after M1

- Only the Standard route is returned; preferences and scope are recorded but camera assessment does not exist yet (M4/M5). Route cards say "Not assessed in this version".
- Address search depends on the geocoder import having finished; the UI reports the state explicitly.
- The camera-sync worker does not yet review quarantined snapshots or record lifecycle history (M2/M7).
- The CI workflow has not run (no remote).
- The clean-checkout bootstrap test skipped the geocoder import to keep the run bounded; the geocoder path (import, restart behaviour, address search) was exercised on the primary stack.
- The clean-checkout test ran from a copy of the tracked working tree rather than a `git clone`, because M1 was not yet committed at that point; the copy contained exactly the files that are committed in the M1 commit.
