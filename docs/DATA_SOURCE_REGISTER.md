# DeFlockMigration - Data Source Register

**Checked:** 2026-10-15 (Milestone 0). Quotes are verbatim from the pages fetched that day; recheck before each release because policies change without notice.
**Status key:** *executed* = this project actually fetched/ran it in M0; *inspected* = documentation read only; *not used* = reviewed and rejected or deferred.

Nothing in this register is a complete camera inventory, a deployment plan, or a guarantee of provider availability.

---

## 1. OpenStreetMap ALPR records via the Overpass API - *executed (M0 to M9); the Colorado configuration moved to section 2 in M10*

- **Endpoint used:** `https://overpass-api.de/api/interpreter` (main public instance, Overpass API 0.7.62.11).
- **Policy pages:** https://dev.overpass-api.de/overpass-doc/en/preface/commons.html and https://wiki.openstreetmap.org/wiki/Overpass_API
- **What it provides:** `man_made=surveillance` records tagged `surveillance:type=ALPR` (plus Flock-branded aliases) inside a fixed bounding box, with element version and source edit timestamp. Output is OSM data under ODbL; the Overpass software is AGPL v3.
- **Policy terms that bind this project:**
  - "users are expected to send a maximum of about 10000 requests per day" and "keep their download volume below about 1 GB per day"; for anything regular, "divide those numbers by 100", i.e. "less than 100 queries fetching less 10 MB of data per day fine".
  - Listed as a don't: "Setting up an app for more than just OSM mappers and relying on the public instances as backend."
  - "If you receive an HTTP error code such as 429 or 406, pause for 30 seconds before making a new request"; "No parallel running of multiple scripts".
  - "Be sure to check that your app or website adds User-Agent or Referer headers to requests that uniquely identify your app".
  - "Commercial use should use self-hosted or paid Overpass servers"; "Nowadays this server is overloaded - be mindful of that".
  - Defaults: "If no maximum run time is declared then a default limit of 180 seconds applies", memory "512 MiB". Rate-limited requests get HTTP 429; resource denial 504.
- **M0 usage record:** query file `data/raw/overpass/denver_alpr_envelope_query.overpassql`; first attempt 2026-10-15T20:18:05Z returned HTTP 502 from the instance's nginx; second attempt 20:19:15Z to 20:20:26Z succeeded; 1,591 nodes, 785,686 bytes; `timestamp_osm_base` 2026-10-15T20:18:00Z; raw SHA-256 `6ffd2e80...2802c79d` (full value in `data/manifests/overpass_snapshot_2026-10-15.json`). User-Agent identified the project. No contributor identity fields are kept in committed fixtures.
- **Pilot design decision:** a fixed-region sync every 6 hours (4 queries/day, under 1 MB each) sits far below the "divide by 100" ceiling and is acceptable for development and an invited pilot. Public rollout must move the inventory to the Geofabrik extract pipeline (section 2) or a self-hosted Overpass instance. Never derive the query from a user's trip; never rotate endpoints to evade limits; honor the 30-second pause rule on 429/406.

- **M10 (decision 0004):** the Colorado configuration no longer queries this instance; the camera inventory comes from the Geofabrik extract and its change files (section 2). The Denver pilot configuration still runs the bounded query, and the Colorado query file stays on disk as a documented fallback.

## 2. Geofabrik Colorado extract and daily diffs - *executed (download + checksum; change files applied since M10)*

