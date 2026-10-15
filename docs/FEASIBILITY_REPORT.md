# DeFlockMigration - Milestone 0 Feasibility Report

**Date:** 2026-10-15
**Scope:** Denver pilot feasibility: source policies, geography, a pinned routing-engine spike, geocoding and basemap deployment, resource costs.
**Verdict:** Feasible with open-source components, no paid API, and everything runnable through Docker on the pilot machine. Three items need the owner's decision before M1 (section 10).

Every number below was measured on the pilot machine on 2026-10-15 unless marked *inspected* (documentation only) or *unverified*.

---

## 1. What was actually done

| Activity | Status | Evidence |
|---|---|---|
| Inspected repository and host environment | executed | section 2 |
| Read provider documentation and usage policies (14 sources) | inspected | `docs/DATA_SOURCE_REGISTER.md` |
| Pulled real Denver-region ALPR records with one bounded Overpass query | executed | `data/manifests/overpass_snapshot_2026-10-15.json`, `docs/evidence/overpass_alpr_tag_summary_2026-10-15.md`, `data/fixtures/overpass_alpr_sample_2026-10-15.json` |
| Downloaded the official Denver boundary and computed the service boundary and envelope options | executed | `docs/evidence/boundary_analysis_2026-10-15.md`, `data/boundaries/*.geojson`, `configs/regions/denver.yaml` |
| Downloaded the Geofabrik Colorado extract and verified its checksum | executed | `data/raw/osm/colorado-latest.download.log` (local only) |
| Built a Colorado routing graph inside the pinned Valhalla 3.9.1 container and measured it | executed | `spikes/valhalla/results/README.md` |
| Ran a synthetic avoidance test with instructions, limits, warnings, alternates, legality evidence | executed | `spikes/valhalla/results/route_spike_2026-10-15.json`, `..._routes.geojson` |
| Extracted a Denver-envelope basemap archive from the Protomaps daily build | executed | section 6 |
| Containerized Nominatim import of the Colorado extract | executed, see section 6 for results | `spikes/nominatim/` |
| Wrote decisions 0001 (pilot scope) and 0002 (Docker Compose runtime, owner requirement received during M0) | executed | `docs/decisions/` |
| Application code, Compose stack, UI | **not started** (by design) | - |

No planet import, no TIGER or Wikipedia download, no paid service, no public deployment, no OSM edits.

## 2. Environment

- **Host:** Windows 11 Home 10.0.22631, AMD Ryzen 7 5700X (8 cores / 16 threads), 15.9 GB RAM, 224 GB free on C:.
- **Docker:** Docker Desktop engine 29.8.2, Compose v5.5.1, 16 CPUs and 8.29 GB memory allocated to the Linux VM (containers see 7.72 GiB). This allocation is the main capacity constraint for running the whole stack (decision 0002).
- **Git:** 2.55.0. The project folder is now its own repository (`main`, no commits yet). Note: the user's home directory `C:\Users\jjhod` is itself a git repository, so the project repository is nested inside it; run git from the project folder.
- **Host runtimes:** Python 3.14.6 present (used only for M0 analysis scripts); Node.js absent. Under decision 0002 neither is required to run the application, because images carry their own runtimes. Python 3.14 wheels exist on PyPI for shapely 2.2.0, pyproj 3.8.0, psycopg-binary 3.3.6, SQLAlchemy 2.1.4, GeoAlchemy2 0.20.0, FastAPI 0.143.2, Pydantic 2.14.1, httpx 0.28.1, osmium 4.3.1, Alembic 1.20.0, pytest 9.1.1 (Windows build; Linux wheels to be confirmed when the backend image is pinned in M1).
- **Pinned images:** `ghcr.io/valhalla/valhalla:3.9.1` (927.6 MB), `mediagis/nominatim:5.3.2` (1.53 GB), `protomaps/go-pmtiles:v1.31.2`.

## 3. Camera source findings

**Source:** OpenStreetMap through the public Overpass API, one fixed bounding box (39.40 N to 40.12 N, 105.40 W to 104.35 W). The first request returned HTTP 502 from the instance; the retry 70 seconds later succeeded (1,591 nodes, 786 KB, data timestamp 2026-10-15T20:18:00Z). Treat 502/429/504 as normal operating conditions in the sync worker, not as exceptions.

