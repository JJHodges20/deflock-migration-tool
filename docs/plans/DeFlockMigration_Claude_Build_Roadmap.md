# DeFlockMigration
## Denver Pilot - Claude Code Implementation Roadmap

**Document version:** 1.0  
**Prepared:** October 15, 2026  
**Status:** Proposed implementation specification; not an implemented or field-tested routing system.  
**Platform:** Responsive web application first; native/live navigation later.  
**First service area:** Denver, Colorado, with a maintained surrounding analysis buffer.  
**Product purpose:** Help people compare practical driving routes that reduce potential encounters with mapped automated license-plate-reader cameras.

> Product promise: Find efficient alternatives around mapped cameras, explain the detour, and make data limitations visible. Never promise an unrecorded journey or label an area surveillance-free.

---

## 1. Confirmed requirements and proposed defaults

### Confirmed by the project owner

- The application is named **DeFlockMigration**.
- A person enters a starting location and destination.
- The application should find an efficient route that avoids mapped Flock cameras where practical.
- Camera locations should come from open databases and refresh as records are added or changed.
- Begin with Denver and expand only after the pilot works.
- Provide a simple, clean interface and street-by-street directions.
- Claude Code will implement the application in verified milestones.

**Addendum confirmed by the project owner on October 15, 2026 (Docker Compose is the primary runtime):**

- Docker Compose must be the primary way to run the entire application, not merely the database or routing engine. Containerize the frontend, backend, PostgreSQL/PostGIS, Valhalla, and the camera-update worker, plus any selected self-hosted geocoding and map-serving components.
- Run database migrations, initial data imports, and road-graph builds through containerized commands or setup jobs.
- Normal application use must not require separately installing Python, Node.js, PostgreSQL, or Valhalla on the host computer.
- Persist database contents and downloaded/built geographic data across normal container restarts; never delete them during ordinary shutdown.
- Document first-time setup separately from everyday startup. After initialization, the intended startup command is `docker compose up`.
- Verify service readiness, persistence, restart behavior, and a complete browser-to-backend routing request before marking Docker setup complete.
- The existing M0 feasibility review and approval gates are preserved. See `docs/decisions/0002-docker-compose-primary-runtime.md`.

### Recommended defaults, not previously approved requirements

- Begin with ordinary passenger-car trip planning, not an actively tracking navigation app.
- Offer **Standard**, **Balanced**, and **Fewest mapped cameras found** route preferences.
- Offer a visible camera scope: **Flock-tagged ALPRs only** or **All mapped ALPRs**. Recommend the latter, including unknown manufacturers, without silently changing the user's selection.
- Start with local development and an invited pilot, not an unrestricted public service.
- Use open-source software and avoid mandatory paid APIs. Hosting, storage, electricity, and third-party services can still have costs.
- Do not require an LLM, chatbot, or paid AI API. Routing and geometry belong in deterministic software.
- Keep personal trips ephemeral by default; retain public camera-data snapshots separately.

Ask for approval before adding paid services, making the app public, enabling external address lookup, changing the service area, or adding persistent personal trip history. Do not ask again about the already confirmed name, purpose, or Denver-first scope.

## 2. What Version 1 must do

The first complete release is **DeFlockMigration v1.0 - Denver Route Planner**.

A successful journey through the application:

1. The user opens a map centered on the Denver pilot area.
2. They type and confirm two addresses or place two map pins.
3. They select the camera scope and acceptable extra travel time.
4. The app calculates a time-focused reference route, then evaluates avoidance alternatives.
5. It returns up to three genuinely different route options, not three differently colored copies of the same route.
6. Each option shows estimated travel time, distance, additional time, relevant mapped-camera encounters, uncertain matches, and assessment status.
7. Selecting an option updates the map and its engine-generated street-by-street directions together.
8. The user can inspect the camera evidence, source dates, and methodology without leaving the route planner.
9. Public camera records update independently of any individual's trip.

**Out of scope for v1:** live GPS tracking, background location collection, automatic rerouting while driving, voice guidance, traffic-aware ETA claims, nationwide service, accounts, payments, camera-feed access, license-plate searches, facial recognition, automated OSM edits, and interacting with or disabling camera equipment.

A planned route is advisory. Road signs, access restrictions, closures, and actual conditions take precedence.

## 3. Source strategy: consume open records, not another site's interface

### 3.1 Camera inventory

DeFlock's project documentation identifies OpenStreetMap as its underlying source for crowdsourced ALPR locations. Use the underlying records rather than scraping the DeFlock map, depending on an undocumented download endpoint, or treating DeFlock and OSM as independent corroborating datasets. [S1]

Use two replaceable ingestion adapters:

- **Pilot adapter:** a bounded Overpass query for ALPR records within the camera-data envelope, cached in the application's own database.
- **Scale adapter:** filtered regional OSM extracts and, later, managed updates. Geofabrik publishes Colorado OSM extracts and change files. [S4]

For the initial query, use the documented `surveillance:type=ALPR` classification. Preserve manufacturer, operator, direction, and lifecycle information separately. A Flock manufacturer tag alone does not establish that a device is an ALPR. OSM documentation distinguishes these concepts and identifies direction-tag inconsistencies. [S2]

In Milestone 0, inspect actual Denver records to establish supported aliases and parsing fixtures. Do not invent a current camera count, assert every mapped device is operating, or assume the map contains every installed camera.

An optional official/local-government dataset can be added only after its actual fields, license, currency, and coverage are inspected. Denver's Open Data Catalog is a candidate source for boundaries and supplementary public GIS data, not an assumed complete camera feed. [S11]

