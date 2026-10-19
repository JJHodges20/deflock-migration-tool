# Project context

**DeFlockMigration** is a Denver-first web route planner. A person enters a start and a destination; the app compares practical driving routes by their potential encounters with mapped automated license-plate-reader (ALPR) cameras, explains each detour, and makes data limitations visible. It never promises an unrecorded journey and never labels an area surveillance-free.

It is an independent project with no affiliation to DeFlock, Flock Safety, OpenStreetMap, or the City and County of Denver.

## Confirmed by the owner

- Exact name DeFlockMigration; Denver pilot first, expanded to all of Colorado in M9 (decision 0003, 2026-10-19); web trip planning before any live navigation.
- No public use for now and a separate approval before any public deployment; the owner tests personally (decision 0003).
- Start and destination can be typed; map pins are an additional option.
- Camera records come from permitted open sources (OpenStreetMap) and refresh on a schedule.
- Travel-time trade-offs, uncertainty, and data timestamps are explained in the UI.
- No guarantee of avoiding all actual cameras or all recordings.
- Docker Compose is the primary runtime for the entire application (decision 0002, 2026-10-15).
- Approved on 2026-10-15: decisions 0001 and 0002, self-hosted Nominatim inside Compose (TIGER optional, off by default), self-hosted PMTiles basemap, no external geocoder or tiles, milestone commits to the local repository.

## Sources of truth

| Topic | Where |
|---|---|
| Roadmap and milestone gates | `docs/plans/DeFlockMigration_Claude_Build_Roadmap.md` |
| Decisions | `docs/decisions/0001-denver-pilot.md`, `docs/decisions/0002-docker-compose-primary-runtime.md`, `docs/decisions/0003-colorado-service-area.md` |
| Feasibility evidence (M0) | `docs/FEASIBILITY_REPORT.md`, `docs/evidence/`, `spikes/` |
| Sources, licenses, policies | `docs/DATA_SOURCE_REGISTER.md` |
| Region geometry and versions | `configs/regions/colorado.yaml` (default since M9) and `configs/regions/denver.yaml` (pilot area), `data/boundaries/`, `data/manifests/` |
| How to run | `docs/USER_GUIDE.md`, `compose.yaml`, `scripts/` |
| Milestone status | `docs/IMPLEMENTATION_PLAN.md`, `docs/DEVELOPMENT_LOG.md` |
| Tests | `docs/TEST_PLAN.md` |
| Engineering rules for Claude Code | `CLAUDE.md` |

## Non-negotiables

Private trip details stay out of logs and storage. Camera sync uses the fixed region, never a trip. Missing, stale, or failed data is uncertainty, not zero cameras. Every candidate's whole path is assessed. Driving restrictions are preserved. Router parameters, coordinates, quality scores, detection ranges, and verification dates are never invented. Public-service policies are respected without endpoint rotation. No paid services, public deployment, automatic OSM edits, or major architecture changes without approval.
