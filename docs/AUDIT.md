# Denver pilot audit and v1.0 release candidate (M8)

> M9 (2026-10-19, decision 0003) made Colorado the default service area after this audit. The audit below describes the Denver pilot configuration, which remains available through `DEFLOCK_REGION_CONFIG=configs/regions/denver.yaml`; the statewide evidence is in the M9 entry of `docs/DEVELOPMENT_LOG.md`.

Audited on 2026-10-19 on the pilot machine (Windows 11, Docker Desktop with about 8.3 GB allocated), version `1.0.0rc1`,
against the roadmap's definition of done (section 21). Every line says what was executed, what was only inspected, and
what remains unverified. Nothing here claims global route optimality, complete camera coverage, or guaranteed avoidance.

## 1. Definition of done, item by item

| # | Roadmap item | Status | Evidence |
|---|---|---|---|
| 1 | Named DeFlockMigration throughout UI and documentation | done | title, heading, print header, exports, compose project name, package names; `grep -ri deflock` finds no other product name |
| 2 | Address entry and map-pin alternatives both work | done | browser suites: address-to-address through the local geocoder, pin-to-pin on the rendered map, coordinates typed as `lat, lon`, one-shot device location; live geocode cases (M3) |
| 3 | Service boundary, data envelope, and graph extent versioned separately | done | `denver-service-v1`, `denver-envelope-v1-20km`, `colorado-geofabrik-2026-10-14@<build time>`; shown in Data Health and every route result |
| 4 | Real public ALPR records imported with source and lifecycle metadata | done | active snapshot `ovp-denver-20261019T195537Z-83bc21f3`: 1,548 ALPR records, source version and timestamp, lifecycle state, check date, direction tags, envelope flag; raw snapshot kept; history endpoint |
| 5 | Flock-only and all-ALPR scope explicit; manufacturer-unknown never misidentified | done | scope control in the UI; counts split Flock / other manufacturer / unknown; unit tests on the real M0 sample (decision 0001 D8) |
| 6 | The route engine demonstrably avoids mapped targets in validated cases | done, within stated limits | synthetic matrix (M5) and live Denver trips: Union Station to DEN found a 2-exposure route by penalties where the Standard had 7; three of five reviewed trips improved through the engine's own alternates; the method is "best among evaluated candidates" |
| 7 | All route options checked against the full assessed area and detour limits | done | every candidate is assessed over its entire path; partial-coverage candidates are never ranked; bounds are enforced and shown per option; live tests assert every avoidance option is complete and within its bound |
| 8 | Honest candidate count; no padding to three options | done | shared labels for shared paths; one card when nothing beats Standard; the search block states candidates generated and assessed |
| 9 | Directions match the selected path exactly | done | maneuvers are the engine's own for the selected path; indices cover the shape; lengths add up within 3 %; highlighting shows each step's segment; browser test keeps card, map, and directions in sync |
| 10 | Zero, unknown, stale, unassessed, no improvement, and no route are distinct states | done | labelled state blocks with test ids; stale badge; unit, browser, and mocked-state tests (M6) |
| 11 | Newly appearing source records incorporated after a validated sync | done | M2 and M7 integration matrices; live manual refresh on 2026-10-19 promoted a new snapshot that later plans cite |
| 12 | Failed or suspicious updates retain last-good data | done | outage, rate limit, HTML page, malformed and truncated JSON, quarantine, concurrent runs, failed graph build: all keep the active data (tests and live) |
| 13 | No paid AI runtime or undocumented provider API required | done | `scripts\audit.ps1 -Check keys`: no API key, token, or paid provider in code, configuration, or the env example; only local database passwords |
| 14 | Personal trip data absent from persistent default logs, URLs, and storage | done | log audit (zero hits for coordinates, address, viewport, landmark names in all container logs after real requests), browser privacy suite (no storage, cookies, service worker, or coordinates in the address bar), redaction filter tests, POST bodies only |
| 15 | External address and map data flow disclosed and approved | done | no external address or tile provider at runtime (approved 2026-10-15); egress audit shows only the sync worker can reach the internet; disclosures in `docs/PRIVACY_AND_DATA_FLOW.md` and the UI status strip |
| 16 | Map, data, and asset attribution and public-service policies documented | done | `docs/ATTRIBUTION.md`, `docs/DATA_SOURCE_REGISTER.md`, attribution strings in the footer, map, Data Health, print, and export |
| 17 | Unit, integration, browser, privacy, and synthetic routing tests pass | done | see section 2 |
| 18 | Real-world pilot checks and unvalidated limitations recorded honestly | done | sections 3 and 5 |
| 19 | User guide and recovery procedures work on a clean local installation | done (second attempt; the first found a defect, now fixed) | section 4 |
| 20 | The owner approves any public deployment separately | open by design | no public deployment exists; the service boundary is unchanged; both need separate approval |