### 3.2 Updates

The product cannot discover an installation merely because it exists in the physical world. It discovers records after contributors or another permitted source publish them, upstream data becomes available, and the local sync succeeds.

Recommended starting policy:

| Data | Proposed cadence | Publication rule |
|---|---|---|
| Camera inventory | Every 6 hours while the sync service is running | Publish only a complete, validated snapshot |
| Manual camera refresh | Operator-triggered; shared cooldown | Coalesce concurrent requests into one job |
| Road graph | Weekly staged rebuild, or an approved urgent rebuild | Validate before replacing the active graph |
| Geographic boundary | Explicitly versioned | No silent expansion |
| Basemap/geocoder data | According to the selected deployment | Report their dates separately |

These intervals are product defaults, not provider guarantees. Review provider policies before enabling scheduled jobs.

Public Overpass instances are shared infrastructure and discourage apps relying on them as an end-user backend. Keep queries small and infrequent for development; move to regional extract processing or an appropriately hosted instance before a public rollout. Do not rotate IPs or providers to defeat limits. [S3]

### 3.3 Address search and map tiles

**Default design:** a `Geocoder` interface with a regional, self-hosted implementation preferred for private address lookup. Benchmark regional Nominatim during the feasibility phase; do not attempt a planet import on a development PC. Nominatim documents its self-hosted setup separately from the public service. [S13]

**Optional low-volume pilot:** the owner may deliberately enable public Nominatim after reviewing its current policy. This is not an automatically enabled free backend. Its published restrictions include an application-wide maximum of one request per second, identifying requests, caching, attribution, no client-side autocomplete, and the ability to switch services. It also warns against submitting personal/confidential data. Use a submitted Search button, not a request on each keystroke. [S7]

If no permitted geocoder is configured, map pins remain available during development, but the address-entry requirement is not complete. V1 cannot pass acceptance with only map-pin input.

MapLibre is the map renderer, not a free map-data subscription. [S9] Prefer a permitted regional tile bundle served locally; PMTiles can serve a tiled archive through HTTP range requests. Include compatible styles, fonts, sprites, and their licenses. [S14]

An external basemap can be enabled for a small pilot only with documented terms and privacy disclosure. Do not bulk-download or prefetch tiles from the public OSM raster service; its policy distinguishes ordinary interactive viewing from prohibited offline collection. [S8]

## 4. Geographic scope: three boundaries, not one

Maintain these separately in `configs/regions/denver.yaml`:

1. **Service boundary:** where users may start and end trips. Proposed default: a reviewed City and County of Denver geometry, explicitly checking airport and non-contiguous geometry handling.
2. **Camera-data envelope:** service boundary plus a proposed 20 km analysis buffer, reviewed during M0. Camera ingestion must include neighboring roads within this envelope, not only cameras inside city limits.
3. **Routing-graph coverage:** a broader Colorado extract or another tested extract that fully surrounds the camera-data envelope and preserves road connectivity.

The buffer is not a claim of camera coverage. It defines where a particular source snapshot was assessed. Store and display the actual geometry and version.

Every candidate route must be checked against the complete camera-data envelope. A detour must not win merely because it leaves the assessed area. V1 should exclude such a candidate from privacy ranking and explain why; it may still show the reference route as **not fully assessed**. Never assign a zero exposure score to the unassessed section.

Do not restrict the routing graph to a downtown rectangle. Conversely, do not silently enable every Colorado destination just because the road graph covers Colorado. The product's service boundary and the graph's extent serve different purposes.

## 5. Recommended technical architecture

| Layer | Proposed choice | Responsibility |
|---|---|---|
| Web interface | Next.js, React, TypeScript | Address entry, responsive layout, route comparison |
| Map rendering | MapLibre GL JS | Basemap, camera layer, route geometry, interactions |
| Backend | FastAPI and Pydantic | Validated requests, orchestration, response contracts |
| Geospatial persistence | PostgreSQL/PostGIS, SQLAlchemy, migrations | Public camera inventory, snapshots, spatial queries |
| Geometry | PostGIS with Shapely/pyproj where useful | Projection-safe distances and intersections |
| Driving engine | Self-hosted Valhalla | Road-valid route generation and maneuvers |
| Updates | One Python sync worker or scheduled CLI job | Public-source refresh, validation, snapshot publication |
| Tests | pytest; Vitest; Playwright | Calculations, contracts, browser flows |
| Local environment | Docker Compose; Windows/PowerShell instructions | Reproducible services and persistent public data |

Pin compatible versions after a feasibility test. Do not use floating `latest` container tags as the reproducible release baseline. Keep the first deployment small; no Kubernetes, distributed event bus, or model-serving stack.

Valhalla provides driving routes and maneuver instructions; its documentation also covers route exclusions, alternatives, and geometry-based cost factors. Verify those capabilities against the exact pinned build before depending on them. The project documents Docker deployment as a supported approach. [S5, S6]

### Dependency rules

```text
Frontend -> API -> application services -> domain logic and adapters
                                      |-> camera repository
                                      |-> routing provider
                                      |-> geocoding provider
                                      |-> exposure assessor

Sync worker -> source adapters -> validation -> staged public snapshots

Public sources never receive an individual's trip as part of camera sync.
The UI does not calculate route safety, exposure, or directions.
```

Keep the router behind a `RoutingProvider` interface. A change to a provider must not change the route-response schema or silently weaken the product's guarantees.

## 6. Proposed repository structure

Create files when their milestone needs them; do not generate hundreds of empty modules.

