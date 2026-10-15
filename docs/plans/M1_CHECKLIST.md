# M1 implementation checklist - Repository, contracts, and visible application shell

**Entry condition:** owner approves decisions 0001 and 0002 and the geocoder/basemap deployment choices in `docs/FEASIBILITY_REPORT.md`.
**Exit gate (from the roadmap plus the Docker Compose requirement):** documented Windows first-time setup followed by `docker compose up` works on a clean clone; every service reports ready; a restart keeps data; one browser-to-backend routing request succeeds through the containers; mock fixtures are labelled; no production module imports test fixtures.

## 1. Repository skeleton
- [ ] `README.md`, `CLAUDE.md` (engineering rules from roadmap section 20 plus decision 0002), `.env.example`, `compose.yaml`, `.gitignore` (already present), `.github/workflows/tests.yml`.
- [ ] `configs/` with `regions/denver.yaml` (from M0), `providers.yaml`, `route_profiles.yaml`, `data_quality.yaml`, `privacy.yaml`; a config loader that validates them at startup and fails loudly.
- [ ] `docs/PROJECT_CONTEXT.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/DEVELOPMENT_LOG.md` started.

## 2. Docker Compose (decision 0002)
- [ ] Services: `web` (Next.js, multi-stage image, Node pinned inside the image), `api` (FastAPI, Python pinned inside the image), `db` (PostGIS, pinned tag), `valhalla` (`ghcr.io/valhalla/valhalla:3.9.1` serving from the `valhalla_tiles` volume), `camera-sync` worker (same backend image, worker entrypoint), `basemap` (static range-capable server for the PMTiles file), `geocoder` (Nominatim, pinned, only if approved).
- [ ] One-time jobs under a `setup` profile: `db-migrate`, `osm-download` (Geofabrik extract + checksum), `graph-build` (the M0 container build script, ported), `camera-sync --once`, `basemap-extract`, `geocoder-import`.
- [ ] Named volumes: `pgdata`, `valhalla_tiles`, `osm_extracts`, `basemap`, `geocoder_db`. Documented warning that `docker compose down -v` destroys them.
- [ ] Healthchecks: `pg_isready`, Valhalla `/status`, API `/api/v1/health/data`, web HTTP 200, basemap HEAD with `Accept-Ranges`; `depends_on` with `condition: service_healthy`.
- [ ] Ports bound to `127.0.0.1` only; PostGIS, Valhalla, geocoder not published.
- [ ] Resource notes for the 8 GB Docker Desktop allocation: graph build (3 GB peak) and geocoder import never run concurrently with each other by default; documented `memory` limits per service.
- [ ] `scripts/bootstrap.ps1` (first-time setup: copies `.env`, runs the setup profile in order), `scripts/import_region.ps1`, `scripts/sync_cameras.ps1`, `scripts/smoke_test.ps1`; each implemented and run before being documented.
- [ ] `docs/USER_GUIDE.md` sections "First-time setup" and "Everyday startup (`docker compose up`)" written separately, with measured durations from this machine.

## 3. Backend (`backend/`)
- [ ] `pyproject.toml` pinned (FastAPI, Pydantic v2, SQLAlchemy 2, GeoAlchemy2, psycopg 3, Alembic, httpx, pytest); verified wheels exist for the image's Python version.
- [ ] Package layout from roadmap section 6; `RoutingProvider`, `Geocoder`, `CameraRepository`, `ExposureAssessor` interfaces with a Valhalla adapter skeleton that only wraps documented parameters (`exclude_locations`, `exclude_polygons`, `linear_cost_factors`, `alternates`, `units`, `id`).
- [ ] Endpoints `GET /api/v1/region`, `GET /api/v1/health/data`, `POST /api/v1/routes/plan` (returns `ROUTER_UNAVAILABLE` or a standard route only; no avoidance claim yet), `POST /api/v1/geocode` (returns `GEOCODER_NOT_CONFIGURED` until approved provider is wired).
- [ ] Alembic migration 0001: `camera_snapshots`, `camera_records`, `sync_jobs` tables with the field groups from roadmap section 7 (geometry as `geography(Point,4326)`).
- [ ] Redacted logging: request bodies, query strings, coordinates, and bounding boxes never logged; tests for exceptions and timeouts.
- [ ] Settings via environment with validation; no secrets in images.

## 4. Frontend (`apps/web/`)
- [ ] Next.js + TypeScript + MapLibre GL JS pinned; `pmtiles` protocol wired to the local basemap service; self-hosted fonts/sprites; attribution control showing "Protomaps © OpenStreetMap" and the boundary credit.
- [ ] Responsive planner shell: desktop side panel + map; mobile bottom sheet; start/destination inputs with explicit Search/Confirm (no autocomplete), swap, map-pin mode, route preference, camera scope, max extra time; Data Health placeholder; disclaimer wording from the roadmap.
- [ ] Typed API client generated from the backend schemas; cancellation and late-response discard.
- [ ] No analytics, no third-party scripts, no persistent storage of trips.

## 5. Tests
- [ ] Backend: startup smoke, config validation, API error-state contracts, privacy redaction, module-boundary test (production code never imports `tests/`).
- [ ] Frontend: Vitest unit tests for input state; Playwright smoke at 390/768/1440 px against the Compose stack.
- [ ] Secret scanning in CI; fixtures labelled `fixture` in filenames and loaders.
- [ ] Compose verification script: readiness of every service, `docker compose restart` then data still present (row count in `camera_snapshots`, Valhalla `/status` tileset date unchanged), and one routing request from the browser through `api` to `valhalla`.

## 6. Carry-overs from M0 to settle in M1 code
- [ ] Standard route = fastest reported time among baseline candidates (decision 0001 D6).
- [ ] Aliases and exclusions from decision 0001 D8 implemented in the normalizer with the M0 fixture as a test input.
- [ ] Camera sync query file and envelope geometry loaded from `configs/regions/denver.yaml`, never from a trip.
- [ ] Record the M0 version manifest ids (`data/manifests/versions_m0_2026-10-15.json`) as the initial graph, snapshot, boundary, and basemap versions in Data Health.

## 7. Report back at the end of M1
Changed files, commands executed, test results, known limitations, public-source calls made, measured setup and startup durations, and the M2 acceptance gate.