- **Pages:** https://download.geofabrik.de/north-america/us/colorado.html , https://download.geofabrik.de/technical.html , https://download.geofabrik.de/north-america/us/colorado-updates/
- **License:** page footer "Data processed by Geofabrik GmbH and created by OpenStreetMap Contributors | License: ODbL 1.0". No stated rate limit or fair-use quota; robots.txt only blocks crawlers from the data files.
- **File fetched:** `colorado-latest.osm.pbf`, 384,780,419 bytes (page shows "366 MB"), Last-Modified 2026-10-15 03:05:49 GMT, "contains all OSM data up to 2026-10-14T20:21:12Z". MD5 verified against the published `.md5` (`39e228e284bb5224fcb1440636078978`); SHA-256 `4619ce93...39873cb`. Download took 27 seconds.
- **Diffs:** daily `.osc.gz` files exist (`state.txt`: `timestamp=2026-10-14T20:21:12Z`, `sequenceNumber=4941`); "Diff files are kept for 100 days and then deleted." "The user, uid and changeset fields are missing in these files since May 3, 2018."
- **Use:** routing-graph input (Valhalla) and the planned scale adapter for camera records. Outline `colorado.poly` fetched; it fully contains the 20 km Denver envelope with a 102 km margin.
- **Plan:** one extract download per graph rebuild; diffs at most once per day, matching Geofabrik's cadence.
- **M10 usage (decision 0004):** the camera-sync worker copies the routing graph's extract as its seed and applies the daily change files with pyosmium 4.3.2 (`ReplicationServer`: identifying User-Agent, one request at a time, 30 s pause after HTTP 429/503, three attempts, no retries inside the HTTP library). Probe on 2026-10-19: the extract header carries `osmosis_replication_base_url` `.../colorado-updates`, sequence 4945, timestamp 2026-10-18T20:25:06Z; applying three change files and rewriting the 385 MB file took 13 s at 309 MB resident; reading the camera records from the file takes about 5 s. The outline `colorado.poly` (15 vertices, kept under `data/boundaries/raw/` and as `data/boundaries/geofabrik_colorado_outline_v1.geojson`) follows the state line within about 300 m, which is why the camera-data envelope v2 stops there. Cadence: one state request per day plus the day's change file; a full download only when no seed exists or the needed change files are gone (kept about 100 days).

## 3. OSM tagging documentation for ALPR cameras - *inspected*

- **Pages:** https://wiki.openstreetmap.org/wiki/Tag:surveillance:type%3DALPR , https://wiki.openstreetmap.org/wiki/Key:surveillance:type , https://wiki.openstreetmap.org/wiki/Key:camera:direction , https://wiki.openstreetmap.org/wiki/Key:direction (documentation is CC BY-SA 2.0)
- **Documented scheme:** `man_made=surveillance` + `surveillance=public|outdoor|...` + `surveillance:zone=traffic|parking|entrance` + `surveillance:type=ALPR`; "Implies camera:type=fixed"; `camera:mount=pole`; `manufacturer=Flock Safety` ("The largest vendor of ALPR devices in the United States."), `manufacturer=Axis Communications`; `operator=*` "is often revealed (typically, a police department or a Home Owners Association/HOA)"; lifecycle prefixes `removed:*` ("officially removed or decommissioned"), `destroyed:*`, `was:*`.
- **Direction:** `direction=*` is "The direction that the camera is pointed toward; usually expressed as a number representing degrees clockwise from north"; the page states "a preference for direction=* is given" over `camera:direction`. Ranges such as `315-45` are read clockwise. Neither page says device orientation equals recorded traffic direction, so the product must not infer it.
- **Listed tagging mistakes to accept as aliases during ingestion:** `camera:type=ALPR`, `surveillance=ANPR`, `surveillance=license_plate_scanner`, `surveillance:type=ANPR`, `brand=Flock Safety`, `operator=Flock Safety`, `name=Flock Falcon`.
- **What the real Denver-region snapshot showed (see `docs/evidence/overpass_alpr_tag_summary_2026-10-15.md`):** 1,538 `surveillance:type=ALPR`, 37 `camera`, 14 `gunshot_detector` (matched only through Flock branding and must be excluded from ALPR counts); manufacturer present on 1,413 records (Flock Safety 1,291; Axon 37; Neology 25; Motorola 18; Axis 14; Leonardo 13; Genetec 6; LiveView 4; others), absent on 178; `direction` numeric on 1,439, ranges on 61, multi-valued on 46, absent on 45; `camera:direction` on only 21 records, conflicting with `direction` on 5 of the 7 records that carry both; `check_date` on 4 records only; no lifecycle-prefixed keys at all; 98 pairs of records within 10 m of each other (multi-camera poles or duplicates to keep separate).

## 4. DeFlock project - *inspected, not a data source*

- **Pages:** https://github.com/FoggedLens/deflock (MIT license, default branch `master`, last push 2026-10-09); https://wiki.openstreetmap.org/wiki/Deflock ; deflock.me redirects to deflock.org, whose pages are a JavaScript app that could not be read as text.
- **Finding:** DeFlock describes itself as a "Crowdsourced tool for locating and reporting ALPRs" that uses "OpenStreetMap data to populate a map with crowdsourced locations of ALPRs"; its map data lives in OSM and its own API/R2 storage has no published usage terms.
- **Decision:** consume OSM directly (sections 1 and 2). Do not scrape DeFlock's map or depend on its API or R2 files. Do not present DeFlockMigration as affiliated with DeFlock.