```text
DeFlockMigration/
|-- README.md
|-- CLAUDE.md
|-- compose.yaml
|-- .env.example
|-- .gitignore
|-- configs/
|   |-- regions/denver.yaml
|   |-- providers.yaml
|   |-- route_profiles.yaml
|   |-- data_quality.yaml
|   `-- privacy.yaml
|-- apps/
|   `-- web/
|       |-- package.json
|       |-- src/app/
|       |-- src/features/planner/
|       |-- src/features/camera-map/
|       |-- src/features/data-health/
|       |-- src/components/
|       |-- src/lib/api/
|       |-- src/styles/
|       `-- tests/
|-- backend/
|   |-- pyproject.toml
|   |-- src/deflockmigration/
|   |   |-- api/                 # routers, validation, errors
|   |   |-- application/         # plan_trip, refresh_inventory
|   |   |-- domain/              # cameras, routes, profiles, policies
|   |   |-- geospatial/          # CRS, association, proximity, coverage
|   |   |-- routing/             # Valhalla adapter, candidates, scoring
|   |   |-- geocoding/           # interface and approved providers
|   |   |-- data_sources/        # Overpass, regional OSM extracts
|   |   |-- ingestion/          # sync, validation, differences, promotion
|   |   |-- storage/            # repositories and schema migrations
|   |   |-- workers/            # single scheduler/CLI entrypoints
|   |   `-- core/               # settings, redacted logs, clocks, errors
|   `-- tests/
|       |-- unit/
|       |-- integration/
|       |-- routing_fixtures/
|       |-- privacy/
|       `-- regression/
|-- infra/
|   |-- valhalla/
|   |-- geocoder/
|   |-- basemap/
|   `-- database/
|-- data/
|   |-- boundaries/
|   |-- raw/                    # local public-source snapshots
|   |-- processed/
|   |-- road_graphs/
|   `-- manifests/
|-- scripts/
|   |-- bootstrap.ps1
|   |-- import_region.ps1
|   |-- sync_cameras.ps1
|   `-- smoke_test.ps1
|-- docs/
|   |-- PROJECT_CONTEXT.md
|   |-- IMPLEMENTATION_PLAN.md
|   |-- DATA_SOURCE_REGISTER.md
|   |-- DATA_DICTIONARY.md
|   |-- ROUTING_METHOD.md
|   |-- PRIVACY_AND_DATA_FLOW.md
|   |-- UI_SPECIFICATION.md
|   |-- TEST_PLAN.md
|   |-- USER_GUIDE.md
|   |-- DEVELOPMENT_LOG.md
|   `-- decisions/
`-- .github/workflows/
    `-- tests.yml
```

Ignore local secrets, dependencies, databases, large downloaded data, and build artifacts. Commit small sanitized public-data fixtures, licenses, schemas, manifests, and test expectations. Never commit a person's actual trip history.

## 7. Data contracts and persistent records

### Camera record

Use a canonical source key such as `osm:node:12345`; include the object type so node, way, and relation IDs cannot collide.

| Field group | Required information |
|---|---|
| Identity | Internal camera ID, source object type/ID/version, source URL |
| Location | Geometry, coordinate system, geometry quality, representative-point method if applicable |
| Classification | Raw ALPR tags, normalized manufacturer, operator, classification evidence |
| Orientation | Raw direction fields, parsed orientation if unambiguous, unresolved conflicts |
| Lifecycle | Mapped status, lifecycle evidence, removal/retirement history |
| Time | Source edit time, source dataset time, first/last locally seen time, downloaded time, field-check date only if supplied |
| Provenance | Snapshot ID, raw payload hash, source license, parser version |
| Review | Parse warnings, match status, unresolved ambiguity |

A record's source edit time is not a physical installation or inspection date. Refreshing the feed does not make every camera recently field-verified.

For non-point geometries, preserve the original shape and mark approximate representative points. Do not pretend a relation centroid is the camera lens position.

Do not merge different devices simply because their coordinates are close. Preserve individual records; optionally group them into explicitly labeled sites for display.

### Road association

Store `camera_id`, `graph_version`, routing edge/way references, candidate geometries, possible direction, matching method, ambiguity flags, and reviewed evidence. Treat association IDs as graph-version-specific and rebuild them after graph replacement.

Do not treat a closest road as conclusively monitored. Parallel roads, bridges, ramps, walls, and roadside placement must remain explicit test cases.

### Snapshot and sync records

Store `snapshot_id`, region and query identity, fetch status, upstream timestamp, downloaded timestamp, element count, content hash, parser version, quality results, previous active snapshot, and promotion state.

Maintain job status and added/changed/no-longer-present counts. Keep edit history sufficient to explain a changed recommendation. Do not collect OSM contributor personal profile information unless operationally required; strip unnecessary editor identity fields from published exports.

### Route response

Every successful route option must include:

```text
route_id                         # random, ephemeral ID
profile                          # standard / balanced / fewest_mapped
geometry                         # typed GeoJSON LineString
estimated_duration_seconds       # no live-traffic claim
length_meters
extra_duration_seconds
extra_distance_meters
matched_camera_record_count
uncertain_nearby_camera_count
counting_method_version
camera_scope                     # flock_only / all_alpr
camera_snapshot_id
camera_source_as_of
camera_downloaded_at
road_graph_version
assessment_coverage_status
search_status                    # completed / budget_exhausted / partial
warnings[]
maneuvers[]                       # generated by routing engine
```

Expose matched camera IDs on demand for explanation. Counts describe modeled encounters with mapped records, not observed recordings, people, or license plates. Do not turn those counts into a fabricated probability of being recorded.

## 8. Camera refresh algorithm

