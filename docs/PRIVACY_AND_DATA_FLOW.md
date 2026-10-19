# Privacy and data flow (v1.0 release candidate)

Privacy is part of the implementation, not just the name. This page states what moves where, what is stored, and what is never stored.

## Data flows

| Flow | Path | Leaves the machine? | Stored? |
|---|---|---|---|
| Trip planning (origin, destination, preferences) | browser → nginx edge (127.0.0.1:3000) → api → valhalla, all on the Compose network | no | no: the API keeps it in memory for the request only; the UI keeps it in page state until Clear trip or reload |
| Address search | browser → edge → api → self-hosted geocoder container | no | no; the geocoder is a local Nominatim with no access log configured by this project |
| Device location (optional "Use my location") | browser geolocation API, read once on an explicit click; the coordinates then follow the map-pin path (reverse lookup on the local geocoder, routing on the local engine) | no | no: never watched, never stored; it lives in page state until Clear trip or reload |
| Print and GeoJSON download of a planned route | browser only: the print dialog and a file written by the browser on the user's computer | no | only where the user saves or prints it; nothing is uploaded, and the file warns that other apps may recalculate the path |
| Coordinate entry (`lat, lon`) | parsed by the API without any provider call | no | no |
| Camera overlay for the current map view | browser → edge → api → PostGIS (`camera_records`) | no | no; the viewport bounding box is in a query string that nginx does not log and the API never logs |
| Map tiles, fonts, sprites | browser → edge → static files in the `basemap` volume | no | public data only |
| Camera inventory refresh | `camera-sync` worker → public Overpass API, one fixed bounding-box query every 6 hours | yes, the fixed Denver envelope query with an identifying User-Agent and no personal data | yes: public OSM records, snapshot metadata, sync job records (PostGIS) and raw snapshot files (`camera_snapshots` volume) |
| Road data | `osm-download` setup job → Geofabrik; `graph-build` job inside the Valhalla container, which also downloads the timezone boundary shapefile from the GitHub release of `evansiroky/timezone-boundary-builder` (found by the fresh-install test in M8; the job therefore joins the egress network) | yes, two public downloads (extract, timezone boundaries) | yes: the extract (`osm_extracts` volume) and the graph with its timezone and admin databases (`valhalla_tiles` volume) |
| Basemap | `basemap-extract` and `basemap-assets` jobs → Protomaps build server and GitHub | yes, public data downloads | yes: `basemap` volume |
| Geocoder data | `geocoder` container imports the local extract | no (uses the downloaded extract) | yes: `geocoder_db` volume |

No analytics, session replay, advertising SDKs, error-reporting services, or external fonts are used. The web page is served with `robots: noindex`.

## Logging rules (implemented and tested)

- nginx: `access_log off`; only warnings and errors go to stderr.
- API: Uvicorn's access log is disabled; the request middleware logs method, path, status code, and duration only. Query strings and bodies are never logged. A redaction filter masks coordinate pairs, `lat=`/`lon=`/`bbox=`/`q=` style values, JSON keys, and query strings in any log line, including exception traces (`backend/tests/privacy`).
- Worker and setup jobs log counts, statuses, and sanitized error types, never payload content.
- Nothing from a request is written to the database: the only tables are public camera snapshots, camera records, and sync jobs.

## Service metrics (M7)

`GET /api/v1/health/metrics` reports request counts and latency summaries per declared route template, plan outcomes by search status, routing calls, process memory, and public-data storage sizes. The numbers are kept in the API process memory only and contain no coordinates, addresses, shapes, bodies, or query strings; the contract and browser tests assert their absence. Sync job rows record outcomes and counts of public records, never a trip.

## Storage rules

- Browser: no localStorage, sessionStorage, IndexedDB, cookies, or service-worker caches for trips. Clear trip resets page state.
- URLs never contain trip coordinates (the planner uses POST bodies).
- Named Docker volumes hold only public data and the local database credentials you set in `.env` (git-ignored).

## Network exposure

- Only nginx is published, on `127.0.0.1:3000`. PostGIS, Valhalla, the geocoder, the API, and the web server are reachable solely on the internal Compose network.
- CORS is closed by default (same-origin through the edge); `DEFLOCK_CORS_ORIGINS` exists only for development against a separately published API.
- Request bodies are limited to 64 KB at the edge and in the API; camera viewport queries are limited to 0.6 degrees per side.

## Network layout and egress audit (executed 2026-10-19)

The Compose stack uses two networks. `internal` is a Docker internal network with no route outside the machine; `web`, `api`,
`db`, `valhalla`, and `geocoder` are attached to it only. `egress` is an ordinary bridge; only `camera-sync` (the Overpass
query), the public-data setup jobs (`osm-download`, `graph-build` for the timezone boundaries, `basemap-extract`, `basemap-assets`, `camera-sync-once`), and `edge`
(which publishes 127.0.0.1:3000 and never initiates a connection) join it. `scripts\audit.ps1 -Check egress` probes every
running container; on 2026-10-19 the api, web, valhalla, db, and geocoder containers had no internet route (name resolution
or connection failed), the edge's probe timed out, and only camera-sync reached the public Overpass instance. The browser
privacy suite (`apps/web/e2e/privacy.spec.ts`) shows that a complete session makes requests to this origin only, sends trip
details only in POST bodies, writes nothing to browser storage, sets no cookie, registers no service worker, and keeps
coordinates out of the address bar. `scripts\audit.ps1 -Check logs` makes a plan, an address search, a reverse lookup, a
camera viewport query, and an outside-area plan, then searches every container log for the coordinates, the address, the
bounding box, and the landmark names: zero hits, with the nginx access log off and the API logging method, path template,
status, and duration only.

## Remaining limitations

- The stack is local only by design: no TLS, no authentication, no rate limiting beyond the request body limit and the bounded search. Publishing it on a network needs its own review and the owner's approval.
- The geocoder container's own logging configuration is the image's default (no project hardening beyond keeping it on the internal network and never logging its queries in this application).
- Operator actions are scripts and CLIs on the machine that runs the stack; there is no operator endpoint, which is the chosen design for a local pilot.
- Service metrics are kept in the API process only and never written anywhere; they contain no trip data, as the tests assert, but they are visible to anyone who can reach the local port.
