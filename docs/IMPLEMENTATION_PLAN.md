# Implementation plan and milestone status

Milestones follow roadmap section 15. One milestone at a time; each ends with a report and an approval gate.

| Milestone | Scope | Status |
|---|---|---|
| M0 | Source, geography, and routing feasibility | **Complete, approved 2026-10-15** (commit `4476da0`) |
| M1 | Repository, contracts, Docker Compose stack, visible application shell | **Complete, approved 2026-10-16** (commit `5f78ac8`) |
| M2 | Public camera inventory: envelope checks, no-longer-mapped carry-over, diff and record history, retention, quarantine review, overlay legend and source links | **Complete, approved 2026-10-19** (commit `1aecbd3`) |
| M3 | Standard route and usable address entry: reviewed Denver address cases, reverse-labelled pins, swapped-coordinate handling, snapping and alignment disclosures, units, legality evidence, freshness and privacy strip, map worker and layout fixes | **Complete, approved 2026-10-19** (commit `8528cc5`) |
| M4 | Encounter assessment and road-association validation: PostGIS proximity in meters, nearest-road association by road identity (name set, way id when unnamed) local to the pass, uncertainty statuses, per-record explanations, sensitivity radii, envelope coverage, association cache, evidence UI | **Complete, approved 2026-10-19** (commit `c523ba5`; method in `docs/ROUTING_METHOD.md`) |
| M5 | Camera-aware route generation and comparison: documented avoidance requests, bounded candidate search with full reassessment, deterministic ranking per preference, duplicate suppression, honest partial and no-improvement states, search disclosure, comparison UI, synthetic routing fixture | **Complete, approved 2026-10-19** (commit `66c7134`; method in `docs/ROUTING_METHOD.md` section 3) |
| M6 | Complete trip-planning experience: unmistakable result states, data-age badges, camera details, directions summary, print view, GeoJSON download, explicit cancel, focus management, bottom-sheet summary, one-shot device location, accessibility polish with an axe scan | **Complete, approved 2026-10-19** (commit `44b679b`) |
| M7 | Scheduled updates, resilience, operating instructions: scheduler and freshness disclosure, manual-refresh cooldown, snapshot rollback, validated graph rebuild with rollback, per-request pinning made visible, provider policy, diff history, trip-free metrics, operations runbook | **Complete, approved 2026-10-19** (commit `84644a4`; runbook in `docs/OPERATIONS.md`) |
| M8 | Denver pilot audit and v1.0 release candidate: definition-of-done audit, release audit script (keys, egress, logs, restore, perf), local-only network layout, browser privacy suite, pilot fixture set with live cases, fresh-install test, attribution and policy review, known limitations, release checklist | **Built and audited 2026-10-19 (`1.0.0rc1`, tag `v1.0.0-rc1`); awaiting the owner's gate review** (evidence in `docs/AUDIT.md`) |

## M1 deliverables (what exists after M1)

- `compose.yaml` with edge (nginx), web (Next.js), api (FastAPI), camera-sync worker, db (PostGIS), valhalla (pinned 3.9.1), geocoder (pinned Nominatim 5.3.2); setup-profile jobs for migrations, extract download, graph build, basemap extract and assets, first camera snapshot; test-profile services for backend, frontend, and browser tests; named volumes for every persistent dataset; healthchecks and localhost-only ports.
- Backend: validated configuration, redacted logging, region/health/plan/geocode/cameras endpoints with explicit error codes, Valhalla adapter using only documented parameters, Standard route chosen by reported time (D6), self-hosted Nominatim adapter with a public-service guard, policy-aware Overpass client, normalizer implementing D8, snapshot/record/sync-job schema (Alembic 0001), atomic snapshot promotion with quarantine and last-good retention, scheduler worker.
- Frontend: responsive planner shell (desktop panel + map, mobile bottom sheet), typed inputs with Search/Confirm, coordinate entry, map pins, swap, route preference and camera scope controls, detour limits, route cards with honest "not assessed" states, engine directions, camera overlay from the local snapshot, Data Health panel, disclaimers and attributions, map-failure fallback.
- Scripts: `bootstrap.ps1`, `import_region.ps1`, `sync_cameras.ps1`, `smoke_test.ps1`.
- Docs: user guide (first-time setup vs everyday startup), test plan, development log, engineering rules.

## Next gate (M1 to M2)

Owner reviews the M1 report: Compose bring-up from a clean clone, service readiness, restart persistence, the browser-to-backend routing request, test results, and known limitations. Approval starts M2.