1. Acquire a region-scoped sync lock. Use one scheduler, not one per browser session or API worker.
2. Load a fixed approved query and the full camera-data envelope; never derive the query from a user's current route.
3. Fetch with a real application identifier, timeouts, bounded backoff, and provider-policy-aware limits.
4. Detect HTTP errors, rate limits, HTML challenge pages, malformed JSON, upstream error remarks, partial responses, and missing completion information. Do not bypass access controls.
5. Save a public raw snapshot and its manifest. Normalize records and preserve unknown fields separately.
6. Validate coordinates, region, schema, classification, IDs, and timestamps; calculate a diff against the active snapshot.
7. Quarantine anomalous results. A very large count reduction or unexpected empty response must be reviewed or corroborated, not silently published.
8. Atomically promote only a valid snapshot. Retain the last known good version on failure.
9. Refresh camera-road associations for affected records and invalidate assessment caches by snapshot/graph version.
10. Publish the new Data Health state. Existing route results retain the versions used to calculate them and become visibly outdated rather than changing underneath the user.

No longer present in a successful same-scope query means **no longer mapped in this source snapshot**. It does not prove physical removal. Explicit lifecycle evidence and mapping changes should remain distinguishable. Define the conservative treatment of unresolved disappearances in `data_quality.yaml` and surface warnings.

Track source additions as **newly mapped records**, not "new cameras installed today."

## 9. From camera points to potential route encounters

### Stage A: reproducible proximity assessment

Use a meter-based geometry operation and a versioned candidate radius to find potentially relevant cameras near a complete route. A proposed starting radius such as 50 m is only a review parameter; it is not the device's detection range and must be assessed with 25/50/100 m sensitivity checks.

PostGIS geography distance functions use meters; ordinary geometry distances use the geometry's coordinate-system units. Make unit conversion explicit and test it. Never buffer longitude/latitude as though degrees were meters. [S12]

### Stage B: road-aware assessment

Use routing-edge candidates, road geometry and attributes, and trustworthy mapped context to improve the association. Record both an associated-road result and unresolved nearby cases. Do not claim actual line of sight based on the map alone.

For v1, do not filter away a nearby device merely because the direction tag seems to face the other way. Device orientation is not automatically the same as traffic direction, and front/rear capture assumptions may be wrong. Directional exclusion can be introduced only after explicit fixtures and evidence validate it.

Count each canonical record once per route for the headline count. Retain repeated passes and grouped-site details separately. Keep a device with ambiguous road association visible as an uncertainty, not silently zero.

**Do not produce a coverage percentage for physical cameras.** A geometric in-envelope fraction is allowed only with the label "portion of route inside our assessed data area," which says nothing about how many real devices have been mapped.

## 10. Route construction: real avoidance, not just a camera overlay

### 10.1 Reference route

Request a normal driving route with no camera preference using the pinned Valhalla build. Keep its actual geometry and instructions as the reference for detour calculations. Label it **Standard route**, not a guaranteed globally fastest route.

Keep normal turn/access constraints. Do not permit wrong-way travel, pedestrian paths, closed/private through-roads, or prohibited turns to improve the camera metric. Test the exact selected engine behavior, including endpoint access, rather than assuming every desired restriction is covered by a soft penalty.

### 10.2 Native avoidance capability probe

Valhalla documents exclusions that map points to roads, polygon exclusions, alternatives, and geometry-based `linear_cost_factors`. Alternatives are not guaranteed and have request-mode limitations. [S5]

M0 must prove which options the pinned engine supports and whether they affect the intended road segments without distorting ETA. Reject or surface warnings about ignored/clamped inputs. Do not invent a `camera_penalty` API parameter.

Recommended implementation order:

- Use tested native geometry-based penalties when available and correctly matched.
- Otherwise use bounded exclusion-based candidate generation, keeping its approximations explicit.
- Do not fork the routing engine or create a new turn-aware road router for v1 without approval.

### 10.3 Bounded candidate search

A practical v1 algorithm:

1. Generate the reference route and available baseline alternatives.
2. Assess all of them against one pinned camera snapshot and one graph version.
3. Identify avoidance targets along the current candidates using the tested association policy.
4. Request additional routes with supported road penalties or targeted exclusions. Avoid large arbitrary circles that can block parallel roads and unrelated crossings.
5. Assess each new route against the entire maintained envelope, not only the cameras found on the original route.
6. Remove invalid, out-of-envelope-for-ranking, over-budget, and duplicate candidates.
7. Iterate within a configured budget, preserving the best previously valid candidates.
8. Rank the resulting candidates and return up to three meaningful choices.

Suggested initial limits: eight routing calls per trip, one bounded planning deadline, and strict payload-size limits. These must be tuned against measured local performance. A timeout returns a labeled partial search or a clearly unassessed reference route, not invented alternatives.

Never force exactly three results. When two preferences choose the same path, display one option with multiple applicable labels.

### 10.4 What "efficient" means

Let `T0` be the reference duration and `T(r)` a candidate duration, both in seconds. Let `E(r)` be the versioned conservative encounter count, incorporating associated and unresolved candidates without double-counting a camera.

Use explicit constraints and labels rather than a mysterious privacy score:

```text
Standard:
    the routing engine's time-focused reference

Balanced:
    minimize E(r) among generated routes satisfying
    T(r) <= min(T0 + 600 seconds, 1.50 * T0)
    then prefer shorter duration and distance

Fewest mapped cameras found:
    minimize E(r) among generated routes satisfying
    T(r) <= min(T0 + 1200 seconds, 1.75 * T0)
    then prefer shorter duration and distance
```