## 2. Test suites executed for this audit (2026-10-19)

| Suite | Result |
|---|---|
| Backend in the container (unit, contract, integration on PostGIS, live Denver cases, pilot trips) | 167 passed (including the eleven pilot trip cases) |
| Backend on the host (integration and live cases skipped) | 125 passed, 42 skipped |
| Frontend type check and Vitest | 52 passed |
| Playwright at 390, 768, and 1440 px (smoke, planning, experience, operations, privacy, screenshots, WebGL probe) | 78 passed in 1.3 min with no page errors (smoke, planning, experience, operations, privacy, screenshots, WebGL probe at 390, 768, and 1440 px) |
| Smoke test with restart on the split networks and release-candidate images | passed: the snapshot and the graph survived the restart |
| Release audit script (`scripts\audit.ps1`) | keys clean; egress as designed; zero trip text in logs; restore counts identical |

## 3. Real Denver planning cases (stationary, public landmarks only)

The pilot fixture set `data/fixtures/pilot_trips.json` holds nine planned trips and two expected rejections. Results on
the 2026-10-19 snapshot and the graph built 2026-10-19T20:02:35Z (counts describe mapped records and change with every
snapshot; they are printed by the live test, never asserted):

| Trip | Covers | Search | Standard route | Camera-aware alternatives |
|---|---|---|---|---|
| Union Station to Denver Zoo | downtown to City Park across the Capitol corridor | completed, 1 routing call, 0.15 s | exposure 4, 618 s | Balanced and Fewest mapped share one path: exposure 0 at +113 s |
| Capitol to Washington Park | arterial south of downtown | completed, 1 call | exposure 0, 571 s | nothing to avoid; the Standard card carries all three labels |
| Downtown one-way grid | short trip inside the one-way grid | completed, 1 call | exposure 0, 184 s | nothing to avoid |
| Union Station to DEN | city edge, interstate ramps, the airport arm | completed, 5 calls, 0.72 s | exposure 7, 1,669 s | Balanced exposure 4 at +340 s; Fewest mapped exposure 2 at +734 s (found by penalties) |
| Cherry Creek to Highlands | diagonal through Speer Boulevard | completed, 1 call | exposure 4, 609 s | shared path: exposure 0 at +61 s |
| Zoo to Cherry Creek mall | Colorado Boulevard, a divided road with frontage access | completed, 1 call | exposure 0, 477 s | nothing to avoid |
| Union Station to Coors Field | a few blocks in the ballpark district | completed, 1 call | exposure 0, 120 s | nothing to avoid |
| Botanic Gardens to Union Station | Capitol Hill to the downtown grid | completed, 2 calls, 0.24 s | exposure 4, 582 s | shared path: exposure 0 at +70 s |
| Washington Park to Lowry | both ends in Denver with the Glendale enclave between them | completed, 1 call | exposure 4, 859 s | shared path: exposure 0 at +49 s |
| Union Station to Red Rocks | destination outside the service boundary | `OUTSIDE_SERVICE_AREA`, as expected | | |
| Same place twice | identical start and destination | `VALIDATION_ERROR`, as expected | | |

Every displayed option was road-legal by the engine's own edge attributes (no backward traversal, drivable uses only,
destination-only edges only at the ends), every avoidance option was fully assessed with lower exposure than its Standard
route and within its detour bound, all geometries were distinct, and endpoint snapping stayed within 117 m (Coors Field).