## 5. OpenStreetMap copyright, ODbL and attribution - *inspected*

- **Pages:** https://www.openstreetmap.org/copyright , https://osmfoundation.org/wiki/Licence/Attribution_Guidelines , ODbL 1.0 text, OSMF Produced Work and Substantial guidelines.
- **Obligations:** "Provide credit to OpenStreetMap by displaying our attribution notice."; "Make clear that the data is available under the Open Database License."; "If you alter or build upon our data, you may distribute the result only under the same license."; for browsable maps "the credit should typically appear in a corner of the map."; databases "must include attribution to OpenStreetMap and either the text of the ODbL or a link to it".
- **Derivative database analysis:** the Substantial guideline treats fewer than 100 features as insubstantial and notes "we regard repeated small extractions as one big extraction!" The Denver camera inventory (1,591 records, refreshed repeatedly) is therefore a Derivative Database. "Attribution is only necessary when a Produced Work is used Publicly", so an invited pilot has lighter duties, but the plan is to attribute from day one and, before any public use, to offer the derived camera table (or the diff from OSM) in machine-readable form under ODbL.
- **Attribution text to use:** "© OpenStreetMap contributors" with a link to https://www.openstreetmap.org/copyright on every map view and on data exports.

## 6. City and County of Denver "County Boundary" dataset - *executed (download)*

- **Pages:** https://opendata-geospatialdenver.hub.arcgis.com/datasets/53a0ae35c018471788efe36b6f730a79_40/explore ; service `https://services1.arcgis.com/zdB7qR0BtYrg0Xpl/arcgis/rest/services/ODC_ENG_SRVCCDBOUNDARY_A/FeatureServer/40`
- **Fetched:** `.../FeatureServer/40/query?where=1%3D1&outFields=*&outSR=4326&f=geojson` on 2026-10-15T20:28:12Z (SHA-256 `487d6cd4...02fbec`); 12 polygon features: COUNTY=Denver 2, Arapahoe 7, Jefferson 3 (the enclaves). Native CRS is EPSG:2877 (Colorado Central, US feet); the Hub's GeoJSON export keeps projected coordinates, so the FeatureServer query with `outSR=4326` is the one to use. Layer `lastEditDate` 2026-04-09T23:27:23Z; item modified 2024-05-28; lineage note "Data update of the municipal boundary between Glendale and Denver."
- **Terms:** item `licenseInfo` is a custom disclaimer: data "IS PROVIDED AS IS WITHOUT WARRANTY OF ANY KIND" and "NOT FOR ENGINEERING PURPOSES." It is not ODbL; keep it as a separate attribution ("Boundary: City and County of Denver") and do not merge it into ODbL-licensed exports.
- **Use:** service boundary `denver-service-v1` (400.47 km², airport arm included and contiguous, 10 enclave holes); see `docs/evidence/boundary_analysis_2026-10-15.md`.
- **Alternative not used:** OSM relation 1411339 (`official_name=City and County of Denver`, `admin_level=6`), available under ODbL if the official layer ever becomes unavailable.

## 6b. U.S. Census Bureau TIGERweb state boundary - *executed (download, M9)*

- **Pages:** https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer (layer 0 "States", January 1, 2026 vintage)
- **Fetched:** `.../MapServer/0/query?where=GEOID='08'&outFields=*&outSR=4326&f=geojson` on 2026-10-19T21:45:57Z; one Polygon feature, 7,519 vertices, 307,051 bytes, SHA-256 `ffdc7e51bbfbb67f...`; `AREALAND` 268,419 km², `AREAWATER` 1,185 km²; raw file and layer metadata kept under `data/boundaries/raw/`.
- **Terms:** Census Bureau data are in the public domain in the United States; the layer's copyright text is "Source: U.S. Census Bureau". Attributed as "Boundary: U.S. Census Bureau TIGERweb state boundary (public domain)".
- **Use:** service boundary `colorado-service-v1` (269,604.5 km² by geography area) and, buffered 20 km in EPSG:26913 and clipped to the routing graph extent, the envelope `colorado-envelope-v1-20km` (311,081 km²). The Denver boundary from the City and County of Denver remains the source for the retained `denver.yaml` configuration.

## 7. Valhalla routing engine - *executed (pinned container build + spike)*