The thresholds are proposed UI defaults and should be configurable. Both the absolute and relative constraints apply; explain this for short trips. Handle `T0 = 0` without division by zero.

This is **best among evaluated candidates**, not a proof of a globally optimal camera-minimum path. Report search-budget exhaustion and method version.

If camera costs influence search, keep those artificial costs separate from physical travel time. Do not inflate the displayed ETA by adding a camera penalty as though it were real driving time.

### 10.5 No satisfactory route

Use specific outcomes:

- **No lower-exposure route found within your detour limit.** Offer a deliberate increase of the limit.
- **Camera assessment unavailable.** A standard route may still be offered, visibly unassessed.
- **Route leaves the assessed area.** Do not advertise its camera count as complete.
- **Selected endpoints make exclusions infeasible.** Explain rather than snapping the destination far away or quietly dropping exclusions.
- **No drivable route found.** Do not draw a straight line and call it a route.

Zero modeled encounters should read: **"No mapped encounters detected by this assessment. Unmapped or mislocated cameras may still be present."**

## 11. Street-by-street directions

Use the routing engine's maneuver output for the exact selected path. Valhalla documents trip legs, route shapes, and maneuver narratives. [S6]

Display instruction, road name when supplied, distance to the next maneuver, and the relevant map highlight. Handle missing road names, ramps, roundabouts, destination instructions, units, and multiple legs without inventing text.

When a user selects another route, geometry, distance, duration, exposure, and instructions must switch as one state update. Discard late responses from superseded requests.

Allow printing of the selected route and directions. A later GPX/GeoJSON download should preserve geometry and timestamps and warn that another navigation application may recalculate a different path. Do not claim a Google/Apple Maps handoff preserves avoidance.

Text instructions are not yet live navigation. Ask users to plan while stopped; do not imply the app tracks road progress or closures.

## 12. Clean interface specification

### Main planner

Desktop: a focused left-hand planning panel and a large map. Mobile: a full-width map with an accessible bottom sheet for inputs and route cards. Preserve input and selected-route state as the layout changes.

Primary controls:

- Start and destination with explicit Search/Confirm, swap, and map-pin alternatives.
- Route preference and clearly visible Flock-only/all-ALPR scope.
- Maximum extra travel time, with advanced relative-limit controls.
- Plan route, cancel request, clear trip, and show/hide cameras.
- Optional "Use my location" only after a deliberate user action and browser permission; no background tracking.

Route cards should show time, distance, extra time, known mapped encounters, ambiguous matches, and data status. Distinguish selected paths with line pattern and width as well as color. No unlabeled red/green safety grading.

### Camera details

Show manufacturer only when supported, mapping/source link, raw mapped lifecycle, source edit/check times, and association uncertainty. Do not display live vehicle records; they are neither needed nor part of the source inventory.

### Data Health

Show sync state, latest successful download, source dataset timestamp, last failure, counts/differences, active graph version, service boundary, and data envelope. Manual sync is an operator action, not an unauthenticated public trigger.

### Design approach

Use restrained typography, clear spacing, readable road labels, a neutral base palette, one accent color, and semantic warning colors. This is a proposed visual direction; the owner has not chosen a specific palette for this project. Avoid copying DeFlock's logo or presenting this independent app as an official DeFlock/Flock product.

Include keyboard access, visible focus, useful map alternatives in list form, screen-reader labels, reduced-motion support, and adequate contrast. Test approximately 390 px, 768 px, and 1440 px viewports. Treat these as QA targets rather than exclusive supported resolutions.

### Required non-happy-path states

Loading; canceling; no address match; ambiguous address; outside pilot; geocoder unavailable; no camera snapshot; stale camera data; partial sync quarantined; route engine unavailable; no improvement found; incomplete geographic assessment; unsupported route settings; empty but validated inventory; and map rendering failure with directions still readable.

## 13. Privacy and security requirements

Privacy is part of the implementation, not just the app's name.

- No accounts or trip history in v1. Origins, destinations, route shapes, and exact geolocation remain ephemeral application/session data.
- No analytics pixels, session replay, advertising SDKs, or automatic error-report payloads containing trip data.
- Use POST bodies for trip and address requests; redact those bodies, query strings, and routing-provider payloads in application, reverse-proxy, and container logs.
- Disable engine/request debug logging in normal mode. Redact camera-viewport bounding boxes and disable or minimize identifying tile-request access logs as well. Test redaction, including exceptions and timeouts.
- Persist public camera data, not personal journeys. Use random request IDs; a coordinate hash is not an anonymization guarantee.
- Keep route/geocode caches in bounded ephemeral memory by default; document any provider-required cache retention. Do not expose caches or connect them to user identity. Clear Trip removes current UI state.
- Send camera sync queries for the fixed region, never for a person's destination or path.
- Disclose external geocoding and tile requests. A local backend does not make an external tile provider private. Do not promise third-party non-retention.
- Use self-hosted address lookup for sensitive addresses. Test a local-only mode with network egress auditing before making privacy claims.
- Avoid precise trip coordinates in shareable URLs. Do not store routes in browser persistent storage or service-worker caches by default.
- Bind development services to localhost. Never expose PostGIS, Valhalla, or admin-sync endpoints directly to the public internet.
- Restrict CORS, bound input sizes and geometry complexity, and allowlist provider destinations to avoid an arbitrary-URL proxy.
- Escape externally supplied names/tags in map popups; do not render source strings as trusted HTML.
- Implement cancellation, request deadlines, and bounded candidate search to prevent resource exhaustion.

