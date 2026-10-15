# 0001 - Denver pilot: scope, geography, sources, and routing engine

- **Status:** Proposed by Milestone 0 (2026-10-15); awaiting the owner's approval before M1
- **Related:** `docs/FEASIBILITY_REPORT.md`, `docs/DATA_SOURCE_REGISTER.md`, `configs/regions/denver.yaml`, decision 0002 (Docker Compose runtime)

## Context

The owner confirmed the product (DeFlockMigration, a Denver-first web route planner that compares driving routes by potential encounters with mapped ALPR cameras) and asked for a feasibility milestone before any application code. M0 executed real data pulls and a containerized routing spike; the numbers below come from those runs.

## Decisions

### D1. Service boundary = City and County of Denver official boundary (`denver-service-v1`)
Source: Denver Open Data "County Boundary" layer, features with COUNTY='Denver', retrieved 2026-10-15 (layer last edited 2026-04-09). 400.47 km², one main polygon with ten enclave holes plus one tiny second part. The airport annexation is part of the main ring, so DEN trips are inside. Enclaves (Glendale, Holly Hills, and eight smaller ones) are outside; a trip starting there gets the `OUTSIDE_SERVICE_AREA` state with a clear message rather than a silent snap. Terms are a custom "as is / not for engineering purposes" disclaimer, attributed separately from ODbL data.

### D2. Camera-data envelope = 20 km metric buffer of the service boundary (`denver-envelope-v1-20km`)
4,385 km²; bbox W -105.34301, S 39.4341, E -104.36565, N 40.09437. M0 compared 10/15/20 km (968 / 1,181 / 1,325 mapped records). 20 km keeps edge-of-city detours inside the assessed area. Candidates that leave the envelope are excluded from privacy ranking and shown as not fully assessed.

### D3. Routing-graph coverage = Geofabrik Colorado extract, rebuilt weekly in a container
The extract outline contains the envelope with a 102 km margin. The graph's Colorado extent does not widen the service boundary. Daily diffs exist but a full weekly rebuild (about 2.5 minutes, 3 GB peak) is simpler and is the chosen cadence.

### D4. Routing engine = Valhalla pinned at `ghcr.io/valhalla/valhalla:3.9.1`
Verified on this build: hard `exclude_locations` (max 50 per request), `exclude_polygons` (max 10,000 m total perimeter, 100 vertices), soft `linear_cost_factors` (does not inflate reported time), `alternates` (max 2), explicit error codes 157/167/171 and warning 208. Legality options stay at their defaults. The former gis-ops image is archived and not used.

### D5. Avoidance mechanism order for M5
1. `linear_cost_factors` built from short linestrings along the road(s) associated with each camera record, factor configurable, for soft steering.
2. `exclude_locations` for up to 50 targeted hard exclusions per request when soft steering is insufficient.
3. `alternates: 2` on baseline and penalized requests to widen the candidate pool.
4. No engine fork, no invented parameters, no hard road-class exclusions (server keeps `allow_hard_exclusions` false).

### D6. Standard route and detour reference are defined by reported time, not by the engine's primary result
M0 showed the engine's primary route can be slower by reported time than its alternates (730.7 s vs 618.1 s on Union Station to Denver Zoo). The Standard option is the fastest-by-reported-time baseline candidate (primary plus alternates with default costing), and `T0` for the Balanced and Fewest-cameras constraints is that time. Every candidate is timed by the same engine so comparisons stay internally consistent; the UI still labels times as estimates without live traffic.

### D7. Camera source = OpenStreetMap, pilot adapter = bounded Overpass query, scale adapter = Geofabrik extract
One fixed query over the envelope's bounding box every 6 hours while the sync worker runs (4 queries/day, under 1 MB each, within the Overpass "divide by 100" guidance for regular use); identify with a User-Agent; pause 30 s on 429/406; never query per trip. Before any public rollout, switch camera ingestion to the Geofabrik extract plus diffs.

### D8. Classification rules from the real snapshot
- ALPR = `surveillance:type` (plain key) contains "ALPR" (case-insensitive), with aliases `surveillance:type=ANPR`, `camera:type=ALPR`, `surveillance=ANPR|license_plate_scanner`.
- Flock scope = `manufacturer` contains "flock" (1,293 of 1,591 records: 1,291 "Flock Safety" plus 2 "Flock"), with `brand`/`operator` Flock values recorded as evidence but not as manufacturer.
- Records matched only by Flock branding without an ALPR type (37 generic cameras, 14 gunshot detectors in the snapshot) are stored but excluded from encounter counts.
- Manufacturer absent (178 records) stays in "All mapped ALPRs" and is never shown as Flock.
- Lifecycle prefixes (`removed:`, `was:`, `destroyed:`, `disused:`) are parsed even though the snapshot contained none.
- `direction` (preferred by the wiki) and `camera:direction` are both stored raw; conflicts are flagged; neither drives exclusion in v1.

### D9. Basemap = self-hosted Protomaps PMTiles extract of the envelope (90 MB, zoom 0 to 15)
Served from a Compose container with HTTP range support; fonts and sprites self-hosted; attribution "Protomaps © OpenStreetMap". No public OSM raster tiles.

### D10. Geocoder = self-hosted Nominatim on the Colorado extract, inside Compose (pending owner approval)
Public Nominatim is not enabled (policy asks users not to submit personal data; trip endpoints are personal data). The containerized Colorado import spike's measurements are in the feasibility report. Optional TIGER address data (about 10 GB) and Wikipedia importance (about 4 GB) are not downloaded without approval.

### D11. Scope options and limits
Route preferences Standard / Balanced / Fewest mapped cameras found; camera scope "Flock-tagged ALPRs only" or "All mapped ALPRs" (default All, user choice preserved); detour defaults Balanced min(T0 + 600 s, 1.5 T0), Fewest min(T0 + 1200 s, 1.75 T0); search budget eight routing calls per trip and a 20 s planning deadline, to be tuned with measured latency (30 to 146 ms per call in M0).

## Consequences

- M1 builds the Compose skeleton (decision 0002) around these pinned sources and versions.
- Any change to the boundary, envelope, engine, or camera source gets a new numbered decision and a new version id in `configs/regions/denver.yaml`.
- Nothing here claims complete camera coverage, guaranteed avoidance, or a surveillance-free route.
