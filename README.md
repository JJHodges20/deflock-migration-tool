# DeFlockMigration

A Denver-first web route planner that compares practical driving routes by their potential encounters with mapped automated license-plate-reader (ALPR) cameras, explains each detour, and makes data limitations visible.

DeFlockMigration is an independent project. It is not affiliated with or endorsed by DeFlock, Flock Safety, OpenStreetMap, or the City and County of Denver. It never promises an unrecorded journey and never labels an area surveillance-free.

## Status

**Milestone 0 (feasibility) complete on 2026-10-15; awaiting owner approval for Milestone 1.** No application code exists yet. The repository holds the roadmap, the M0 evidence, pinned versions, and proposed decisions.

Start with:

1. `docs/plans/DeFlockMigration_Claude_Build_Roadmap.md` - the approved roadmap (with the Docker Compose addendum).
2. `docs/FEASIBILITY_REPORT.md` - what was executed, inspected, and left unverified, plus the decisions requested.
3. `docs/decisions/` - 0001 pilot scope, 0002 Docker Compose as the primary runtime.
4. `docs/DATA_SOURCE_REGISTER.md` - every source, its license, policy terms, and how it is used.
5. `docs/plans/M1_CHECKLIST.md` - the next milestone.

## How the application will run

Docker Compose is the primary runtime for the whole application (frontend, backend, PostGIS, Valhalla, camera-update worker, basemap server, and the geocoder if approved). Normal use requires only Docker Desktop; first-time setup and everyday startup (`docker compose up`) will be documented separately in M1.

## Reproducing the M0 spikes

The spikes used only Docker plus the host Python for analysis scripts:

- Routing graph build and avoidance test: `spikes/valhalla/results/README.md`
- Camera snapshot analysis: `scripts/m0/analyze_overpass_snapshot.py`
- Boundary and envelope analysis: `scripts/m0/analyze_boundary.py` (needs shapely and pyproj in a scratch virtual environment)

Large downloads (OSM extract, basemap archive, raw Overpass responses, Docker volumes) are not committed; the manifests under `data/manifests/` record their identities and checksums.

## Data attribution

Camera records and road data: © OpenStreetMap contributors, Open Database License (https://www.openstreetmap.org/copyright). Basemap: Protomaps © OpenStreetMap. Boundary: City and County of Denver Open Data (provided as is, not for engineering purposes).