- **Pages:** https://valhalla.github.io/valhalla/api/route/api-reference/ , https://raw.githubusercontent.com/valhalla/valhalla/master/scripts/valhalla_build_config , https://raw.githubusercontent.com/valhalla/valhalla/master/docker/README.md , https://raw.githubusercontent.com/valhalla/valhalla/master/docs/docs/api/status.md , https://github.com/valhalla/valhalla/pkgs/container/valhalla
- **Software license:** MIT (Valhalla repository). Road data remains ODbL.
- **Pinned build:** `ghcr.io/valhalla/valhalla:3.9.1` (release 3.9.1 published 2026-10-06; image digest `sha256:4fd114eb1d26b8fc2f43bcb3df234c1b63a0bf13c277405e5943d5361dc575de`, 927.6 MB, Ubuntu 24.04, no entrypoint). A `ghcr.io/valhalla/valhalla-scripted:3.9.1` image exists with an entrypoint that builds tiles from `custom_files/*.pbf`; the former gis-ops image is archived and must not be used.
- **Documented capabilities verified against 3.9.1 in `spikes/valhalla/results/`:**
  - `exclude_locations`: "mapped to the closest road or roads and these roads are excluded from the route path computation" (hard). Limit `max_exclude_locations: 50`; the 51st returns HTTP 400, error 157 "Exceeded max avoid locations: 50".
  - `exclude_polygons`: "Roads intersecting these rings will be avoided during path finding." Limits `max_exclude_polygons_length: 10000` meters total perimeter and `max_exclude_polygons_vertices: 100`; exceeding the perimeter returns error 167.
  - `linear_cost_factors`: "edges with factors larger than 1 will be increasingly avoided" (soft, per matched edge); `min_linear_cost_factor: 1`, `max_linear_cost_edges: 50000`; added in 3.6.2. A factor of 1000 on a forced segment left the reported trip time unchanged.
  - `alternates`: "There may be no alternates or less alternates than the user specifies"; `max_alternates: 2`; not for multipoint or time-dependent routes.
  - Hard exclusions (`exclude_highways` etc.) require `service_limits.allow_hard_exclusions`; otherwise warning code 208 "Hard exclusions are not allowed on this server, ignoring hard excludes".
  - Legality defaults to keep: `ignore_restrictions`, `ignore_oneways`, `ignore_access`, `ignore_closures` all default `false`; `shortest` disables all penalties and stays `false`.
  - `/status` with `verbose: true` reports version, `tileset_last_modified`, `has_admins`, `has_timezones`, and the tileset bounding box.
- **Not found in the documentation:** any `camera_penalty`, `hard_exclude`, or per-point soft penalty parameter. Camera points must become `linear_cost_factors` linestrings or `exclude_locations` points.

## 8. Public Nominatim usage policy - *inspected, not used*

- **Page:** https://operations.osmfoundation.org/policies/nominatim/
- **Terms:** "No heavy uses (an absolute maximum of 1 request per second)."; "Provide a valid HTTP Referer or User-Agent identifying the application"; auto-complete "is not yet supported by Nominatim and you must not implement such a service on the client side using the API."; "Applications and services whose primary function is related to geocoding must run their own service."; "Please do not submit personal data or other confidential material to any of our services."; "Code generated by LLMs must adhere to all terms laid out in this policy."; the policy "may change without notice" and "does not apply to nominatim services run by yourself".
- **Decision:** not enabled. Trip origins and destinations are personal data, which the policy asks users not to submit. A self-hosted regional instance (section 9) is the default; enabling the public service for a small pilot would need the owner's explicit approval plus a submit-only search, a 1 request/second cap, caching, and an identifying User-Agent.

## 9. Self-hosted Nominatim (regional) - *executed (containerized Colorado import spike)*