Before public hosting, review TLS, authentication for operator functions, backups, error logging, quotas, abuse prevention, and source compliance. Public release needs separate approval.

## 14. API and service contracts

These are proposed application endpoints, not existing public-provider APIs:

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/region` | Service/data envelope and capability status |
| `POST /api/v1/geocode` | Submitted address lookup through an approved adapter |
| `GET /api/v1/cameras?bbox=...` | Public camera features for the current viewport; bounded query |
| `POST /api/v1/routes/plan` | Validate trip, generate candidates, assess and return alternatives |
| `GET /api/v1/health/data` | Sanitized source, graph, and sync health |
| `POST /api/v1/admin/cameras/sync` | Protected operator refresh, or omit in favor of a local CLI |

Minimal route-request fields: typed origin/destination coordinates, region ID, requested profiles, camera scope, detour limits, and units. The server enforces hard limits; client settings cannot disable access constraints or coverage validation.

Use explicit error codes: `GEOCODER_NOT_CONFIGURED`, `ADDRESS_AMBIGUOUS`, `OUTSIDE_SERVICE_AREA`, `ROUTER_UNAVAILABLE`, `CAMERA_DATA_UNAVAILABLE`, `STALE_SNAPSHOT`, `NO_DRIVABLE_ROUTE`, `NO_IMPROVED_CANDIDATE`, `ASSESSMENT_INCOMPLETE`, and `SEARCH_BUDGET_EXCEEDED`.

Prefer a synchronous bounded route call for v1. Add a queued job system only when measured workloads justify it. The source-sync worker is separate from route planning.

## 15. Milestone plan and acceptance gates

### M0 - Source, geography, and routing feasibility

**Build:** no broad application implementation yet. Inspect an existing repo if present; otherwise prepare the new project plan. Verify source policies, select boundary geometry, inspect real Denver ALPR records, test a pinned Valhalla container on a small regional graph, and evaluate regional geocoding/basemap resource requirements.

**Evidence:** `FEASIBILITY_REPORT.md`, `DATA_SOURCE_REGISTER.md`, an initial version manifest, a source-tag sample, a camera-data coverage statement, and a synthetic avoidance test with instructions.

**Gate:** demonstrate an actual routing change around a synthetic obstacle without breaking directions or access restrictions; identify unsupported features and costs; obtain approval for geocoding and basemap deployment. Do not invent live counts or treat public demos as a deployment plan.

### M1 - Repository, contracts, and visible application shell

**Build:** backend/frontend, typed API client, Docker Compose, migrations, config validation, redacted logging, region configuration, responsive map shell, inputs, and Data Health placeholder.

**Tests:** startup smoke, schema validation, API error states, secret scanning, input state, and module-boundary tests.

**Gate:** documented Windows bootstrap works on a clean clone. Mock fixtures are explicitly labeled. No production module imports test fixtures. UI development starts here, not after the algorithms are finished.

### M2 - Public camera inventory and first snapshot

**Build:** permitted source adapter, bounded query, normalization, staging and atomic promotion, source versions, geometry checks, lifecycle handling, manufacturer classification, and searchable map overlay.

**Tests:** same ID with multiple versions; node/way identity collision; conflicting directions; missing manufacturer; non-ALPR device; malformed response; unexpected empty result; lifecycle change; vanished record; concurrent sync.

**Gate:** a real dated Denver-region snapshot can be loaded and refreshed without per-route provider calls. Source errors preserve the last known good snapshot. Counts refer to mapped records only.

### M3 - Standard route and usable address entry

**Build:** approved address lookup, candidate confirmation, map pins, ordinary auto routing, engine-generated directions, viewport fitting, cancellation, and route-response contracts.

**Tests:** incorrect address, swapped coordinates, no route, one-way road, turn restriction, private through-road, endpoint snapping, unit conversion, and instruction/geometry alignment.

**Gate:** address-to-address and pin-to-pin planning work for reviewed Denver cases. No camera-avoidance claim yet. Freshness and privacy disclosures appear in the UI.

### M4 - Encounter assessment and road-association validation

**Build:** meter-based proximity, road association, uncertainty flags, pinned snapshots, complete-path assessment, vendor scope, and per-camera explanations.

**Tests:** parallel frontage road; overpass; camera far from a road; ambiguous orientation; multiple cameras on one pole; route touches a buffer edge; endpoint next to a camera; loops; outside-envelope detour; 25/50/100 m sensitivity.

**Gate:** reviewer can inspect why each camera is or is not counted. Report false-association risks instead of treating all nearest-road matches as truth. The method must never measure meters in latitude/longitude degrees.

### M5 - Camera-aware route generation and comparison

**Build:** supported native avoidance, bounded candidate generation, full candidate reassessment, detour constraints, deterministic ranking, duplicate-route suppression, and honest partial/no-improvement states.

**Tests:** a lower-exposure detour is found on a synthetic graph; a longer but unchanged-exposure detour is not presented as a benefit; an over-budget alternative is rejected; repeated requests are deterministic on fixed snapshots; destination-in-exclusion is handled; no silent profile degradation occurs.

**Gate:** routing changes, not just overlay colors. Every displayed avoidance route is road-valid and fully assessed for its declared scope. Limited candidate search is disclosed. Artificial cost penalties do not contaminate ETA.

### M6 - Complete trip-planning experience

**Build:** finished route cards, mobile bottom sheet, camera details, directions highlighting, print view, data-age badges, disclaimer wording, clear trip, and accessibility polish.

**Tests:** full browser flow; keyboard-only operation; narrow-screen layout; request cancellation; late-response handling; selected route and instructions stay synchronized; no external autocomplete on a restricted provider.

**Gate:** a person can plan and compare a trip without opening a terminal. The UI clearly distinguishes no mapped encounters, unknown data, no better route, and no route at all.

### M7 - Scheduled updates, resilience, and operating instructions

**Build:** one scheduler, manual refresh cooldown, diff history, rollback, graph rebuild workflow, per-request version pinning, freshness policy, provider limits, and resource monitoring without trip data.

**Tests:** added/edited/removed records; outage; 429/backoff; invalid partial response; process restart; overlapping refresh requests; graph swap; failed rebuild; route computed during promotion.

**Gate:** new published source records flow into later route assessments after a validated sync. The app does not overwrite good data on failure. Scheduled sync only runs when the local service is running; reopening catches up politely.

### M8 - Denver pilot audit and v1 release candidate

**Build:** final documentation, small permitted pilot fixture set, source/asset attribution, privacy audit, performance measurements, known limitations, and release checklist.

**Tests:** all suites; real Denver planning cases while stationary; a fresh-install test; browser network/log inspection; source-policy review; no paid-key requirement; and restore/rollback checks.

**Gate:** approve an invited pilot only after evidence is reviewed. No claims of global route optimality, complete camera coverage, or guaranteed avoidance. Ask before public deployment or expanding the service boundary.

## 16. Testing strategy and quality targets

### Synthetic routing fixtures are mandatory

Build small deterministic road graphs or pinned engine fixtures with known valid outcomes. Include cases where a low-camera route exists, where it cannot exist, where it violates a detour bound, and where a geographical approximation would associate a camera with the wrong road.

Ordinary unit/CI tests must not call live public geocoding or Overpass services. Use sanitized responses and explicitly separated opt-in provider smoke tests. A passing algorithm test does not certify the physical-world inventory.

### Denver pilot review matrix

Use public landmarks or synthetic endpoints rather than personal home/work addresses. Review downtown one-way streets, major-road ramps, divided roads, city-edge trips, airport-related boundary behavior, short trips, same-location requests, and routes with no suitable alternative. Do not assume the same number of cameras will remain at any site.

### Suggested performance objectives

Treat these as targets to measure, not promised timings:

- Responsive input and clear progress immediately after submission.
- Warm local reference routing target: around 3 seconds or less for typical pilot trips.
- Bounded full comparison target: around 15 seconds, with a configured maximum planning deadline such as 20 seconds.
- Camera overlays served from the local snapshot without provider calls per pan.
- Configurable resource limits that keep the development PC usable; record cold-start, import, and rebuild costs separately.

Record counts, latency summaries, and failures without persistent trip payloads. Never weaken tests merely to obtain a green test run.

## 17. Reproducible operating workflow

Claude must implement and verify the commands before documenting them as working:

```text
Install prerequisites
    -> choose/pin compatible runtimes and containers
    -> copy .env.example to .env
    -> import public Denver/Colorado data
    -> build and validate road graph
    -> configure approved geocoding and basemap
    -> sync camera snapshot
    -> start web + API + DB + router + one sync worker
    -> run fixture tests and a stationary UI smoke test
