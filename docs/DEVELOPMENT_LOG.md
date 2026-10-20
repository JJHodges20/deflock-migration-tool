# Development log

Newest first. Every entry records what was executed, what was only inspected, and what remains unverified.

## 2026-10-19 / 2026-10-20 - M10: camera inventory from the Geofabrik extract with daily change files

### Built

- **Decision 0004:** the Colorado configuration's camera source is the Geofabrik Colorado extract kept current with the publisher's daily change files; the public Overpass instance is no longer queried for Colorado (the Denver pilot configuration keeps the bounded query, and the Colorado query file stays on disk as a documented fallback).
- **Extract reader (`data_sources/extract_elements.py`):** the Overpass query's tag filters applied to every node, way, and relation of the extract with pyosmium (a key filter evaluated in C++, then the regex checks in Python; a second pass only when ways or relations matched, to collect their node points). Output elements have the Overpass `out meta geom` shape minus contributor names and ids, so the normalizer, the diff, the quality rules, quarantine, promotion, retention, and the review tools are untouched.
- **Source adapter (`data_sources/osm_extract.py`):** seeds the worker's copy from the routing graph's extract (no second download), reads the Osmosis replication header, asks the change-file service for its state, applies new change files with pyosmium's replication client in steps of at most 256 MB and replaces the file atomically, and hands the filtered elements to the sync. Politeness as disclosed: identifying User-Agent, one request at a time, 30 s pause after HTTP 429/503, three attempts with backoff, no retries inside the HTTP library, no endpoint rotation. A missing change file inside the publisher's retention window is treated as transient; beyond it the copy is re-seeded from a newer graph extract or one fresh extract is downloaded (checksum verified), at most once per run.
- **Sync pipeline:** `run_sync` takes a camera source (`OverpassSource` or `ExtractSource`; a bare Overpass client still works); snapshot ids carry the source prefix (`ext-` or `ovp-`), the identical-snapshot check hashes the data part only, and a new `source_details` column (migration 0004) keeps the replication state, the extraction statistics, and the filter version. Carried "no longer mapped" rows are judged against the current envelope.
- **Configuration:** `camera_source.adapter: geofabrik_extract` with an `extract` block (url, file, replication_url, outline_file, coverage note) and a 24 h interval in `configs/regions/colorado.yaml`; the replication client's limits in `configs/providers.yaml` (`camera_extract`); `DEFLOCK_CAMERA_EXTRACT_DIR` and `DEFLOCK_GRAPH_EXTRACT_PATH` in the settings; the worker chooses the source from the region configuration.
- **Camera-data envelope v2 (`colorado-envelope-v2-extract`):** the publisher's outline (`colorado.poly`, 15 vertices) follows the state line within about 300 m, so the extract holds no standalone records in neighbouring states. The 20 km envelope v1 would have treated that strip as covered; v2 is v1 limited to the outline with a 500 m metric margin (271,739.7 km², 61 vertices, built in PostGIS, contains the service boundary). Routes that leave the state are assessed only for the part inside and are not ranked for privacy.
- **Runtime:** the backend image installs pyosmium 4.3.2 (with `requests`) and the `libexpat1` library; the worker mounts a new `camera_extracts` volume for its copy and the `osm_extracts` volume read-only as the seed; its memory limit is 1 GB.
- **Disclosure:** Data Health's `camera_source` carries the extract block and the coverage note, `provider_policy` the replication client's limits, and the snapshot its source and `source_details`; the Data Health panel shows the camera source with the change-file sequence; the browser smoke spec accepts either snapshot prefix.
- **Documents:** decision 0004; data source register sections 1 and 2; attribution; privacy flows; operations runbook (scheduler, policy, outcomes, disk, troubleshooting for the extract source); user guide; test plan; implementation plan; project context; audit note; README; `scripts\sync_cameras.ps1` wording.

### Verification (2026-10-19 to 2026-10-20)

