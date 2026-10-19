# Development log

Newest first. Every entry records what was executed, what was only inspected, and what remains unverified.

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