```

Proposed convenience interface: `scripts/bootstrap.ps1`, `scripts/import_region.ps1`, `scripts/sync_cameras.ps1`, and `scripts/smoke_test.ps1`, followed by `docker compose up` after initialization. Do not publish these as already existing scripts before implementing them.

Document expected import time/disk use from the actual pilot machine. Keep a last-good graph and snapshot. A rollback should not require deleting the entire database. Avoid recommending indiscriminate cache removal or global environment changes.

## 18. Cost and deployment policy

The plan does not require a paid LLM, Google Maps API key, or paid camera-location subscription. That is an architectural target, not a promise of costless public operation.

For local use, open-source services and permitted public data can be used with the owner's hardware. A public launch can require server resources, bandwidth, map infrastructure, domains, monitoring, and source-provider agreements. Do not silently enable a trial that turns into a charge.

Do not make the project's scalability depend on donated public endpoints. Start with a small self-hosted regional routing service and a locally served camera inventory, then revisit address search, tiles, and data replication before growing the user base.

Keep brand/code/data obligations separate: cite OpenStreetMap on the map and document the ODbL requirements for distributed derived data. Open-source library licenses do not replace source-data attribution obligations. Review actual dataset and asset licenses before redistribution. [S10]

Use the exact project name **DeFlockMigration**, with an independent-project statement. Do not imply endorsement by DeFlock, Flock Safety, OpenStreetMap, or the City and County of Denver. Name availability and branding permission have not been established by this plan.

## 19. Expansion roadmap

| Release | Goal | Entry condition |
|---|---|---|
| v0.1 | Source and routing proof | M0 capability evidence |
| v0.2 | Denver map, inventory, standard directions | M1-M3 |
| v0.3 | Validated camera-aware comparisons | M4-M5 |
| v1.0 | Usable Denver pilot with updates and privacy controls | M6-M8 |
| v1.1 | Reviewed neighboring service areas | Region config, data envelopes, and new QA cases |
| v2.0 | Broader regional deployment and optional offline planning | Sustainable data/tiles/geocoding infrastructure |
| v3.0 | Mobile live navigation and rerouting, if approved | GPS, permissions, route adherence, battery, safety, and platform-specific validation |

Do not call live navigation a small cosmetic enhancement. Do not introduce automatic tracking or personal trip retention as a side effect of regional expansion.

## 20. Claude Code engineering rules

Add a concise version of these rules to the repository's `CLAUDE.md`:

```text
Project: DeFlockMigration. Denver-first web route planner.