- **Pages:** https://nominatim.org/release-docs/latest/admin/Installation/ , https://nominatim.org/release-docs/latest/admin/Import/ , https://nominatim.org/release-docs/latest/customize/Tiger/ , https://github.com/mediagis/nominatim-docker
- **Requirements:** PostgreSQL "12+ will work, 13+ strongly recommended", PostGIS "3.0+ will work, 3.2+ strongly recommended"; "A minimum of 2GB of RAM is required or installation will fail."; planet-scale numbers (128 GB RAM, 1 TB disk) do not apply to a state extract; "First try the import with a small extract, for example from Geofabrik."; `--osm2pgsql-cache` "approximately to the size of the OSM pbf file".
- **Image pinned for the spike:** `mediagis/nominatim:5.3.2` (1.53 GB, created 2026-06-23). Env vars `PBF_PATH`, `REPLICATION_URL`, `IMPORT_STYLE`, `IMPORT_TIGER_ADDRESSES`, `IMPORT_US_POSTCODES`, `IMPORT_WIKIPEDIA`, `THREADS`, `POSTGRES_*`; database volume `/var/lib/postgresql/16/main`.
- **Optional US extras needing approval before download:** TIGER address data ("The entire US adds about 10GB to your database."), Wikipedia importance ("The files are about 400MB and add around 4GB"). Neither was downloaded in M0.
- **Photon** (https://github.com/komoot/photon): builds its index from a Nominatim database and needs Java 21+; a possible later add-on for typo-tolerant search, not required for v1.
- **Spike result (executed 2026-10-15):** Colorado import 16 min 55 s end to end, 9.77 GB database volume, 5.19 GiB peak memory, local queries 16 to 61 ms with correct results for the tested landmarks and public addresses; details in `docs/FEASIBILITY_REPORT.md` section 6.3.

## 10. OpenStreetMap public raster tiles - *inspected, not used*

- **Page:** https://operations.osmfoundation.org/policies/tiles/
- **Terms:** "Apps must configure a distinct, stable User-Agent naming your app"; "Bulk download ("scrape") tiles or offer prefetch features." is prohibited; "Offline use is not permitted on tile.openstreetmap.org."; "Availability is best-effort: there is no SLA or guarantee."; attribution must be shown "clearly on the map (typically bottom-right)".
- **Decision:** not used. A locally served PMTiles archive (section 11) replaces it and keeps map viewing private.

## 11. Protomaps basemap (PMTiles) - *executed (regional extract)*

- **Pages:** https://docs.protomaps.com/basemaps/downloads , https://docs.protomaps.com/pmtiles/cli , https://docs.protomaps.com/basemaps/maplibre , https://github.com/protomaps/basemaps , https://github.com/protomaps/basemaps-assets
- **License:** daily builds are "distributed as an Open Database License Produced Work" ("OpenStreetMap attribution required"); basemaps code BSD-3, "Map design is CC0", fonts Noto Sans under the SIL Open Font License, sprites derived from MIT-licensed icons. Attribution to show: `Protomaps © OpenStreetMap` with links (the archive's own metadata carries "© OpenStreetMap").
- **Terms:** "Please note that URLs may change and hotlinking to these downloads are discouraged." so the extract is stored locally; "To download a cutout of a specific region ... see the CLI's extract command."; "A full planet file is roughly 120 gigabytes" (build metadata reported 138.9 GB for 2026-10-15).
- **Executed:** `protomaps/go-pmtiles:v1.31.2` ran `pmtiles extract https://build.protomaps.com/20261015.pmtiles ... --bbox=-105.34301,39.4341,-104.36565,40.09437 --maxzoom=15`: 9,616 tile entries, 90,280,588 bytes, 50 HTTP range requests, 9.7 seconds. Archive metadata: Protomaps Basemap 4.15.2, OSM replication time 2026-10-15T04:00:00Z. File: `data/raw/basemap/denver_envelope_z15_20261015.pmtiles` (not committed).
- **Serving plan:** a static HTTP server with range-request support inside Compose, MapLibre `pmtiles://` protocol, self-hosted fonts and sprites from the basemaps-assets ZIPs, so no tile request leaves the machine.

## 12. MapLibre GL JS - *not fetched in M0*

- **Page:** https://maplibre.org/maplibre-gl-js/docs/ (to be read when the version is pinned in M1; license per the repository, expected BSD-3-Clause, verify then).
- **Role:** renderer only; it is not a map-data subscription.

## 13. PostGIS ST_DWithin - *inspected*

- **Page:** https://postgis.net/docs/ST_DWithin.html
- **Terms:** "For geometry: The distance is specified in units defined by the spatial reference system of the geometries." "For geography: units are in meters and distance measurement defaults to use_spheroid = true."
- **Rule for this project:** proximity queries use `geography` (meters) or a projected metric SRID; never a degree-valued buffer on EPSG:4326 geometry.

## 14. Container images pinned in M0

| Image | Digest / size | Purpose | Software license |
|---|---|---|---|
| `ghcr.io/valhalla/valhalla:3.9.1` | `sha256:4fd114eb...` 927.6 MB | routing graph build and service | MIT |
| `mediagis/nominatim:5.3.2` | 1.53 GB | regional geocoder spike | Nominatim GPL-2.0+; image repo license to confirm in M1 |
| `protomaps/go-pmtiles:v1.31.2` | small | basemap extract/serve | BSD-3 |

PostGIS and application base images will be pinned in M1.
