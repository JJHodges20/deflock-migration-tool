# DeFlockMigration

A Colorado web route planner (Denver pilot first, statewide since M9) that compares practical driving routes by their potential encounters with mapped automated license-plate-reader (ALPR) cameras, explains each detour, and makes data limitations visible.

DeFlockMigration is an independent project. It is not affiliated with or endorsed by DeFlock, Flock Safety, OpenStreetMap, or the City and County of Denver. It never promises an unrecorded journey and never labels an area surveillance-free.

## Status

- **M0 feasibility** through **M6 complete trip-planning experience**: complete and approved (2026-10-15 to 2026-10-19); evidence per milestone in `docs/DEVELOPMENT_LOG.md`, milestone table in `docs/IMPLEMENTATION_PLAN.md`.
- **M7 scheduled updates, resilience, and operating instructions:** complete and approved 2026-10-19. The runbook is `docs/OPERATIONS.md`.
- **M8 Denver pilot audit and v1.0 release candidate (`1.0.0rc1`):** built and audited 2026-10-19; reviewed by the owner the same day, who chose personal use only with a separate approval before any public deployment (decision 0003). The audit, known limitations, and release checklist are in `docs/AUDIT.md`; attribution and policies in `docs/ATTRIBUTION.md`. An invited pilot or a public deployment needs the owner's separate approval.
- **M9 Colorado service area:** built and verified 2026-10-19 (decision 0003): U.S. Census state boundary, 20 km envelope clipped to the routing graph, statewide camera inventory and basemap, region-driven wording, statewide review cases; approved 2026-10-19, commit 2cec028 (evidence in the M9 entry of `docs/DEVELOPMENT_LOG.md`).
- **M10 extract-based camera ingestion:** built and verified 2026-10-19/20 (decision 0004): the camera inventory comes from the Geofabrik Colorado extract kept current with the publisher's daily change files (pyosmium), seeded from the routing graph's extract; the planner no longer depends on the public Overpass instance; awaiting the owner's gate review (evidence in the M10 entry of `docs/DEVELOPMENT_LOG.md`).

## Run it (Docker only)

Prerequisites: Docker Desktop with Compose v2, Git. Nothing else is installed on the host.

```powershell
# first time (builds images, imports public data, builds the routing graph, starts everything)
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1

# every day afterwards
docker compose up
```

Then open http://127.0.0.1:3000. Details, timings, operator tasks, and troubleshooting: `docs/USER_GUIDE.md`.

## Repository map

| Path | Contents |
|---|---|
| `compose.yaml`, `.env.example`, `infra/` | the Compose stack: nginx edge, Next.js web, FastAPI api, camera-sync worker, PostGIS, Valhalla 3.9.1, Nominatim 5.3.2, setup and test profiles |
| `backend/` | API, worker, setup jobs, Alembic migrations, pytest suites |
| `apps/web/` | Next.js + MapLibre planner, Vitest tests, Playwright browser suites (`e2e/`) |
| `configs/` | region geometry references, providers, route profiles, data quality, privacy flags |
| `data/` | committed boundaries, fixtures (including the reviewed pilot trips), manifests; local-only extracts and basemap under `data/raw/` |
| `scripts/` | `bootstrap.ps1`, `import_region.ps1`, `rollback_graph.ps1`, `sync_cameras.ps1`, `review_snapshot.ps1`, `associate_cameras.ps1`, `smoke_test.ps1`, `audit.ps1` |
| `docs/` | roadmap, decisions, feasibility report and evidence, data source register, attribution and policies, user guide, operations runbook, routing and assessment method, data dictionary, test plan, privacy and data flow, release audit, development log |
| `spikes/` | M0 routing and geocoder spikes with their results |
| `CLAUDE.md` | engineering rules for Claude Code sessions |

## Tests

```powershell
docker compose --profile test run --rm api-tests
docker compose --profile test run --rm web-tests
docker compose --profile test run --rm e2e        # needs the stack running
powershell -ExecutionPolicy Bypass -File scripts\smoke_test.ps1 -CheckRestart
```

## Data attribution

Camera records and road data: © OpenStreetMap contributors, Open Database License (https://www.openstreetmap.org/copyright). Basemap: Protomaps © OpenStreetMap. Boundary: City and County of Denver Open Data (provided as is, not for engineering purposes). Fonts: Noto Sans (SIL Open Font License). Routing engine: Valhalla (MIT). Geocoder: Nominatim (GPL).