1. Inspect the repository and approved roadmap before edits.
2. Complete one approved milestone at a time.
3. Never invent camera coordinates, vendor identity, source dates,
   completeness, live traffic, detection ranges, or field verification.
4. Never label a route surveillance-free or guarantee no recording.
5. Keep camera assessment, real travel time, and search cost separate.
6. Preserve normal driving restrictions. Do not optimize around them.
7. Evaluate every candidate's complete path and geographic coverage.
8. Use only supported, tested routing parameters.
9. Keep personal trips out of persistent logs and default storage.
10. Fetch public camera data independently of individual trip queries.
11. Respect public-service policies and do not bypass access controls.
12. Do not require paid APIs or use unrestricted public demos as hosting.
13. Test uncertainty, outages, no-route cases, and false road matches.
14. Do not weaken tests or silently fall back to fake/sample production data.
15. Ask before deployment, paid integrations, persistent personal data,
    service-area expansion, or a major routing-engine change.
16. Distinguish implemented, tested, manually reviewed, and proposed work.
```

After every milestone, report changed files, commands executed, test results, known limitations, public-source calls made, and the next acceptance gate. A screenshot alone is not proof of correct routing.

## 21. Definition of done for the Denver pilot

- [ ] The application is named DeFlockMigration throughout UI and documentation.
- [ ] Start/destination address entry and map-pin alternatives both work.
- [ ] The service boundary, data envelope, and graph extent are versioned separately.
- [ ] Real public ALPR records are imported with source and lifecycle metadata.
- [ ] Flock-only/all-ALPR scope is explicit and manufacturer-unknown records are not misidentified.
- [ ] The route engine demonstrably avoids mapped targets in validated cases.
- [ ] All route options are checked against the full assessed area and detour limits.
- [ ] Candidate count is honest; duplicate routes are not padded into three options.
- [ ] Directions match the selected path exactly.
- [ ] Zero, unknown, stale, unassessed, no improvement, and no route are distinct states.
- [ ] Cameras newly appearing in the public source are incorporated after a successful scheduled/manual sync.
- [ ] Failed or suspicious updates retain the last-good data.
- [ ] No paid AI runtime or undocumented provider API is required.
- [ ] Personal trip data is absent from persistent default logs, URLs, and storage.
- [ ] External address/map data flow is disclosed and approved.
- [ ] Map/data/asset attribution and public-service policies are documented.
- [ ] Unit, integration, browser, privacy, and synthetic routing tests pass.
- [ ] Real-world pilot checks and unvalidated limitations are recorded honestly.
- [ ] User guide and recovery procedures work on a clean local installation.
- [ ] The owner approves any public deployment separately.

## 22. Primary-source register

Documentation reviewed October 15, 2026. This review establishes documented capabilities, not a completed Denver ingestion, measured device coverage, deployed server, or proven routing accuracy. Recheck policies and pinned-version behavior during M0.

**[S1] DeFlock project repository**  
https://github.com/FoggedLens/deflock  
Establishes that DeFlock uses OpenStreetMap camera data; useful context for sourcing without scraping its UI.

**[S2] OpenStreetMap ALPR tagging**  
https://wiki.openstreetmap.org/wiki/Tag:surveillance:type%3DALPR  
Device classification, manufacturer/direction fields, and lifecycle documentation.

**[S3] Overpass API shared-resource policy**  
https://dev.overpass-api.de/overpass-doc/en/preface/commons.html  
Ingestion design and public-service limits.

**[S4] Geofabrik Colorado extracts**  
https://download.geofabrik.de/north-america/us/colorado.html  
Regional road/camera input and published update formats.

**[S5] Valhalla route API**  
https://valhalla.github.io/valhalla/api/route/api-reference/  
Capability verification for exclusions, alternatives, linear cost factors, request/response contracts, and limitations.

**[S6] Valhalla routing overview and installation**  
https://valhalla.github.io/valhalla/api/route/overview/  
https://valhalla.github.io/valhalla/  
Route geometry, maneuver outputs, and supported deployment approach.

**[S7] Public Nominatim usage policy**  
https://operations.osmfoundation.org/policies/nominatim/  
Mandatory policy review before enabling that public service; not interchangeable with self-hosting.

**[S8] OpenStreetMap public raster-tile policy**  
https://operations.osmfoundation.org/policies/tiles/  
Interactive use, caching, privacy, and prohibition on bulk/offline tile collection.

**[S9] MapLibre GL JS documentation**  
https://maplibre.org/maplibre-gl-js/docs/  
Frontend map rendering and integration reference.

**[S10] OpenStreetMap copyright and license**  
https://www.openstreetmap.org/copyright  
Attribution and database-license requirements.

**[S11] Denver public data and GIS**  
https://www.denvergov.org/Government/Data-and-Maps  
https://denvergov.org/Government/Agencies-Departments-Offices/Agencies-Departments-Offices-Directory/Technology-Services/Functions/GIS  
Candidate boundary and supplementary public datasets; inspect the actual selected layer.

**[S12] PostGIS ST_DWithin**  
https://postgis.net/docs/ST_DWithin.html  
Distance units and spatial-index behavior.

**[S13] Self-hosted Nominatim installation**  
https://nominatim.org/release-docs/latest/admin/Installation/  
Regional geocoder infrastructure feasibility; do not use full-planet sizing as a local target.

**[S14] Protomaps PMTiles concepts**  
https://docs.protomaps.com/pmtiles/  
Optional regional basemap archive format and local serving requirements.

---

**First implementation action:** Complete M0, show the actual source/routing findings, and obtain approval before building the broader application.