Review-matrix coverage (roadmap 16): downtown one-way streets, major-road ramps (I-25, I-70, Peña Boulevard), a divided
road (Colorado Boulevard), city-edge trips and the airport arm, short trips, a same-location request, an outside-area
destination, and a trip with no suitable alternative. Not covered live: a destination that is physically unreachable
inside the service boundary (the engine snaps to the nearest drivable road; the no-route state is covered by the contract,
synthetic, and mocked browser tests).

## 4. Fresh-install test

Executed twice on 2026-10-19 from a clean `git clone` of the repository into an empty folder, as a separate Compose
project (`COMPOSE_PROJECT_NAME=deflockfresh`, own volumes and networks) on port 3100, with the geocoder skipped
(`scripts\bootstrap.ps1 -SkipGeocoder`; the 17-minute Colorado import was verified on this machine in M1 and M3).

- **Attempt 1 (commit f162136) failed and was the most useful result of the audit:** the graph build stopped in
  `valhalla_build_timezones`, which downloads the timezone boundary shapefile from GitHub, because the network split had
  put the `graph-build` job on the internal network. The main stack had not shown this (its graph was rebuilt before the
  split). The job now joins the egress network, and the download is disclosed in the privacy flows, the attribution page,
  and the runbook (commit 034a3cb).
- **Attempt 2 (commit 034a3cb) passed:** images built from cache, migrations applied, the extract downloaded and verified,
  the graph built in 136 s, the basemap extracted, the fonts and sprites downloaded, the first camera snapshot
  published with one public query, the associations precomputed, the stack started, and the bootstrap's own smoke test
  passed; `scripts\smoke_test.ps1 -CheckRestart` then passed against the fresh project on port 3100, including the restart
  persistence check. Bootstrap took 322 s and the whole test 339 s including teardown. The scratch project's
  containers, networks, and volumes were removed afterwards; the main stack was untouched throughout.

The documented first-time setup therefore works on a clean clone with nothing installed on the host but Docker Desktop
and Git, provided the machine can reach Geofabrik, GitHub, Protomaps, and the Overpass API during setup.

## 5. Performance measured on the pilot machine

Measured with `scripts\audit.ps1 -Check perf` on 2026-10-19 after the release-candidate images and the split networks
were in place (roadmap 16 targets in brackets):

| Measurement | Result |
|---|---|
| Cold start: stopped containers to edge, web, api, db, and valhalla healthy | 19 s |
| First plan after the cold start (three preferences) | 353 ms |
| Plan endpoint over 27 pilot-trip requests, warm | p50 104 ms, p95 717 ms, max 757 ms [target: about 3 s reference, about 15 s full comparison] |
| Search elapsed inside the API | p50 101 ms, p95 711 ms; 42 routing calls for 27 plans; every search completed within budget |
| API process memory | 125 MB resident; database 27 MB on disk |
| Container memory at rest | geocoder 856 MiB, valhalla 148 MiB, api 104 MiB, camera-sync 83 MiB, db 37 MiB, web 35 MiB, edge 4 MiB |

Earlier measurements that still hold: Colorado graph build 214 to 293 s with about 3 GB peak memory; geocoder import about
17 min and 9.5 GB; camera sync one query of about 1 MB; association precompute 10 to 12 s for 1,285 records; forced graph
rebuild 268 s end to end; graph rollback about 25 s.

## 6. Privacy audit summary

- Network: `web`, `api`, `db`, `valhalla`, and `geocoder` have no route to the internet (internal Docker network); only
  `camera-sync`, the setup jobs, and the port-publishing edge join the egress network. Probed per container on 2026-10-19.
- Logs: nginx access log off; the API logs method, path template, status, and duration; a redaction filter guards against
  accidental leaks; after a plan, an address search, a reverse lookup, a camera viewport query, and an outside-area plan,
  no coordinate, address, bounding box, or landmark name appeared in any container log.
- Browser: a full session makes same-origin requests only, sends trip details in POST bodies only, writes nothing to
  storage, sets no cookie, registers no service worker, and keeps coordinates out of the URL; Clear trip empties the page.
- Storage: the database holds public camera records, snapshot metadata, diffs, association caches, and sync job rows;
  the restore check showed the whole database is 825 KB in a compressed dump. No table or file holds a trip.
