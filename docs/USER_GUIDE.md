# User guide (Denver pilot, M1 build)

DeFlockMigration runs entirely in Docker. The host needs Docker Desktop (Compose v2) and Git; nothing else is installed on the computer.

The app is a trip planner, not a navigation app. Plan while stopped. Routes are advisory; road signs, access restrictions, closures, and actual conditions take precedence. Camera counts describe mapped OpenStreetMap records, not physical devices; in the M1 build no camera assessment is shown yet (every route reads "Not assessed in this version").

---

## 1. First-time setup (once)

Measured on the pilot machine (Ryzen 7 5700X, 16 GB RAM, Docker Desktop with 8 GB allocated, 2026-10-15); your timings depend on CPU, disk, and connection.

1. Open PowerShell in the project folder.
2. Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
```

The script performs these steps, each a containerized job, and prints its own timing:

| Step | What happens | Measured duration | Disk |
|---|---|---|---|
| Build images | backend (Python 3.13, 469 MB) and web (Node 22 multi-stage, 340 MB) images | about 3 to 5 minutes the first time; seconds when cached | about 0.8 GB |
| Database migrations | PostGIS 16 starts, Alembic creates the camera inventory tables | 85 s on a fresh database | small |
| OSM extract | Geofabrik Colorado extract (385 MB) with MD5 verification into the `osm_extracts` volume | 46 s (27 s transfer) | 0.4 GB |
| Routing graph | Valhalla 3.9.1 builds time zones, admins, and tiles in a staging directory, then promotes | 207 to 296 s depending on other load, 3 GB memory peak | 1.1 GB |
| Basemap | Protomaps extract of the Denver envelope (90 MB) plus self-hosted fonts and sprites | about 25 s | 0.15 GB |
| First camera snapshot | one bounded Overpass query, validated and published | 61 to 87 s (the public instance sometimes answers 502 first; the job retries politely) | small |
| Geocoder | self-hosted Nominatim imports Colorado in the background | about 16 to 17 minutes, 5.2 GB memory peak; address search becomes available when done | 9.8 GB |
| Start and smoke test | `docker compose up -d` plus `scripts/smoke_test.ps1` | under 1 minute | - |

A complete run from a fresh checkout with cached images took 388 s on the pilot machine (geocoder skipped). Then open **http://127.0.0.1:3000** in a browser on this computer. Nothing is published beyond localhost.

Options: `-SkipGeocoder` leaves the geocoder out of this run (coordinates and map pins still work; the next `docker compose up` starts it and its one-time import); `-SkipBuild` reuses existing images.

If a step fails, fix the cause and rerun the script; every job is idempotent (already-downloaded extracts, already-built graphs, and already-imported geocoder data are reused).

## 2. Everyday startup

```powershell
docker compose up
```

(or `docker compose up -d` to run in the background). All services start, wait for their dependencies, and report healthy; nothing is rebuilt or re-downloaded. Stop with `Ctrl+C` or `docker compose down`.

**Data is kept** across restarts and `docker compose down`: the database, the routing graph, the extract, the basemap, the geocoder database, and camera snapshots live in named Docker volumes. **Do not run `docker compose down -v`** unless you intend to delete all of them; the next start would then need the full first-time setup again.

## 3. Using the planner

- **Start / Destination:** type an address or place name and press Search, then confirm one of the matches (matches inside the pilot area are listed first; the match type and any "outside the pilot area" note are shown); or type coordinates as `lat, lon` (a pair typed as `lon, lat` is recognised, swapped, and flagged for confirmation); or press "Use map pin" and click the map. A pin is labelled with the nearest mapped address or place by the local geocoder, while the pin's own coordinates are what gets routed. Address search needs the geocoder to have finished its import; until then the planner says so and coordinates and pins still work. There is deliberately no autocomplete: searches run only when you submit them.
- **Swap** exchanges start and destination. **km / mi** switches the displayed units; all values are converted on this computer from the engine's metres.
- **Snapping:** the route always starts and ends on the nearest drivable road. When that is more than 50 m from the point you chose, the route card says how far.
- **Status strip** under the title shows the road-data date, the camera snapshot date, whether address search is local-only, and the privacy promise.
- **Route preference** and **camera scope** are recorded with the request. In the M1 build only the Standard route is returned, and the Standard route is the fastest baseline candidate by the engine's reported time (which can differ from the engine's own first suggestion).
- **Maximum extra travel time** and the advanced relative limit will bound camera-aware alternatives in later milestones.
- **Plan route** sends the trip to the local backend; **Cancel** aborts; **Clear trip** removes the current inputs and result from the page. No trip is stored anywhere.
- Route cards show estimated time (no live traffic), distance, extra time versus Standard, the camera assessment (mapped record encounters on roads the route uses, uncertain nearby matches, records within 25/50/100 m, and whether the whole route lies inside the assessed area), the camera snapshot date, and the road-graph version. "Camera evidence" expands to one entry per nearby record with its status, distance, the road it sits on versus the road the route uses, the reason it was or was not counted, and a link to the record. Rings on the map mark the same records (red = counted, orange = uncertain, grey = beyond the counting radius). See `docs/ROUTING_METHOD.md` for the rules. Selecting a card updates the map and the street-by-street directions together. Pointing at (or tabbing to) a direction step highlights that part of the route on the map.
- **Show mapped cameras** draws records from the local snapshot when zoomed in. A legend counts the records in view: red for Flock-tagged, orange for another known manufacturer, grey for manufacturer unknown, faded with a dark outline for records that are no longer present in the source and are retained as uncertain, and no outline for records outside the assessed area. Clicking a dot shows the mapped status, manufacturer, operator, direction tag, whether it lies in the assessed area, last edit, check date, and a link to the record on OpenStreetMap; none of this is field-verified.
- **Data health** (bottom of the panel) shows the snapshot id and source date, counts of mapped records (including how many lie inside the assessed area and how many are retained as "no longer mapped"), what changed versus the previous snapshot, freshness, the last syncs, any snapshot waiting for operator review, the routing graph build date, and geocoder status. "Refresh view" reloads the panel; it does not trigger a sync.

## 4. Operator tasks

| Task | Command |
|---|---|
| Refresh the camera inventory now | `powershell -ExecutionPolicy Bypass -File scripts\sync_cameras.ps1` (the worker also runs every 6 hours while the stack is up) |
| Review a quarantined snapshot | `powershell -ExecutionPolicy Bypass -File scripts\review_snapshot.ps1 list`, then `... accept <snapshot_id> -Note "<what you corroborated>"` or `... reject <snapshot_id> -Note "<why>"`. A snapshot is quarantined when the source returns an empty result or the mapped ALPR count drops by more than half; the last good snapshot stays active until you decide. |
| Refresh the camera road-association cache (after a new snapshot or graph) | `powershell -ExecutionPolicy Bypass -File scripts\associate_cameras.ps1` (routes still assess correctly without it; uncached records are looked up live) |
| Look up one camera record's history | `GET http://127.0.0.1:3000/api/v1/cameras/record?source_key=osm:node:<id>` returns the current record and its versions across retained snapshots |
| After updating the code | `docker compose build`, then `docker compose --profile setup run --rm db-migrate`, then `docker compose up -d` (migrations are never applied silently) |
| Refresh road data and rebuild the graph | `powershell -ExecutionPolicy Bypass -File scripts\import_region.ps1` (add `-Force` to rebuild an unchanged extract) |
| Verify the stack, including a restart persistence check | `powershell -ExecutionPolicy Bypass -File scripts\smoke_test.ps1 -CheckRestart` |
| Follow the geocoder import | `docker compose logs -f geocoder` |
| Run the test suites | `docker compose --profile test run --rm api-tests`, `... web-tests`, `... e2e` (the last one needs the stack running) |
| Refresh the basemap | edit `PROTOMAPS_BUILD_URL` in `.env`, then `docker compose --profile setup run --rm basemap-extract` |

