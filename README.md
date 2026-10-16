# DeFlockMigration

A Denver-first web route planner that compares practical driving routes by their potential encounters with mapped automated license-plate-reader (ALPR) cameras, explains each detour, and makes data limitations visible.

DeFlockMigration is an independent project. It is not affiliated with or endorsed by DeFlock, Flock Safety, OpenStreetMap, or the City and County of Denver. It never promises an unrecorded journey and never labels an area surveillance-free.

## Status

- **M0 feasibility:** complete and approved (2026-10-15).
- **M1 repository, contracts, Docker Compose stack, application shell:** built 2026-10-15; see `docs/DEVELOPMENT_LOG.md` for the gate evidence. In this build the planner returns the Standard route only; camera-aware comparison arrives in M4/M5.

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
| `apps/web/` | Next.js + MapLibre planner, Vitest tests, Playwright smoke tests (`e2e/`) |
| `configs/` | region geometry references, providers, route profiles, data quality, privacy flags |
| `data/` | committed boundaries, fixtures, manifests; local-only extracts and basemap under `data/raw/` |
| `scripts/` | `bootstrap.ps1`, `import_region.ps1`, `sync_cameras.ps1`, `smoke_test.ps1` |
| `docs/` | roadmap, decisions, feasibility report and evidence, data source register, user guide, test plan, privacy and data flow, development log |
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
