# CLAUDE.md - DeFlockMigration engineering rules

Project: DeFlockMigration. Denver-first web route planner that compares driving routes by potential
encounters with mapped ALPR cameras. Read `docs/plans/DeFlockMigration_Claude_Build_Roadmap.md`,
`docs/decisions/`, and `docs/IMPLEMENTATION_PLAN.md` before editing.

## Rules (roadmap section 20 plus decision 0002)

1. Inspect the repository and the approved roadmap before edits.
2. Complete one approved milestone at a time; stop at each gate and report.
3. Never invent camera coordinates, vendor identity, source dates, completeness, live traffic,
   detection ranges, or field verification.
4. Never label a route surveillance-free or guarantee no recording.
5. Keep camera assessment, real travel time, and search cost separate.
6. Preserve normal driving restrictions. Do not optimize around them (engine legality options stay default).
7. Evaluate every candidate's complete path and geographic coverage.
8. Use only supported, tested routing parameters (`exclude_locations`, `exclude_polygons`,
   `linear_cost_factors`, `alternates`, `units`, `id`).
9. Keep personal trips out of persistent logs and default storage (request bodies, query strings,
   coordinates, and bounding boxes are never logged; nginx access log is off).
10. Fetch public camera data independently of individual trip queries (fixed envelope, 6-hourly).
11. Respect public-service policies and do not bypass access controls (Overpass pause rules; no public Nominatim; no public OSM tiles).
12. Do not require paid APIs or use unrestricted public demos as hosting.
13. Test uncertainty, outages, no-route cases, and false road matches.
14. Do not weaken tests or silently fall back to fake/sample production data. Fixtures are named `fixture_*`.
15. Ask before deployment, paid integrations, persistent personal data, service-area expansion,
    a major routing-engine change, or a large download (planet files, TIGER).
16. Distinguish implemented, tested, manually reviewed, and proposed work in every report.
17. Docker Compose is the primary runtime: every service, setup job, migration, and test runs in a
    container; images are pinned; named volumes persist data; `docker compose up` is the everyday command.

## Layout

- `backend/` FastAPI API, camera-sync worker, setup jobs, Alembic migrations, pytest suites.
- `apps/web/` Next.js + MapLibre planner, Vitest unit tests, Playwright smoke tests in `e2e/`.
- `configs/` region, providers, route profiles, data quality, privacy (validated at startup).
- `infra/` nginx edge, Valhalla serve/build scripts, database init.
- `scripts/` PowerShell operator scripts (bootstrap, import_region, sync_cameras, smoke_test).
- `data/boundaries`, `data/fixtures`, `data/manifests` committed; `data/raw/osm`, `data/raw/basemap` local only.
- `docs/` roadmap, decisions, feasibility evidence, user guide, test plan, development log.

## Commands

- Tests in containers: `docker compose --profile test run --rm api-tests`, `... web-tests`, `... e2e`.
- Host-side backend tests (optional): create a venv, `pip install -e backend[dev]`, run `pytest` in `backend/`.
- Setup jobs: `docker compose --profile setup run --rm <db-migrate|osm-download|graph-build|basemap-extract|basemap-assets|camera-sync-once>`.