## 5. Privacy notes

- Requests from the browser go only to this computer (nginx on 127.0.0.1:3000). The API, database, routing engine, and geocoder are not published.
- The nginx access log is off; the API logs only method, path, status, and duration; request bodies, query strings, coordinates, and viewport bounding boxes are never logged, and a redaction filter guards against accidental leaks.
- The camera sync queries a fixed region on a schedule; it never sends a trip anywhere.
- Map tiles, fonts, and sprites are served from the local basemap volume; no tile request leaves the machine.
- Nothing is stored in the browser beyond the current page state.

## 6. Troubleshooting

- **"no completed routing graph" in the valhalla logs:** run `docker compose --profile setup run --rm graph-build`.
- **Route planning says the route engine is unavailable:** `docker compose ps` and `docker compose logs valhalla`; the graph may still be loading.
- **Address search "not configured" or "unavailable":** the geocoder import has not finished (`docker compose logs -f geocoder`), or `DEFLOCK_GEOCODER_URL` is unset. If Docker is stopped while the very first import is running, the import starts over on the next start (about 17 minutes); once it has completed, restarts are immediate.
- **Camera overlay empty:** zoom in (records load from zoom 11), or no snapshot has been published yet (Data health shows the sync state; run `scripts\sync_cameras.ps1`).
- **Map does not render:** the browser lacks WebGL; the planner, coordinates, and written directions still work.
- **Memory pressure:** the graph build and the geocoder import should not run at the same time; the first-time script runs them one after the other.