- Probes on the pilot machine before building: the extract in the volume carries the replication header (`colorado-updates`, sequence 4945, 2026-10-18T20:25:06Z); one key-filtered pass over the 385 MB file 4.4 s with 82,781 objects reaching Python and 2,875 nodes plus 1 way matching, the node-location pass 0.8 s, 192 MB resident; applying three real change files (4943 to 4945) and rewriting the file with pyosmium 13 s at 309 MB resident.
- Backend in the container: 207 passed in 19 s after three rounds of fixes (a temporary file name pyosmium could not type, two test expectations that misread the normalizer's evidence rules, a layer-boundary rule that moved the extract reader and the download function into `data_sources`, and a contract test that hard-coded the 6 h interval). The new tests write tiny extracts with pyosmium and drive the adapter against a fake change-file service; the PostGIS round trip covers the `ext-` snapshot, envelope v2 flags, the identical-data skip, and a change file that removes and adds records. The Overpass tests still run unchanged.
- Frontend: type check clean; 52 Vitest tests passed.
- Browser (Playwright, three viewports): 78 passed in 1.9 min with no page errors, after one spec fix (the operations spec hard-coded the 6 h interval; it now accepts the configured interval) and a new check that the Data Health panel names the camera source. A first run before the fix failed that one test at all three viewports and passed the other 75.
- `scripts\smoke_test.ps1 -CheckRestart`: passed on the M10 images: the `ext-` snapshot (2,766 mapped ALPR records) and the graph survived the restart; the basemap check reads the path from the region endpoint.
- Migration 0004 applied to the live database (`db-migrate`).
- Live first extract sync (`scripts\sync_cameras.ps1`, 2026-10-20T00:09:53Z): the worker copied the graph's extract in about a second, found the publisher's state at 4945 (up to date), read 2,876 elements in 5.6 s, and promoted `ext-colorado-20261018T202506Z-11935e75`: 2,766 ALPR records, all inside envelope v2, 2,168 Flock, 238 unknown manufacturer; diff against the Overpass snapshot: 4 added, 1 changed, 139 missing and carried as no longer mapped. The 139 are the records across the state line that the Overpass box included (77 outside envelope v1, 58 in the 20 km strip) plus edits of 2026-10-19, which the extract (data up to 2026-10-18T20:25Z) does not yet have; they age out after 72 h. The job took 133 s against 71 s for the Overpass job; a forced rerun with the copy in place and the publisher unchanged took 7 s (one state request plus the 5.6 s read) and ended as "identical snapshot already stored", so the first run's time was the database stage (inserting 2,876 records, carrying 139 rows, diffing against the 3,011 previous rows).
- The worker restarted on the new image without querying: "active snapshot is fresh; next scheduled sync in 1309 minutes".
- The publisher had not released the change file for 2026-10-19 by 2026-10-20T00:30Z (state still 4945), so the first live application of a change file by the worker happens at the next scheduled run; the real change-file path was exercised by the probe above and the adapter's loop by the fake-server tests.

### Gate check (M10 as proposed on 2026-10-19)

- The Colorado planner no longer depends on a shared public endpoint for its camera inventory: the recurring external traffic is one state request per day plus the day's change file from the publisher that already supplies the road data.
- Daily cadence, politeness, and the full-download rule are configuration and are disclosed in Data Health; the camera source is still fixed by configuration and never derived from a trip.
- Coverage is stated honestly: envelope v2 stops at the publisher's outline, and the coverage note appears in Data Health and the documents.
- No public deployment, no paid service, no new host software: pyosmium runs inside the backend image.
- Rollback is documented: switch the adapter back to `overpass_bounded`; the `ovp-` snapshots remain retained.

### Observations

- The extract (data up to 2026-10-18T20:25Z) was a day older than the Overpass snapshot it replaced, so "source data as of" moved back by a day until the publisher's next change file; the staleness rule (48 h) still reported the inventory as fresh.
- Geofabrik's outline is a coarse polygon that only slightly exceeds the state, which is why the envelope had to change; the register's M0 statement that the outline "fully contains the 20 km Denver envelope" remains true for Denver only.
- The sync's time is dominated by the database stage, not by reading the extract (5.6 s); worth a look in a later milestone, since the record count is now statewide.
- `ruff check` reports many pre-existing line-length findings across the project; it is not part of the verification gate and was left as is.

## 2026-10-19 - M9: Colorado service area

### Built

- **Owner decisions (decision 0003):** no public use for now and a separate approval before any public deployment; the owner tests personally; the service area expands to all of Colorado; licensing deferred; M10 (extract-based camera ingestion with daily diffs) approved in principle and started only after this gate.
- **Service boundary `colorado-service-v1`:** the U.S. Census Bureau TIGERweb state boundary (State_County MapServer, layer 0 "States", GEOID 08, January 1, 2026 vintage), retrieved 2026-10-19T21:45:57Z as one GeoJSON polygon of 7,519 vertices (269,604.5 km²) and kept at full resolution in `data/boundaries/colorado_service_boundary_v1.geojson`; the raw download and the layer metadata are under `data/boundaries/raw/`; register section 6b; attribution "Boundary: U.S. Census Bureau TIGERweb state boundary (public domain)" in the footer, Data Health, print, and export.
- **Camera data envelope `colorado-envelope-v1-20km`:** built in PostGIS from the boundary (20 km buffer in EPSG:26913, simplified to 25 m, clipped to the routing graph's tileset extent): 311,081 km², 190 vertices, bounding box W -109.2889956, S 36.8122307, E -101.8139749, N 41.1835420. Configuration validation still requires the envelope to contain the boundary.
- **Statewide camera query:** `data/raw/overpass/colorado_alpr_envelope_query.overpassql`, the Denver filters over the fixed box [36.70, -109.40, 41.30, -101.70]; scheduler, cooldown, retries, and User-Agent unchanged.
- **Statewide basemap:** `colorado.pmtiles` (Protomaps build 20261015, zoom 15, box -109.30, 36.80, -101.80, 41.20): 561 MB extracted in 44 s into the `basemap` volume; `BASEMAP_FILE` and `BASEMAP_BBOX` default to it; the Denver extract stays in the volume.
- **Configuration and API:** `configs/regions/colorado.yaml` (config_version 2) is the default region; `denver.yaml` remains loadable through `DEFLOCK_REGION_CONFIG`. The plan request's `region_id` is optional and defaults to the configured region (a different id is a validation error). The region endpoint's attributions come from the configuration. Every wording that named the pilot area now comes from the region display name: planner subtitle, endpoint messages ("outside the Colorado service area"), map label, page description, and the footer non-affiliation (now including the U.S. Census Bureau).
- **Review cases:** `data/fixtures/pilot_trips.json` grows from nine to eighteen planned trips (the Denver cases plus Union Station to Red Rocks, Colorado Springs, Boulder, Fort Collins, Pueblo, Grand Junction, Frisco to Vail, Denver to Colorado Springs, Denver to Grand Junction) and three expected rejections (Cheyenne, Santa Fe, same place). The Colorado Springs destination is the passenger terminal as the local geocoder places it (38.7985, -104.7009); the coordinate first chosen was on the airfield and snapped 804 m to a road, which the fixture's 300 m rule caught.
- **Legality check corrected:** the live pilot-trip check treated an engine edge reported as `backward` as illegal. On the Colorado Springs case the standard route drives North 31st Street, which OpenStreetMap tags `oneway=-1` (one way against the drawn direction), and the engine reports `edge.traversability` relative to the drawn direction, so a legally driven `oneway=-1` way reads `backward`. Verified against the engine: the auto-costed `edge_walk` match refuses the same stretch walked the other way (HTTP 400, error 443), refuses a `oneway=yes` stretch walked backwards, accepts a two-way stretch both ways, and `/locate` shows the directed edge the route uses with car access and `forward: false`. The check now relies on the walk succeeding and confirms every `backward` edge through `/locate` (car access, against the drawn direction). The Denver trips never crossed such a way, which is why M8 did not see it.
- **Tests follow the configured region:** the sync and resilience integration tests use `app_config.region.region_id` instead of the pilot id; the far record outside the envelope moved to Kansas (39.0, -98.0) so it is outside both envelopes; the first-snapshot envelope count is checked against the configured envelope; Glendale is inside the Colorado area; the boundary unit tests cover Denver, DEN, Glendale, Red Rocks, Grand Junction, Colorado Springs, and Durango inside and Cheyenne, Santa Fe, and Green River (Utah) outside, with the Denver configuration still loading; the contract tests use Cheyenne as the outside endpoint; the browser specs no longer send a region id and accept any region's snapshot id.
- **Smoke test:** reads the basemap path from the region endpoint instead of a fixed file name.
- **Documents:** decision 0003; data source register 6b; attribution (two boundary rows, Census policy row, independence statement); privacy flows; user guide; operations runbook (statewide Overpass load); project context; implementation plan rows M9 and M10 and the M8 outcome; test plan; audit note; README.

### Verification (2026-10-19)

- Backend in the container: 178 passed in 19 s, including the eighteen planned trips and three rejections. Host: not run this time: the host interpreter has no backend dependencies (the Docker-only rule keeps them off the host), so the container suite is the authoritative backend run.
- Frontend: type check clean; 52 Vitest tests passed (13 files).
- Browser (Playwright, three viewports): 78 passed in 1.6 min with no page errors, after two spec fixes (the experience spec sent the pilot region id, which the API now rejects; the smoke spec expected the pilot snapshot prefix). A first run before those fixes failed the same two tests at all three viewports and passed the other 72.
- `scripts\smoke_test.ps1 -CheckRestart`: passed on the Colorado configuration: the statewide snapshot and the graph survived the restart, and the basemap check now reads `/basemap/colorado.pmtiles` from the region endpoint.
- Live statewide inventory: the worker's first statewide query failed three times (HTTP 502 and 504 from the shared instance within the bounded retries; the worker kept the Denver snapshot and scheduled the next attempt); a manual refresh about 90 s later (`scripts\sync_cameras.ps1`) succeeded and promoted `ovp-colorado-20261019T215551Z-f091c3f5` (source base 2026-10-19T21:55:51Z, downloaded 21:57:41Z): 3,011 records, 2,901 ALPR, 2,824 inside the envelope, 2,282 Flock, 240 unknown manufacturer. Associations for the statewide snapshot: 1,539 new in 9.4 s, 1,285 reused from the Denver cache.
- Live pilot trips (E = exposure, matched plus uncertain; T = estimated time; counts come from this snapshot and are printed, never asserted):

  | Trip | Search | Calls | Standard E / T | Balanced | Fewest mapped |
  |---|---|---|---|---|---|
  | union_station_to_zoo | completed | 1 | 4 / 618 s | 0 (+113 s) | same as balanced |
  | capitol_to_washington_park | completed | 1 | 0 / 571 s | same as standard | same as standard |
  | downtown_one_way_grid | completed | 1 | 0 / 184 s | same as standard | same as standard |
  | union_station_to_den | completed | 5 | 7 / 1,669 s | 4 (+340 s) | 2 (+734 s) |
  | cherry_creek_to_highlands | completed | 1 | 4 / 609 s | 0 (+61 s) | same as balanced |
  | zoo_to_cherry_creek_mall | completed | 1 | 0 / 477 s | same as standard | same as standard |
  | union_station_to_coors_field | completed | 1 | 0 / 120 s | same as standard | same as standard |
  | botanic_gardens_to_union_station | completed | 2 | 4 / 582 s | 0 (+70 s) | same as balanced |
  | washington_park_to_lowry | completed | 1 | 4 / 859 s | 0 (+49 s) | same as balanced |
  | union_station_to_red_rocks | completed | 1 | 5 / 1,382 s | 0 (+185 s) | same as balanced |
  | colorado_springs_garden_of_the_gods_to_airport | completed | 7 | 4 / 1,439 s | 1 (+127 s) | 0 (+758 s) |
  | boulder_pearl_street_to_cu | completed | 3 | 4 / 278 s | 0 (+110 s) | same as balanced |
  | fort_collins_csu_to_old_town | completed | 1 | 1 / 392 s | 0 (+58 s) | same as balanced |
  | pueblo_riverwalk_to_csu_pueblo | budget exhausted | 8 | 2 / 532 s | 1 (+42 s) | same as balanced |
  | grand_junction_downtown_to_cmu | completed | 1 | 0 / 300 s | same as standard | same as standard |
  | frisco_to_vail | completed | 2 | 2 / 1,644 s | 0 (+90 s) | same as balanced |
  | denver_to_colorado_springs | budget exhausted | 8 | 8 / 3,895 s | 4 (+151 s) | same as balanced |
  | denver_to_grand_junction | partial (see observations) | 8 | 21 / 13,529 s | 16 (+275 s) | 14 (+645 s) |

  Rejected as expected: `union_station_to_cheyenne` and `santa_fe_to_denver` (OUTSIDE_SERVICE_AREA), `same_place_twice` (VALIDATION_ERROR). Every displayed option passed the corrected legality check; every avoidance option is complete, lower in exposure, within its bound, and geometrically distinct. Plan requests took under 1.1 s except Denver to Colorado Springs (3.4 s) and Denver to Grand Junction (4.2 s).
- Boundary checks (unit): Denver, DEN, Glendale, Red Rocks, Grand Junction, Colorado Springs, and Durango inside; Cheyenne, Santa Fe, and Green River outside; the envelope contains the boundary and lies inside the graph extent.
- Live geocoder: "Colorado Springs Airport" resolves to Airport Road first; the terminal resolves from its street address (7770 Milton E. Proby Parkway). Place-name ranking in the local geocoder is a known limitation, unchanged by M9.

### Gate check (M9 as proposed on 2026-10-19)

- Trips anywhere in Colorado plan; endpoints in Wyoming and New Mexico are rejected with OUTSIDE_SERVICE_AREA although the routing graph continues across the state line (verified live and in the contract tests).
- The region configuration drives wording, attribution, and the camera envelope; the Denver configuration still loads, and the M8 audit's statements remain valid for it.
- No public deployment and no paid service. The only external calls remain the fixed-box camera query (now statewide) and the one-time boundary download, both recorded in the data source register. The browser privacy suite ran unchanged.
- Carried to M10: the statewide Overpass query is heavier, and the shared instance answered 502/504 on the first attempt. The worker's response (keep the previous snapshot, retry at the next interval) is the designed one, but the dependency on a public endpoint is the reason M10 moves ingestion to the Geofabrik extract.

### Observations

- The engine's `edge.traversability` is relative to the OpenStreetMap way's drawn direction, not to the direction of travel; the auto-costed edge walk is what proves a direction is drivable. The pilot-trip check now says so in its docstring.
- On the Denver to Grand Junction trip one penalized candidate request is answered by the engine with HTTP 400, error 233 "Failed to edge walk line feature": one of the 120 m route pieces that carry a `linear_cost_factors` penalty could not be walked by the engine. The planner reports the search as `partial` with the candidates assessed so far (two improved options, +275 s and +645 s), which is the honest outcome, but the search stops at that request. Follow-up candidate for a later milestone: drop the piece the engine rejects and continue the search.
- Mapping density outside the Denver area is lower: Grand Junction and the Pueblo trip show zero to two records, Fort Collins one. Statewide, "no better route within your limit" and small counts will be common, and the "unmapped cameras may exist" caveat matters more.
- Mistakes caught by the checks during the milestone: the first `region_id` default rejected every plan under the new configuration (contract tests); the first airport coordinate was on the airfield (the fixture's snapping rule); the integration tests carried the pilot's region id (the container suite); the browser specs carried the pilot's region id and snapshot prefix (the browser suite).

## 2026-10-19 - M8: Denver pilot audit and v1.0 release candidate

### Built

- **Release candidate `1.0.0rc1`:** API and package versions, image tags, and the sync User-Agent bumped; git tag `v1.0.0-rc1` on the final commit.
- **Local-only network layout (roadmap 13):** the Compose stack now has an `internal` network (no route outside the machine) for web, api, db, valhalla, and geocoder, and an `egress` network joined only by the camera-sync worker, the public-data setup jobs, and the port-publishing edge. Verified by probing every container.
- **Release audit script:** `scripts\audit.ps1` with `keys`, `egress`, `logs`, `restore`, and `perf` checks that print evidence and never log a trip.
- **Browser privacy suite:** `apps/web/e2e/privacy.spec.ts` (same-origin requests only, POST bodies for trip details, no browser storage, cookies, or service worker, no coordinates in the address bar, Clear trip empties the page).
- **Pilot fixture set:** `data/fixtures/pilot_trips.json` with nine reviewed public-landmark trips and two expected rejections, planned live by `tests/integration/test_pilot_trips_live.py` with legality, snapping, complete-assessment, lower-exposure, and distinct-geometry checks.
- **Documentation:** `docs/AUDIT.md` (definition of done item by item, suites, live cases, fresh install, performance, privacy summary, source-policy review, known limitations, release checklist, what to tell a pilot user), `docs/ATTRIBUTION.md` (data, software, policies, independence statement), privacy document with the executed egress audit and the remaining limitations, user guide, operations runbook, test plan, and README for the release candidate.

### Verification (2026-10-19)

- Backend in the container: 167 passed, including the eleven pilot trip cases. Host: 125 passed, 42 skipped.
- Frontend: type check clean; 52 Vitest tests passed.
- Browser (Playwright, three viewports): 78 passed in 1.3 min with no page errors, including the new privacy suite. One earlier run straight after two stack restarts failed the address-based tests because the self-hosted geocoder answers its first searches slowly on a cold cache; the API timeout is now 15 s and the geocoder health check is a real search, and the rerun passed.
- `scripts/smoke_test.ps1 -CheckRestart`: passed on the split networks with the release-candidate images (API version 1.0.0rc1); the snapshot and the graph survived the restart.
- Release audit (`scripts\audit.ps1`): no API key, token, or paid provider anywhere; egress probes show api, web, valhalla, db, and geocoder without an internet route and only camera-sync reaching the public Overpass instance; after a plan, an address search, a reverse lookup, a camera viewport query, and an outside-area plan, zero occurrences of any coordinate, address, bounding box, or landmark name in the edge, api, web, geocoder, and valhalla logs (39 lines captured); a compressed dump of the live database (825 KB) restored into a scratch database with identical counts (7 snapshots, 11,175 records, 2 diffs, 1,285 associations, 11 jobs, same active snapshot), scratch dropped afterwards.
- Live pilot trips: nine planned trips and two expected rejections from `data/fixtures/pilot_trips.json`; every displayed option road-legal by `trace_attributes`, every avoidance option complete, lower in exposure, and within its bound, all geometries distinct, snapping at most 117 m; five trips found a zero-exposure alternative for +49 to +113 s, the airport trip went 7 to 4 to 2 mapped records, three trips had nothing to avoid; searches took 0.05 to 0.72 s with 1 to 5 routing calls.
- Fresh install: two attempts from a clean clone as a separate Compose project on port 3100 with the geocoder skipped. The first (f162136) failed in `valhalla_build_timezones`, which downloads the timezone boundary shapefile from GitHub and had no route on the internal network; the graph-build job now joins the egress network and the download is documented (034a3cb). The second (034a3cb) passed: bootstrap 322 s (graph build 136 s), its smoke test and a restart smoke test on the fresh project passed, 339 s in all including teardown; the main stack was untouched.
- Performance: cold start 19 s to healthy; first plan 353 ms; 27 warm pilot-trip plans with three preferences p50 104 ms, p95 717 ms, max 757 ms; API 125 MB resident; database 27 MB.

### Gate check (roadmap M8)

- Evidence for an invited pilot is assembled in `docs/AUDIT.md`; the decision to invite anyone is the owner's.
- No claim of global route optimality, complete camera coverage, or guaranteed avoidance appears in the UI or the documents; the wording was re-read for this audit.
- No public deployment exists and the service boundary is unchanged; both need separate approval.

### Observations

- Splitting the networks surfaced nothing broken: no service needed the internet except the sync worker and the setup jobs, which confirms the local-only design rather than changing it.
- The whole inventory database compresses to under a megabyte; backups are cheap and the restore path is a two-minute operation.
- The audit changed two things and found nothing else: the self-hosted geocoder is slow on its first searches after a restart (now a 15 s API timeout and a search-based health probe that keeps the cache warm), and the diff-history row limit is the one query parameter besides the camera viewport, which the privacy suite now names explicitly. The release candidate is otherwise the M7 code with a version, a network boundary, and evidence.
## 2026-10-19 - M7: scheduled updates, resilience, and operating instructions

### Built

- **One scheduler, politely:** unchanged from M2 (one `camera-sync` container, region lock, 6-hour interval, restart waits for the remainder of the interval). Data Health now derives the same schedule the worker uses: next due time, overdue flag (interval plus a one-hour grace), last trigger, and the fact that syncs run only while the stack is up.
- **Manual refresh cooldown and coalescing:** operator refreshes share a 30-minute cooldown (`manual_refresh_cooldown_minutes`); a refresh inside it is recorded as a `skipped` sync job with the reason and the active snapshot id, `--force` (`scripts\sync_cameras.ps1 -Force`) bypasses it, concurrent runs still coalesce on the region lock, and the scheduled worker is never subject to the cooldown.
- **Rollback without deletion:** `deflock-snapshot-review rollback [snapshot_id] --note` (`scripts\review_snapshot.ps1 rollback`) makes a previously active, still-retained snapshot active again; the replaced snapshot stays retained as superseded so the rollback can be undone the same way; refusals for a missing note, an already active, unknown, pruned, or never-active snapshot; a `rollback` job records both ids and the note.
- **Graph rebuild workflow with validation and rollback:** the build keeps the graph it replaces as the last-good graph in the volume (`previous/`); `scripts\import_region.ps1` now validates the promoted graph through the running application (router available, a reviewed public-landmark route succeeds) and refreshes the camera road associations for the new graph version, and tells the operator to roll back when validation fails; `scripts\rollback_graph.ps1` (`graph-rollback` setup job) swaps the last-good graph back, restarts the service, refreshes associations, and running it again undoes the rollback.
- **Per-request version pinning made visible:** the planner polls Data Health every five minutes and when the tab becomes visible again; a result planned on an older snapshot or graph is marked outdated and stays exactly as computed (the person plans again to use current data). The API already pinned the active snapshot per request; an integration test now proves a request on snapshot A keeps A's records and lifecycle states after B is promoted.
- **Freshness policy and provider limits disclosed:** Data Health carries the scheduler block and a `provider_policy` block (fixed envelope query never derived from a trip, one request at a time, identified application, timeout, pause after a rate limit, attempts, backoff, no endpoint rotation); the routing graph's rebuild cadence is shown.
- **Diff history:** `GET /api/v1/cameras/diffs` lists what each retained snapshot changed versus the one it replaced, with state and review notes; Data Health shows it as "Snapshot history".
- **Resource monitoring without trip data:** `GET /api/v1/health/metrics` reports per route template request counts, rejected and failed counts, p50/p95/max latencies from a bounded in-memory reservoir, plan outcomes by search status, options returned, routing calls, plan latencies, API process memory, and public-data storage sizes; Data Health summarises it. Nothing in it derives from a trip, and the tests assert the absence of coordinates, addresses, and geometry.
- **Operating instructions:** `docs/OPERATIONS.md` (everyday operation, the scheduler, cooldown, outcomes, review, snapshot and graph rollback, rebuild, version pinning, metrics, measured disk and memory, backups, upgrades, troubleshooting); the user guide, data dictionary, privacy document, and test plan updated.

### Verification (2026-10-19)

- Backend in the container: 156 passed, including the M7 resilience matrix on PostGIS (manual cooldown recorded as a skipped job, `--force`, scheduled unaffected; rollback and its undo with refusals; pinned snapshot assessable across a promotion; truncated upstream response keeps the active snapshot; diff history), the metrics and scheduler unit tests, and the M7 contracts (metrics without trip text, scheduler and policy without a database, diff history unavailable rather than empty). Host: 125 passed, 31 skipped.
- Frontend: type check clean; 52 Vitest tests passed (Data Health scheduler, policy, history, and metrics views; the outdated-result notice after a newer snapshot is reported, with the planned result untouched).
- Browser (Playwright, three viewports): 72 passed in 2.4 min with no page errors. The new operations tests show Data Health with the scheduler, the source policy, the snapshot history, and the service metrics, assert that the metrics endpoint carries no coordinate, address, or geometry text, and show that a planned result is marked outdated when Data Health reports a newer snapshot while the result itself stays as computed.
- `scripts/smoke_test.ps1 -CheckRestart`: passed on the M7 images: the rebuilt graph (built 2026-10-19T20:02:35Z) and the new snapshot survived the restart.
- Live operations checks on the pilot machine, in this order:
  - Manual refresh twice: the first made one public query and promoted `ovp-denver-20261019T195537Z-83bc21f3` (replacing the 14:46 snapshot); the second and a third were skipped by the cooldown and recorded as `skipped` jobs; Data Health reported "on schedule", next due 2026-10-20T01:57Z, cooldown remaining 1,766 s.
  - Snapshot rollback to the previous snapshot and roll-forward to the newer one through `scripts\review_snapshot.ps1 rollback`; both recorded as `rollback` jobs; 7 snapshots retained; the diff history endpoint shows the review notes.
  - Failed rebuild: `graph-build` against a missing extract exited 2 and the active manifest (built 2026-10-15T23:22:43Z, 599 tiles) was untouched.
  - Forced rebuild with `scripts\import_region.ps1 -Force` while a route loop planned Union Station to Denver Zoo every two seconds for eleven minutes: the latest Geofabrik extract (385,213,485 bytes) downloaded and verified in 26 s; the graph built in 214 s (build_tiles 202 s, 599 tiles) in staging and was promoted; the service restarted; the script validated the new graph through the app (built 2026-10-19T20:02:35Z, test route 9 maneuvers) and refreshed the association cache (1,279 records in 10.1 s, 1,285 rows of the old graph pruned); 268 s end to end. The loop recorded 292 successful plans and 0 failures: 99 cited the old graph version, 192 the new one, and 1 (during the restart) came back with the Standard route but no graph version, that is, honestly not assessed rather than wrong. The previous graph stayed in the volume as the last-good graph (606 MB).
  - Graph rollback with `scripts\rollback_graph.ps1`: the last-good graph was swapped back (Data Health: built 2026-10-15T23:22:43Z; a test route succeeded with that graph version) and the association cache was refreshed for it (1,285 records, 12.2 s); running the script again undid the rollback (built 2026-10-19T20:02:35Z again, test route 9 maneuvers, cache refreshed in 10.9 s). No download or rebuild was needed for either step.

### Gate check (roadmap M7)

- New published source records flow into later route assessments after a validated sync: the manual refresh above promoted a new snapshot and the next plans cite it; the M2 and M7 integration tests prove added, edited, and vanished records across snapshots.
- The app does not overwrite good data on failure: outage, rate limit, HTML page, malformed or truncated JSON, quarantine, and concurrent runs all keep the active snapshot (integration tests); a failed graph build leaves the active graph untouched (live).
- Scheduled sync only runs when the local service is running; reopening catches up politely: the worker is a Compose service; the schedule view and the worker share `seconds_until_due`; a stack that was down catches up with one query.
- Rollback does not require deleting the database: snapshot rollback flips promotion flags only; graph rollback swaps files kept in the volume.

### Observations

- The first manual refresh of the day was the only public query M7 made; everything else was served from retained data. The cooldown message names the age of the active snapshot so an operator understands why nothing happened.
- Metrics are keyed by route templates taken from the OpenAPI document rather than from the request scope, because this FastAPI version nests included routers in a way that hides the matched route from middleware; the raw URL is never used as a key.
- A forced rebuild on the pilot machine takes about four and a half minutes including the download, validation, and the association refresh, and keeping the last-good graph costs about 600 MB; both numbers are in the runbook. Graph rollback is a file swap plus a restart, about 25 s including the association refresh, so a bad rebuild costs minutes, not a day.
## 2026-10-19 - M6: complete trip-planning experience

### Built

- **Result states that cannot be confused (gate):** every card carries a labelled state block: *No mapped encounters* (the honest zero, with an extra caveat when the snapshot holds no records inside the assessed area), *Unknown data* (nothing assessed; counts unknown, not zero), *Incomplete assessment* (route leaves the assessed area; lower bound, not ranked), *No better route within your limit* (Standard card, with the raise-limit action), *Lower exposure than Standard* (alternatives, including the zero sentence when they reach zero); *No route at all* is its own block in the planner, distinct from engine outages and validation errors.
- **Data-age badges:** the status strip and every card show how old the camera download and the road data are; stale snapshots (threshold from Data Health), an empty inventory, and snapshots awaiting operator review are flagged.
- **Camera details:** the evidence list and the map ring popups now carry the raw mapped status, the direction tag, the source's last edit time, and the check date next to manufacturer, distance, association, and the source link (backend: `source_timestamp` and `check_date` on each encounter).
- **Directions:** a summary line (steps, distance, estimated time, toll or highway use, selected preference), engine instruction text untouched, road names only when supplied, roundabout exits, "to next" distances, keyboard focus with `aria-current`, and the plan-while-stopped wording.
- **Print view and GeoJSON download:** a print stylesheet keeps the selected card, the directions, a print header with trip endpoints, snapshot and graph versions, and the disclaimer, and drops the map and controls; the download writes the selected geometry with timestamps, counts, maneuvers, and the recalculation warning to a file on the user's computer (nothing uploaded).
- **Cancel, clear, focus:** cancelling is an explicit state and the late answer to a cancelled request is discarded; Clear trip aborts any request in flight and resets inputs, result, selection, and errors while keeping preferences; a successful plan moves keyboard focus to "Route options"; errors are announced as alerts; a skip link leads to the planner.
- **Mobile bottom sheet:** a one-line summary of the selected route stays visible when the sheet is hidden; the sheet button declares what it controls; state survives viewport changes.
- **Optional one-shot device location:** "Use my location" asks the browser once, only on the click, labels the start as a device estimate with its accuracy and the nearest mapped place, explains a denied permission, and never watches or stores the position (roadmap section 12).
- **Accessibility polish:** visually hidden help for the inputs, labelled select buttons on the cards, `aria-pressed` and `aria-current`, a text alternative stating that the map is optional, reduced-motion respected, and an automated axe scan in the browser suite.
- **Disclaimer wording** reviewed: the footer now says that nothing leaves the computer except requests to the local services; the directions say the app does not follow your position or know about closures.

### Verification (2026-10-19)

- Backend in the container: 142 passed (the encounter detail fields ride on the existing suites). Host: 116 passed, 26 skipped.
- Frontend: type check clean; 49 Vitest tests passed (the four result states with the empty-inventory caveat, badges with the stale flag, print and download on the selected card only, status-strip badges, directions summary and steps, device location and its denied state, explicit cancellation with the late answer ignored, the no-route-at-all state, focus on results, clear trip, age and export helpers, plus the M1 to M5 suites).
- Browser (Playwright, three viewports): 66 passed in 1.8 min with no page errors. The new experience suite covers the full address-to-address flow with selection of another option, keyboard-only operation, the narrow-screen sheet with state surviving viewport changes, cancellation with the late answer discarded, the print view, the GeoJSON download, no request while typing and none off the origin, the four result states against mocked responses derived from a real one, the one-shot device location with a mocked position, data-age badges, and an axe scan with zero serious or critical violations before and after planning. The suite now shares the edge's network namespace and reaches the app at `http://localhost:3000`, a secure context like a person's browser.
- `scripts/smoke_test.ps1 -CheckRestart`: passed on the M6 images; the snapshot and graph survived the restart.
- Reviewed by hand in the browser: the screenshot spec saved fifteen full-page captures (three viewports; start, planned, alternative selected, evidence open, print layout) under `apps/web/e2e/test-results/screens/`, and I looked at the desktop and phone captures: the dashed alternative and the bold selected route render with the encounter rings, the state blocks and badges read correctly, the evidence entries show status, roads, reason, heading, mapped status, last edit, check date, and the source link, and the print layout keeps the header, the selected card, and the directions. The first print capture still showed the slider and checkbox labels, which are now hidden as well.

### Gate check (roadmap M6)

- A person can plan and compare a trip without opening a terminal: the browser suite runs the whole address-to-address flow through the local geocoder, compares the three preferences, selects another option, prints, downloads, and raises the limit from the page; the user guide describes every control.
- The UI clearly distinguishes no mapped encounters, unknown data, no better route, and no route at all: distinct labelled blocks with their own test ids, exercised in unit tests and in the browser against mocked responses derived from a real one.
- Full browser flow, keyboard-only operation, narrow-screen layout, request cancellation, late-response handling, synchronized route and instructions, and no external autocomplete on a restricted provider: each is a named browser test.

### Observations

- The axe scan is the first automated accessibility check in the project; it found no serious or critical violations on the initial page or after planning at any of the three viewports, which is a floor, not a certificate; keyboard operation and screen-reader wording were checked by the named tests and by reading the markup, not by a person using assistive technology.
- **Two bugs found by the browser suite before the commit:** the "Use my location" button was rendered only on the client (`navigator` is undefined on the server), which produced a React hydration mismatch on every page load; it is now decided after mount. And the test browser reached the stack at `http://edge:3000`, where Chromium treats the page as insecure and refuses geolocation, which is also what a person would hit on any host name other than localhost; the planner now explains that case, and the suite runs from the edge's network namespace at localhost.
- Alternatives that reach zero exposure are labelled "Lower exposure than Standard" and still carry the honest zero sentence, so the comparison and the zero statement never contradict each other.
- "Use my location" is implemented as the roadmap's optional, deliberate action only; it is the only feature that reads a sensor, and the browser test mocks the position.

## 2026-10-19 - M5: camera-aware route generation and comparison

### Built

- **Avoidance requests (decision 0001 D5):** the Valhalla adapter gained `avoiding_candidates`, which adds only `linear_cost_factors` (encoded polyline pieces with a factor) and `exclude_locations` (at most 50 points) to the documented baseline request. Engine warnings are surfaced; undocumented, over-limit, or empty inputs are refused before the engine sees them.
- **Bounded candidate search:** targets are 120 m pieces of each assessed candidate's own geometry around every counted record (matched or uncertain), accumulated across candidates so the search learns the corridor. Penalized requests escalate 10, 40, 160; then one hard-exclusion request on the current best candidate's records; then penalized requests at the maximum factor while new candidates keep appearing. Records within 100 m of the start or destination are never targeted (no route can avoid them) and are reported as unavoidable. The search stops on zero exposure within the tightest requested limit, on convergence, on the 8-call budget, or on the 20 s deadline; an engine refusal of exclusions is disclosed and ends the search rather than being retried blindly.
- **Full reassessment:** every engine answer is de-duplicated by geometry, validated (start and destination maneuvers, ordered indices covering the shape), and assessed over its entire path against the whole envelope with the M4 assessor. Candidates that leave the envelope are excluded from ranking and reported as not ranked.
- **Deterministic ranking (roadmap 10.4):** exposure is matched plus uncertain records, each once. Per preference, among fully assessed candidates within min(T0 + max_extra, factor x T0): minimise exposure, then duration, distance, and a geometry key. The user's extra-time control replaces the Balanced limit; Fewest mapped is never tighter than the user's limit. Ties never favour a longer route. Preferences that choose the same path share one card; a preference that finds nothing better is labelled on the Standard card with that message; when the assessment is unavailable every preference reports `not_assessed` and the response warns, so nothing degrades silently.
- **Contract:** a `search` block (status `completed` / `budget_exhausted` / `partial` / `not_run`, routing calls used and budget, deadline and elapsed time, candidates generated and assessed, iterations, notes, one outcome per preference with its limit and bound, method `search-1.0`, meaning); options carry `exposure_count`, `generated_by`, and `detour_bound_seconds`.
- **UI:** the planner always compares the three preferences ("Routes compared" explains each with its limit); a comparison summary above the cards shows calls, candidates, elapsed time, status, notes, and per-preference outcomes with a "raise the limit and plan again" action; cards show exposure, how the route was found, and the detour limit it satisfied; the map keeps the other options as thin dashed grey lines under the selected route.
- **Synthetic routing fixture (roadmap 16):** `backend/tests/support/synthetic_graph.py`, a deterministic grid engine that searches on penalized cost but reports physical time, with locate and route_edges services so a whole plan runs end to end without a network.

### Verification (2026-10-19)

- Backend in the container: 142 passed, including the 16-case M5 matrix on the synthetic network (lower-exposure detour found and shared by both preferences; a longer detour with unchanged exposure not presented as a benefit and an over-budget zero-exposure candidate rejected, then admitted when the limit is raised; deterministic repeats; a record at the destination unavoidable and never excluded; an engine refusing exclusions handled; penalized cost never changes reported time; no silent degradation without assessment; a zero-exposure Standard needs no search; baseline alternates ranked without extra calls; budget exhaustion and the deadline disclosed; candidates leaving the envelope not ranked; a frontage-road camera counted as uncertain; Standard always present and first), adapter tests for the avoidance request, contract tests for the search block, and the live Denver cases. Host: 116 passed, 21 skipped.
- Live Denver cases, all three preferences, every option checked for legality with `trace_attributes`, complete assessment, lower exposure within its bound, distinct geometry, and a deterministic repeat:
  - Union Station to Zoo: Standard exposure 4 (618 s); Balanced and Fewest mapped share one option with exposure 0 at +113 s, a baseline alternate (the engine's own primary); 1 routing call, 3 candidates assessed, 0.16 s.
  - Capitol to Washington Park and the downtown one-way grid: Standard exposure 0, nothing to avoid, 1 call each.
  - Union Station to DEN: Standard exposure 7 (1,669 s); Balanced exposure 4 at +340 s (baseline alternate); Fewest mapped exposure 2 at +734 s, found by penalties at factor 160; 5 of 8 routing calls, 10 candidates assessed, 0.71 s.
  - Cherry Creek to Highlands: Standard exposure 4 (609 s); Balanced and Fewest mapped share one option with exposure 0 at +61 s (baseline alternate); 1 call, 0.11 s.
- Frontend: type check clean; 28 Vitest tests passed (comparison summary, shared labels, outcome messages, raise-limit action, not-assessed warning, the compare list in the shell, plus the earlier suites).
- Browser (Playwright, three viewports): 30 passed in 25 s. The routing smoke now requests all three preferences and asserts the search block, that every avoidance option is fully assessed with lower exposure and a distinct geometry, and that the comparison summary renders.
- `scripts/smoke_test.ps1 -CheckRestart`: passed on the M5 images; the Union Station to Denver Zoo request reported "0 mapped record encounters, 4 uncertain, assessment complete"; the snapshot and graph survived the restart.

### Gate check (roadmap M5)

- Routing changes, not just overlay colours: the airport trip's Fewest-mapped option is a different path the engine produced under penalties; the live test asserts distinct geometries for every option.
- Every displayed avoidance route is road-valid and fully assessed for its declared scope: legality per `trace_attributes` (no backward edges, drivable uses only, destination-only edges only at the ends) and a complete assessment are asserted live for every option, and the synthetic matrix shows partial candidates are never ranked.
- Limited candidate search is disclosed: the `search` block and the comparison summary carry status, calls, budget, deadline, elapsed time, notes, and per-preference outcomes.
- Artificial cost penalties do not contaminate ETA: the synthetic engine proves the planner reports physical time while the engine searched on penalized cost; M0 showed the same for Valhalla (factor 1000 left the reported time unchanged).
- Honest partial and no-improvement states: `same_as_standard` with the limit in the message and a raise-limit action; `budget_exhausted`, `partial` (deadline or engine failure), and `not_run` are distinct and tested.

### Observations

- On real Denver trips the engine's own alternates often carry the improvement: in three of five reviewed trips the Balanced option was a baseline alternate with zero exposure. Penalties mattered on the airport trip, where factor 160 produced a 2-exposure route the alternates did not offer.
- Exposure counts uncertain records (roadmap 10.4), so the corner ambiguity seen in M4 drives the comparison as much as matched records do; the cards show both numbers separately.
- The search is cheap on the local stack: under a second for every reviewed trip. The 20 s deadline and the 8-call budget were never reached live, only in the synthetic tests.
- The first synthetic scenario I wrote expected the full Ridge Road detour, but the search found a cheaper zig-zag through the grid with the same zero exposure; the test now encodes the engine's answer, which is the point of a real path search over a hand-picked "detour".

## 2026-10-19 - M4: encounter assessment and road-association validation

### Built

- **Stage A (meters):** PostGIS geography finds the active snapshot's ALPR records within 100 m of the route line and measures the fraction of the route inside the camera-data envelope. An in-memory metric index with the same interface drives the fixture tests, and an integration test shows the two agree within a metre.
- **Stage B (roads):** for each nearby record the engine's `/locate` service lists drivable roads within 50 m (one candidate per OpenStreetMap way, nearest first); `/trace_attributes` with `edge_walk` lists the roads the route traverses. A record is counted only when its nearest road is one the route uses and no other road is about as close. Parallel or frontage roads, grade-separated crossings (bridge/tunnel mismatch), ambiguous placements, carried "no longer mapped" records, and records outside the envelope stay visible as uncertainties with a written reason.
- **Counting rules:** each record once; repeated passes reported; site groups for records within 10 m; direction tags reported, never used to exclude; sensitivity counts at 25/50/100 m; partial coverage when the route leaves the envelope; `not_assessed` with null counts when any dependency is missing (never zero).
- **Contract:** route options carry `matched_camera_record_count`, `uncertain_nearby_camera_count`, `counting_method_version` (`assess-1.0`), the graph version, and a full `assessment` block with per-record explanations and association details. Migration 0003 adds the `camera_road_associations` cache (graph-version specific); `deflock-associate-cameras` / `scripts/associate_cameras.ps1` precompute it and the bootstrap runs it after the first snapshot.
- **UI:** route cards show the headline count with the honest zero wording, uncertain matches, sensitivity, coverage, and an expandable "Camera evidence" list; the map draws rings for counted, uncertain, and beyond-radius records with popups; `docs/ROUTING_METHOD.md` documents the method.

### Verification (2026-10-19)

- Backend in the container: 116 passed, including the 17-case assessment matrix on a synthetic metric street (camera on the traversed road, parallel and frontage roads, grade-separated crossing, ambiguous placement, split segments of one street, a same-named street elsewhere on the route, an unnamed cross way, no road within the radius, beyond the radius, Flock-only scope, no-longer-mapped and outside-envelope records, loops counted once, site groups, direction never excludes, missing snapshot or graph gives not-assessed), the recorded `locate` and `trace_attributes` fixtures, the PostGIS proximity test (geography distances within a metre of the metric index; coverage as a length fraction), the association-cache round trip, pruning, and recompute clearing, and the live Denver cases. Host: 95 passed, 21 skipped (integration cases need the container database).
- Frontend: type check clean; 24 Vitest tests passed (route-card wording for the zero, matched, uncertain, sensitivity, and not-assessed states; reducer; planner shell). No frontend file changed after the web image was built.
- Browser (Playwright, three viewports): 30 passed; the routing smoke accepts `complete`, `partial`, and `not_assessed` and asserts the encounter summary text.
- `scripts/smoke_test.ps1 -CheckRestart`: passed. The Union Station to Denver Zoo request reported "0 mapped record encounters, 4 uncertain, assessment complete"; the snapshot and graph survived the restart.
- Migration 0003 applied live. `scripts/associate_cameras.ps1 -Recompute` associated all 1,285 in-envelope ALPR records on graph `colorado-geofabrik-2026-10-14@2026-10-15T23:22:43Z` in 11.2 s with 0 failures: 1 record has no drivable road within 50 m, 8.7 candidate ways per record on average, the nearest road 6.4 m away on average, and 860 records have a different road within 10 m of being as close (mostly at intersections).
- Live assessments of the five reviewed trips, all `complete` with coverage 1.0, through the edge with a warm cache (39 to 218 ms per plan):
  - Union Station to Zoo: matched 0, uncertain 4. The four records at the Capitol corner sit 2 to 11 m from the route on East Colfax Avenue with Pearl Street about as close, so all four stay ambiguous with that reason.
  - Capitol to Washington Park: 0 and 0. Downtown one-way grid: 0 and 0.
  - Union Station to DEN: matched 4, uncertain 3, sensitivity 6 / 7 / 10. Four records on I-70 and Peña Boulevard are on the roads the route traverses; two I-70 records are ambiguous against unnamed adjacent ways (ramps); one record at the terminal is nearest an unnamed way while the route passes 41 m away on Terminal East; three records between 50 and 100 m are listed for sensitivity only.
  - Cherry Creek to Highlands: matched 0, uncertain 4, sensitivity 4 / 4 / 8.

### Gate check (roadmap M4)

- A reviewer can inspect why each camera is or is not counted: every encounter carries its status, distance in meters, position along the route, nearest road and distance, the route's road at that point, the ambiguity and grade-separation flags, the mapped direction next to the travel heading (information only), the source link, and a written reason. The UI lists them under "Camera evidence" and the map rings them.
- Direction never excludes a record: matrix test, and the `heading_relation` wording says "not used for counting".
- Missing data is uncertainty, never zero: `not_assessed` with null counts when the snapshot, graph, database, or engine edge services are missing (contract and matrix tests); partial coverage is flagged when a route leaves the envelope.
- Known false-association risks are reported, not hidden: parallel and frontage roads, grade-separated crossings, and intersection ambiguity each have a status and a reason, and the Capitol corner and the I-70 ramps show them live.
- Distances are meters on the spheroid: PostGIS geography and the metric index agree within a metre; nothing is compared in degrees.

### Observations

- Real example found while probing: three Axon ALPR records within a metre of each other at the Capitol with directions 0°, 185°, and 99° (one pole, three cameras). They are counted individually and grouped as one site.
- The engine's locate service returns several sub-edges per way (both directions and splits); the adapter keeps one candidate per way at its minimum distance, which is what road association needs.
- **Road identity refined after the first live run.** Comparing roads by OpenStreetMap way id flagged 969 of 1,285 records as ambiguous, because one street is split into many consecutive ways and a record's nearest way was often the neighbouring segment of the street the route was on. Roads are now identified by their name set (way id only when unnamed) and compared against the route edges within 150 m along the route of the pass, with tests for split segments, a same-named street elsewhere on the route, and an unnamed cross way. Union Station to DEN went from 3 matched / 4 uncertain to 4 matched / 3 uncertain. The cache stores raw candidates and the verdict is recomputed from them, so cached rows stay valid across rule changes; `-Recompute` was added for a clean rebuild.
- **Most records stay ambiguous at intersections (860 of 1,285).** Cameras are usually mapped at corners, where the cross street is within 10 m of being as close as the street the route uses. The assessment keeps those uncertain rather than guessing, so the headline matched count is conservative and the uncertain count carries most of the signal. Whether to keep the 10 m margin and whether M5's comparison should rank by matched plus uncertain are owner decisions before M5.

## 2026-10-19 - M3: standard route and usable address entry

### Built

- **Address entry:** candidates inside the pilot area are listed first with their match type; identical points are de-duplicated; a pair typed as `lon, lat` is recognised, swapped, and returned with a note that asks for confirmation instead of a silent failure; the no-match state is explicit. Still submit-only, never autocomplete.
- **Map pins:** a placed pin is labelled "Map pin near <nearest mapped place>" through a new reverse endpoint (`POST /api/v1/geocode/reverse`) on the local geocoder; the pin's own coordinates are kept for routing and a stale reverse result for a replaced pin is ignored.
- **Routing disclosures:** each route option reports how far the engine's start and end snapped from the chosen points; the card says so above 50 m. Maneuver checks now require in-range, ordered indices covering the whole shape, and a length-sum mismatch above 3 % becomes a visible warning. Identical start and destination is rejected with a clear message.
- **Units:** km/mi toggle in the UI; all server values stay in metres and seconds and are converted only in the display helpers (feet below 0.1 mi). The adapter handles a miles response from the engine.
- **Directions to geometry:** pointing at (or focusing) a direction step highlights its shape segment on the map, which exercises the begin/end shape indices directly.
- **Freshness and privacy strip:** always-visible road-data date, camera snapshot date (with a stale flag), address-search locality, and the no-storage promise.
- **Reviewed Denver cases:** a live backend test resolves ten public addresses and landmarks against the local geocoder with inside/outside flags, and routes five reviewed trips through the engine with legality evidence from `trace_attributes` (no backward edges, drivable uses only, destination-only edges only at the ends) plus alignment and snapping checks.

### Verification (2026-10-19)

- Backend in the container: 91 passed, including the live Denver cases against the local geocoder and router (ten addresses and landmarks within tolerance with correct inside/outside flags; nonexistent street empty; reverse lookup labels a pin; five reviewed trips legal per `trace_attributes` with no backward edges, drivable road uses only, destination-only edges only at the ends; maneuvers aligned; snapping under 300 m).
- Frontend: type check clean; 21 Vitest tests passed (units conversion, pin relabelling, units kept across clear trip, status strip and units toggle in the shell).
- Browser (Playwright, three viewports): 30 passed. Address-to-address planning with candidate confirmation through the local geocoder, the explicit no-match state, the swapped-coordinate explanation, the km/mi toggle without a new request, map initialisation (worker, controls, legend after load, no worker errors), pin-to-pin planning on the rendered map, plus the earlier smoke tests and the WebGL probe.
- `scripts/smoke_test.ps1 -CheckRestart`: passed after the backend rollout; the plain smoke test passed again after the final web rollout.
- The live stack runs the M3 images; the camera snapshot `ovp-denver-20261019T144621Z-37c4cf74` and the 2026-10-15 graph are unchanged.

### Gate check (roadmap M3)

- Address-to-address and pin-to-pin planning work for reviewed Denver cases: yes (live backend cases and browser tests above).
- No camera-avoidance claim yet: route cards say "Not assessed in this version", counts stay null, coverage `not_assessed`.
- Freshness and privacy disclosures appear in the UI: the status strip shows road-data date, camera snapshot date with a stale flag, address-search locality, and the no-storage promise; route cards show the snapshot date and graph version.

### Observations

- **Map worker bug found and fixed (present since M1):** MapLibre 6 ships its worker as a separate module and derives the worker URL from its own script URL, requiring a plain http(s) URL. Inside the Next.js production bundle that condition fails, the worker URL becomes empty, MapLibre logs "Worker failed to load", and the map never fires `load`: no boundary outline, no camera overlay, no pins, with an entirely blank map area. None of the earlier browser tests asserted a rendered map, so the gap went unnoticed. Fix: a `prebuild` step copies `maplibre-gl-worker.mjs` and `maplibre-gl-shared.mjs` from the installed package into `public/vendor/maplibre/` (ignored by git, served same-origin through the edge), and the map calls `setWorkerUrl` with that path before initialising. A new browser test asserts that the canvas appears, the overlay legend renders after `load`, and no worker error is logged.
- The test browser (headless Chromium in the Playwright image) does provide WebGL1 and WebGL2 through SwiftShader, so map-level browser tests are possible there; the pin-to-pin test still skips itself cleanly if a browser lacks WebGL2.
- **Second layout bug found by the pin test:** MapLibre's stylesheet sets `position: relative` on the map container, overriding the app's absolutely positioned container and collapsing its height to zero (the canvas still drew because MapLibre sizes it itself). The container is now positioned inline, which MapLibre's rule cannot override.
- My first version of the geocode endpoint reordered candidates to put pilot-area matches first. The live Denver cases showed it displacing the geocoder's best match for "Glendale, Colorado"; the reordering was removed so the first match means what the geocoder ranked first, with the inside/outside flag left to the user.
- NO_DRIVABLE_ROUTE cannot be produced from inside the Denver boundary in practice: the engine snaps to the nearest drivable road within its search cut-off, so the state is covered by the contract test and the M0 spike (engine error 171), not by a live Denver case.
- "Use my location" (browser geolocation) is deliberately not implemented; the roadmap lists it as optional and it would be the only feature that reads a sensor. It can be revisited in M6 with an explicit user action.

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