- Metrics: kept in the API process only, keyed by route template, with no trip text (asserted by tests).

## 7. Source-policy review

| Source | Policy point | Status |
|---|---|---|
| Overpass API | shared resource, identify, low load, no backend use at scale | 4 scheduled queries per day while the stack runs; manual refreshes share a 30 min cooldown; one request at a time; identifying User-Agent; 30 s pause after 429/406; bounded retries; no rotation. Pilot only: a public rollout must switch to the Geofabrik extract plus diffs (decision 0001 D7) |
| Geofabrik | reasonable download frequency | one download per weekly rebuild, checksum verified |
| Protomaps build server, GitHub assets | public downloads | one-time setup downloads |
| OSMF Nominatim and tile servers | not for application backends | not used |
| City and County of Denver boundary | as is, not for engineering purposes | endpoint-in-area decisions only; attributed separately |

## 8. Known limitations (unvalidated or by design)

- Counts describe mapped OpenStreetMap records. Unmapped, mislocated, or newly installed cameras are invisible to the
  system until contributors publish them and a validated sync runs.
- Road association is a geometric heuristic. On the 2026-10-19 snapshot 860 of 1,285 in-envelope records sit at
  intersections where a different road is within 10 m of being as close, so they stay uncertain and the uncertain count
  carries most of the signal. The ranking uses matched plus uncertain, as the roadmap defines.
- Camera orientation, line of sight, and detection range are not modelled or claimed. Direction tags are shown only.
- Routes are best among the candidates a bounded search evaluated (8 routing calls, 20 s), never a proof of a minimum.
- Travel times are the engine's estimates without live traffic; closures and restrictions on the ground take precedence.
- Text directions are not live navigation; there is no GPS tracking, rerouting, or voice guidance.
- The Overpass dependency is acceptable for a local pilot only; the register names the extract-based path for later.
- After a restart the self-hosted geocoder answers its first searches slowly while its database cache warms (seconds, not milliseconds); the health probe is a real search and the API waits up to 15 s. The browser suite hit this once during the audit when it ran straight after two restarts; a rerun on a warm geocoder passed.
- The geocoder ranks some places unexpectedly (M3: "Glendale, Colorado" returns a boulevard segment first); the inside
  or outside flag is shown so the person can judge.
- Operator scripts are PowerShell; the stack itself is platform independent, but the documented workflow is Windows.
- The automated accessibility scan found no serious or critical issues; no person using assistive technology has
  reviewed the planner yet.
- The pilot is local only: no TLS, authentication, abuse controls, backups schedule, or monitoring beyond the local
  metrics; all of these need their own work before any public deployment.

## 9. Release checklist for v1.0 (invited pilot)

- [x] All suites green on the release-candidate images (section 2).
- [x] Live pilot trips planned while stationary with legality evidence (section 3).
- [x] Fresh install from a clean clone (section 4).
- [x] Browser network, storage, and container log inspection (section 6).
- [x] Egress audit on the split networks (section 6).
- [x] Source-policy review (section 7) and attribution (`docs/ATTRIBUTION.md`).
- [x] No paid key or undocumented provider (section 1, item 13).
- [x] Restore and rollback checks: database dump restored with identical counts; snapshot and graph rollback exercised live in M7.
- [x] Known limitations recorded (section 8); wording in the UI makes no optimality, coverage, or avoidance guarantee.
- [ ] Owner reviews this evidence and decides whether to invite pilot users.
- [ ] Owner chooses a license for the repository (none is granted yet).
- [ ] Separate approval before any public deployment or service-boundary change.

## 10. What an invited pilot user should be told

The planner compares routes by mapped camera records at a stated snapshot date. It cannot see cameras that nobody has
mapped, it cannot know whether a mapped camera is pointed at them, and it cannot promise an unrecorded journey. The
Standard route is the engine's time-focused reference; the alternatives are the lowest-exposure routes found within the
chosen extra-time limit among the candidates the bounded search evaluated. Plan while stopped; road signs, closures,
and conditions take precedence. Nothing about a trip leaves the computer or is stored.