**What the records look like** (full tables in the tag summary):

- `surveillance:type=ALPR` on 1,538 records; 37 generic cameras and 14 gunshot detectors matched only through Flock branding and must be excluded from ALPR counts.
- Manufacturer: Flock Safety 1,291, absent 178, Axon 37, Neology 25, Motorola 18, Axis 14, Leonardo 13, Genetec 6, LiveView 4, others 5. Operators are present on 188 records (Home Depot, Boulder PD, Denver PD, Lowe's, and others).
- Direction: numeric degrees 1,439, ranges 61, multi-valued 46, absent 45; `camera:direction` on 21, disagreeing with `direction` on 5 of the 7 records with both. Orientation is stored but never used to exclude a camera in v1.
- Lifecycle prefixes: none in this snapshot; parsers still handle `removed:`, `was:`, `destroyed:`, `disused:`.
- Freshness: `check_date` on only 4 records; last-edit years 2024: 96, 2025: 703, 2026: 792. Edit time is not inspection time.
- Co-location: 98 pairs within 10 m and 228 within 25 m. Keep records separate; group for display only.
- All 1,591 elements are nodes; no ways or relations matched, so representative-point logic is not exercised by real data yet.

**Policy fit:** a 6-hourly fixed-region sync (4 queries/day, under 1 MB each) is far below the Overpass "divide by 100" guidance for regular use (100 queries, 10 MB per day). The public instance must not back a public app; the Geofabrik extract pipeline is the scale path. The camera inventory is an ODbL Derivative Database; attribution and a machine-readable export must be ready before any public use.

**Coverage:** see `docs/evidence/camera_data_coverage_statement.md`. The snapshot is a record of what contributors mapped, not of what exists.

## 4. Geography

Service boundary `denver-service-v1` from the City and County of Denver "County Boundary" layer (COUNTY='Denver'): MultiPolygon, 400.47 km² (154.6 sq mi), valid geometry, main polygon with 10 interior rings for the Arapahoe and Jefferson enclaves. All ten probe landmarks behaved as expected (Union Station, Capitol, Zoo, and the DEN terminal inside; Glendale, Holly Hills, Aurora, Lakewood, Englewood, Red Rocks outside).

| Case | Finding |
|---|---|
| Airport | The DEN annexation is part of the main exterior ring, so the airport is inside the service area and contiguous with the city. Approach roads (I-70, Peña Boulevard, E-470) run through neighbouring jurisdictions that are inside the envelope, so their cameras are assessed. |
| City edge | The 20 km envelope (4,385 km²) holds 1,325 mapped records versus 968 at 10 km and 1,181 at 15 km. Detours that leave the envelope are excluded from privacy ranking. |
| Enclaves | Glendale and Holly Hills are outside the service boundary but inside the envelope: their cameras are assessed, and a trip starting inside them gets `OUTSIDE_SERVICE_AREA`. |
| Divided roads and overpasses | *unverified in M0.* Valhalla maps `exclude_locations` to "the closest road or roads", which can catch both carriageways; the association tests in M4 (parallel frontage road, overpass, ramp) must decide this with fixtures. |
| Routing graph | The Geofabrik Colorado outline contains the envelope with a 102 km margin; the Colorado-wide graph does not widen the service boundary. |

The Overpass query box contains the 20 km envelope. Buffers were computed in EPSG:26913 (meters), never in degrees.

## 5. Routing engine spike (Valhalla 3.9.1, pinned container)

**Build** (Colorado extract, 385 MB, concurrency 8, inside the container, tiles on a named volume): config 0 s, time zones 8 s, admins 12 s, tiles 105 s, extract 2 s; peak memory 3.03 GiB; output 599 tiles, 482 MB tiles plus a 482 MB tar, 117 MB time-zone DB, 6.7 MB admin DB. Service idle memory about 55 MB; `/status` verbose confirms admins and time zones are loaded.

**Capabilities proven on this build** (details and instruction lists in `spikes/valhalla/results/README.md`):

| Mechanism | Result |
|---|---|
| `exclude_locations` (hard) | Route moved 2,140 m away from the synthetic target with valid instructions; 51 points returns error 157 (limit 50). |
| `exclude_polygons` (hard) | 80 m box produced the same detour; 12 km perimeter returns error 167 (limit 10,000 m, 100 vertices). |
| `linear_cost_factors` (soft) | factor 1 reproduced the reference exactly; factor 50 produced the detour; factor 1000 on a forced segment left the reported time unchanged (no ETA contamination). |
| `alternates: 2` | Two genuinely different routes (overlap 0.146 and 0.056). |
| Warnings | Hard road-class exclusions are ignored with warning 208; an oversized location radius produced no warning. |
| Legality | `trace_attributes` over the avoidance routes: 246 edges, none traversed backward; uses were road (241) and destination driveway (5). Engine defaults `ignore_oneways`, `ignore_restrictions`, `ignore_access`, `ignore_closures` are kept false. |
| Latency | 30 to 146 ms per warm request for 6 to 40 km trips; responses 7 to 22 KB. A 20 s planning deadline for eight calls is comfortable. |
| Errors | Outside-graph destination returns error 171 "No suitable edges near location". |

**Design-changing finding:** the engine's primary route is not always its fastest by reported time (Union Station to Denver Zoo: primary 730.7 s via I-25/I-70, alternates 627.4 s and 618.1 s on surface streets; the pattern repeated in reverse). `use_highways` 0.0 or 0.3 returned the 627 s route; disabling hierarchy pruning changed nothing; `shortest` returned a 4.99 km route reporting 542.9 s. Valhalla minimises an internal cost (turn, road-class, and other preferences) that the reported time excludes. Decision 0001 D6 therefore defines the Standard route and `T0` as the fastest reported time among baseline candidates, so an avoidance route is never shown as faster than Standard by accident.

**Also observed:** in a one-way downtown grid, excluding a single point on Stout Street moved the whole route to 17th, Broadway, and Colfax rather than producing a small local detour. Candidate assessment must always cover the complete new path.

## 6. Geocoding and basemap deployment

### 6.1 Address lookup

- **Public Nominatim:** not enabled. Its policy caps use at one request per second, forbids client-side autocomplete, requires identification, states "Applications and services whose primary function is related to geocoding must run their own service", and asks users not to submit personal data. Trip endpoints are personal data. If the owner ever wants it for a tiny pilot, it needs explicit approval and a submit-only search with caching.
- **Self-hosted Nominatim (recommended):** `mediagis/nominatim:5.3.2`, Colorado extract mounted read-only, no TIGER, no Wikipedia, `IMPORT_STYLE=full`, PostgreSQL memory settings reduced to fit the 8 GB Docker allocation (shared_buffers 1 GB, maintenance_work_mem 1 GB, effective_cache_size 3 GB). First start failed because the image's entrypoint runs `chown -R` on `/nominatim`, which rejects a read-only mount there; mounting the extract at `/pbf` fixed it. Import started 2026-10-15T20:42:52Z.
  - **Measured result:** see section 6.3 (17 minute import, 9.8 GB database, 5.2 GiB peak memory, correct results for all tested landmarks and public addresses).
  - **House numbers:** OSM address coverage in Denver is what the import provides; the TIGER address dataset ("The entire US adds about 10GB to your database.") would improve house-number interpolation but is a large download that needs approval.
  - **Photon** could be added later for typo-tolerant search; not required for v1.

### 6.2 Basemap

- **Public OSM raster tiles:** not used (policy forbids bulk download and offline use, blocks unidentified apps, no SLA; also a privacy leak of viewport positions).
- **Self-hosted PMTiles (recommended, executed):** `pmtiles extract` of the 20 km envelope at zoom 0 to 15 from the 2026-10-15 Protomaps daily build took 9.7 s, 50 HTTP range requests, and produced a 90.3 MB archive (9,616 tile entries, Protomaps Basemap 4.15.2, OSM data of 2026-10-15T04:00:00Z). The file is stored locally because Protomaps discourages hotlinking. Serving needs only a static HTTP server with range requests inside Compose; MapLibre uses the `pmtiles://` protocol; fonts (OFL) and sprites (MIT) are self-hosted; attribution "Protomaps © OpenStreetMap". Monthly refresh is sufficient for a basemap.

### 6.3 Self-hosted Nominatim import result (measured)

- **Run:** `mediagis/nominatim:5.3.2`, Colorado extract (data as of 2026-10-14T20:20:43Z per `/status`), `IMPORT_STYLE=full`, 8 threads, no TIGER, no Wikipedia, no postcode file, PostgreSQL 16 and PostGIS 3.4 inside the container, extract mounted read-only at `/pbf`.
- **Duration:** container start 20:42:52Z, osm2pgsql load 299 s, indexing from 20:49:15Z, API serving at 20:59:47Z: **16 min 55 s** end to end.
- **Resources:** peak container memory 5.19 GiB (60 s samples); database volume 9.77 GB after import. The 8 GB Docker allocation was sufficient, but the import must run as a standalone setup job, never alongside the graph build or the full stack.
- **Queries (warm, local, 16 to 61 ms each):** landmarks resolved to the expected places (Union Station, Denver Zoo, Denver International Airport, Red Rocks Amphitheatre, Washington Park). Public street addresses resolved through OSM features carrying that address: 1437 Bannock St returned the Denver City & County Building; 1701 Wynkoop St the Crawford Hotel inside Union Station; 2300 Steele St the Denver Zoo; 200 E Colfax Ave a feature at the Capitol. "Colorado State Capitol, Denver" ranked the Capitol Annex first; "Glendale, Colorado" returned a road in Glendale before the municipality. A nonexistent street returned zero results (no false positive). Reverse geocoding returned a Capitol-grounds feature and Peña Boulevard at the airport terminal.
- **Reading:** adequate for the pilot's submit-only address search and landmark search, with candidate confirmation in the UI covering the ranking quirks. House numbers that have no OSM feature will not resolve without TIGER interpolation data (about 10 GB more database plus a large download, approval needed). M3 adds Denver address test cases.
- Results file: `spikes/nominatim/results/queries_2026-10-15.json`; run notes in `spikes/nominatim/results/README.md`.

## 7. Resource and cost summary

| Component | Disk | Memory | Time | Money |
|---|---|---|---|---|
| Colorado extract | 385 MB | - | 27 s download | none |
| Valhalla graph volume | about 1.1 GB (tiles + tar + time zones + admins) | 3.0 GiB peak during build, about 55 MB idle service | 2.1 min build | none |
| Valhalla image | 0.93 GB | - | one pull | none |
| Basemap archive | 90 MB | negligible | 10 s extract | none |
| Nominatim image | 1.53 GB | - | one pull | none |
| Nominatim database (Colorado, full style, no TIGER) | 9.77 GB volume | 5.19 GiB peak during import; serving footprint to measure in M1 | 16 min 55 s import | none |
| Camera snapshot | under 1 MB per sync | negligible | about 70 s per Overpass query | none |
| PostGIS, API, web, worker images | to be measured in M1 | expected under 2 GB combined | - | none |

Software and data licenses cost nothing (MIT, BSD, GPL, ODbL, OFL). Running costs are the owner's electricity and hardware. A public launch would add hosting, bandwidth, and operations costs that this report does not estimate.

## 8. Docker Compose implications (owner requirement received during M0)

Decision 0002 makes Compose the primary runtime. M0 confirms it is practical: the graph build, the geocoder import, and the basemap extract already ran entirely inside pinned containers with named volumes, and the host needed only Docker and Git. The memory plan for `docker compose up` on this machine: PostGIS under 1 GB, Valhalla under 1 GB with Colorado tiles, Nominatim 1 to 2 GB, API/web/worker/basemap under 1 GB combined, which fits the 8.29 GB allocation if the graph build (3.0 GiB peak) and the geocoder import (5.2 GiB peak) never run at the same time as each other or as the full stack (both are one-time `setup` profile jobs in M1).

## 9. Risks and unverified items

1. **Camera-to-road association accuracy** (parallel roads, ramps, overpasses, divided carriageways) is untested; M4 fixtures decide it.
2. **Divided-road behaviour of `exclude_locations`** may exclude both directions; linear cost factors on a single carriageway are the likely answer, untested.
3. **Reported time vs internal cost**: route comparison relies on Valhalla's time estimate, which excludes its own turn and preference costs; all candidates share the same bias, but ETAs remain estimates without traffic.
4. **Public Overpass availability**: a 502 occurred on the first M0 request; the sync must keep the last good snapshot and retry politely.
5. **Geocoder coverage without TIGER**: the tested landmarks and public addresses resolved, but a house number resolves only when OSM has a feature with that address, and ranking has quirks (Capitol Annex before the Capitol, a road before the town of Glendale). M3 needs Denver address test cases and candidate confirmation in the UI.
6. **Docker memory headroom** for the full stack plus a browser is thin on an 8 GB allocation; M1 must measure it and document how to raise the allocation.
7. **Frontend stack versions** (Next.js, MapLibre, pmtiles) are not yet pinned or tested.
8. **OSM data completeness**: 178 records lack a manufacturer; directions are inconsistent; nothing is field-verified by this project.
9. **Nested git repository** inside the home-directory repository could confuse tooling; keep working from the project folder.

## 10. Decisions requested from the owner before M1

1. Approve decision 0001 (D1 to D11): boundary source, 20 km envelope, Colorado graph, Valhalla 3.9.1, avoidance mechanism order, Standard-route definition, camera source and classification rules, scope defaults.
2. Approve decision 0002 as recorded (Docker Compose primary runtime) and the M1 checklist that implements it.
3. **Geocoding:** approve a self-hosted Nominatim service inside Compose built from the Colorado extract (measured: 17 minute one-time import, 9.8 GB database volume, 5.2 GiB peak memory during import), and say whether the optional TIGER address download (about 10 GB more in the database) is allowed. Confirm that no external geocoder is enabled.
4. **Basemap:** approve the self-hosted PMTiles basemap (90 MB extract, monthly refresh) with no external tile requests.
5. Confirm whether M0 artifacts should be committed to the project repository now (nothing has been committed).

## 11. Public-source calls made during M0

Overpass main instance: 2 (one 502, one success). Geofabrik: 4 small requests plus one 385 MB extract. Denver Open Data (ArcGIS): 3. Protomaps build server: 99 range requests (dry run plus extract, 95 MB transferred). GitHub, Docker Hub, and Protomaps metadata: 5. Image registries: 3 pulls. Documentation pages read by research agents: about 40. No calls carried a trip, an address, or personal data.

## 12. Files produced in M0

- `docs/FEASIBILITY_REPORT.md`, `docs/DATA_SOURCE_REGISTER.md`, `docs/decisions/0001-denver-pilot.md`, `docs/decisions/0002-docker-compose-primary-runtime.md`, `docs/plans/M1_CHECKLIST.md`
- `docs/evidence/overpass_alpr_tag_summary_2026-10-15.{md,json}`, `docs/evidence/boundary_analysis_2026-10-15.{md,json}`, `docs/evidence/camera_data_coverage_statement.md`
- `data/manifests/overpass_snapshot_2026-10-15.json`, `data/manifests/versions_m0_2026-10-15.json`, `data/fixtures/overpass_alpr_sample_2026-10-15.json`
- `data/boundaries/denver_service_boundary_v1.geojson`, `data/boundaries/denver_camera_envelope_v1.geojson`, `data/boundaries/raw/*` (source download and metadata)
- `data/raw/overpass/denver_alpr_envelope_query.overpassql` (raw response kept locally, not committed)
- `configs/regions/denver.yaml` (proposed)
- `scripts/m0/analyze_overpass_snapshot.py`, `scripts/m0/analyze_boundary.py`
- `spikes/valhalla/{container_build.sh,run_build.sh,route_spike.py,route_spike_extra.py}`, `spikes/valhalla/results/*`
- Local-only (ignored): `data/raw/osm/`, `data/raw/basemap/`, `spikes/*/output/`, Docker volumes `deflock_valhalla_spike` and `deflock_nominatim_spike_db`
- Roadmap addendum recording the Docker Compose requirement in `docs/plans/DeFlockMigration_Claude_Build_Roadmap.md`
