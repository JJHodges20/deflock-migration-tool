# DeFlockMigration - Start Here in Claude Code

## How to use this handoff

Place `DeFlockMigration_Claude_Build_Roadmap.md` in the new project's root or `docs/plans/`. Open Claude Code in the intended repository, then paste the prompt below. The roadmap describes proposed work; no application, camera inventory, or working routes are included in this package.

Do not ask Claude to build the entire product in a single unattended run. Complete Milestone 0, review the findings, and approve subsequent milestones one at a time.

## Copyable kickoff prompt

```text
We are building a new application called DeFlockMigration.

Read DeFlockMigration_Claude_Build_Roadmap.md before making changes.
If I placed it under docs/plans/, read that copy. Inspect any existing
repository content before scaffolding, replacing files, or adding tools.

Product:
A simple, responsive web application that accepts a trip's origin and
destination, compares efficient driving routes with fewer potential
encounters with mapped Flock/ALPR cameras, and provides street-by-street
directions. Begin with Denver, Colorado. Expand only after approval.
Use open camera data and maintain scheduled updates when the local
services are running.

Confirmed constraints:
- Exact project name: DeFlockMigration.
- Denver pilot first; web trip planning before live mobile navigation.
- Start and destination can be typed; map pins are an additional option.
- Camera updates come from permitted open sources.
- Explain travel-time tradeoffs, uncertainty, and data timestamps.
- No guarantee of avoiding all actual cameras or all recordings.

Recommended architecture to evaluate:
- Next.js/TypeScript/React with MapLibre.
- FastAPI with typed request/response models.
- PostgreSQL/PostGIS for public camera snapshots and spatial queries.
- Self-hosted Valhalla for driving paths and maneuver instructions.
- A bounded, cached Overpass adapter for development and a regional
  OSM-extract adapter for sustainable expansion.
- Prefer regional self-hosted address lookup and permitted local map
  tiles. Never silently enable a third-party geocoder or public demo.
- No LLM is needed for routing. No mandatory paid API.

Only complete Milestone 0 now: feasibility and decisions.

Tasks:
1. Inspect the repository and development environment. Do not delete or
   overwrite existing work. Confirm compatible runtime/container versions.
2. Read primary provider documentation and usage policies. Record actual
   source URLs, license obligations, and the date checked.
3. Inspect real Denver-region ALPR records through permitted bounded
   access. Preserve source identity, manufacturer, lifecycle, direction,
   timestamps, and unknowns. Do not scrape another map's UI.
4. Propose a reviewed Denver service boundary, a larger camera-data
   envelope, and broader road-graph coverage. Explicitly address airport,
   city-edge, divided-road, and overpass cases. Do not equate mapped data
   with complete physical-camera coverage.
5. Test a pinned Valhalla build in a small isolated spike. Demonstrate
   a standard route and a changed path around a synthetic avoidance target
   with valid instructions. Check supported exclusions, native geometry
   penalties, alternative-route behavior, warnings, and payload limits.
6. Assess address lookup and basemap deployment: regional self-hosting
   resource cost versus an explicitly approved external pilot service.
   Public Nominatim is not pre-approved. Its policy must be reviewed before
   any use, including rate limits, caching, no autocomplete, and privacy.
7. Document memory, disk, startup/build time, dependencies, and any cost.
   Do not perform a planet import or a large download without approval.
8. Produce docs/FEASIBILITY_REPORT.md, docs/DATA_SOURCE_REGISTER.md,
   docs/decisions/0001-denver-pilot.md, and an M1 implementation checklist.
   Clearly identify what was actually executed, what was inspected only,
   and what remains unverified.

Non-negotiable implementation rules:
- Keep private trip details out of logs and persistent default storage.
- Camera sync uses a fixed region, not a user's current route.
- Treat missing/stale/failed source data as uncertainty, not zero cameras.
- Assess every candidate's entire path, including detours.
- Do not associate a camera with a parallel road simply because it is close.
- Do not infer recorded traffic direction solely from camera orientation.
- Preserve driving access and turn restrictions.
- Never invent router parameters, camera coordinates, data quality scores,
  detection ranges, live traffic, or verification dates.
- Do not use public-service endpoint rotation to evade rate limits.
- No paid services, public deployment, automatic OSM edits, or major
  architecture changes without approval.
- Use small offline fixtures for ordinary tests and explicitly separate
  optional live provider smoke tests.
- Do not weaken tests or produce fake camera data presented as real.

Stop after Milestone 0 and ask me to approve the decisions and M1.
Do not implement all milestones or claim the pilot is production-ready.
```

## Reviewing Claude's first response

Look for evidence of a real routing capability test, an honest camera-source coverage assessment, a clear boundary/envelope decision, and an explicit geocoding/basemap approval request. A mock interface and a list of libraries are not enough to pass M0.

If a proposed integration fails, preserve the useful foundation and choose an approved fallback. Do not silently substitute a paid API, remove the address-entry requirement, or pretend that a route overlay is an avoidance engine.
