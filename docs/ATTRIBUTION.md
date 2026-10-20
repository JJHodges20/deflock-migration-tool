# Attribution, licenses, and public-service policies (v1.0 release candidate)

This page lists what the Denver pilot uses, what each source requires, and how the application meets it. The data
register in `docs/DATA_SOURCE_REGISTER.md` records when each source was inspected or executed and the exact URLs.
Nothing here grants a right to redistribute; it records the obligations as understood on 2026-10-19 for an invited,
local pilot. A public deployment needs its own review and the owner's separate approval.

## Data

| Data | Source | License and terms | How the pilot complies |
|---|---|---|---|
| Camera records (ALPR tags) | OpenStreetMap via a bounded Overpass API query of the Denver envelope | Open Database License 1.0 (ODbL); attribution "© OpenStreetMap contributors" required; derived databases must stay ODbL | Attribution shown in the planner footer, on the map, in Data Health, in the print layout, and in the GeoJSON export; the snapshot table records the license; the raw snapshots are kept as fetched; no derived database is redistributed |
| Road network | Geofabrik Colorado extract (OpenStreetMap data) | ODbL as above; Geofabrik asks for reasonable download frequency | Weekly rebuild cadence, one download per rebuild, checksum verified; attribution as above |
| Basemap | Protomaps PMTiles build (OpenStreetMap data), regional extract served locally | Protomaps builds are ODbL (OpenStreetMap) data; attribution "Protomaps © OpenStreetMap" | Attribution control on the map and in the footer; the extract is served from a local volume, never from Protomaps at runtime |
| Basemap fonts and sprites | Protomaps basemaps assets (fonts under the SIL Open Font License; sprites from the Protomaps basemaps repository) | OFL permits bundling with attribution; sprites follow the basemaps repository license | Downloaded once by a setup job to the local volume; served same-origin |
| Service boundary (Colorado, default since M9) | U.S. Census Bureau TIGERweb state boundary, GEOID 08, January 1, 2026 vintage | Public domain (U.S. federal government work); the layer says "Source: U.S. Census Bureau" | Used only to decide whether endpoints are inside the service area; attributed in the footer, Data Health, print, and export |
| Service boundary (Denver pilot configuration) | City and County of Denver Open Data, "County Boundary" | Provided "as is", "not for engineering purposes", custom disclaimer; not ODbL | Used only for the retained `denver.yaml` configuration; attributed separately; never merged into ODbL exports |
| Address search data | the same Geofabrik extract, imported into a self-hosted Nominatim | ODbL as above | Local only; the public OSMF Nominatim service is never called |
| Timezone boundaries used by the routing graph build | `evansiroky/timezone-boundary-builder` release shapefile (derived from OpenStreetMap), downloaded by `valhalla_build_timezones` | data ODbL (OpenStreetMap derived); builder code MIT | Downloaded once per graph build into the `valhalla_tiles` volume; used only to attach time zones to road edges |

## Software

| Component | License | Use |
|---|---|---|
| Valhalla 3.9.1 (`ghcr.io/valhalla/valhalla`) | MIT | routing engine, self-hosted |
| Nominatim 5.3.2 (`mediagis/nominatim`) | GPL-2.0 (Nominatim); image scripts per their repository | geocoder, self-hosted, not modified or redistributed |
| PostgreSQL 16 with PostGIS 3.4 | PostgreSQL License; GPL-2.0 (PostGIS) | inventory database |
| nginx 1.28 | BSD-2-Clause | local edge |
| Next.js 16, React 19 | MIT | web planner |
| MapLibre GL JS 6 | BSD-3-Clause | map rendering, worker self-hosted |
| pmtiles, @protomaps/basemaps | BSD-3-Clause | basemap protocol and style |
| FastAPI, Pydantic, SQLAlchemy, GeoAlchemy2, httpx, shapely, PyYAML, psycopg, Alembic | MIT / BSD / LGPL (psycopg: LGPL-3.0, used unmodified) | API and workers |
| Playwright, Vitest, axe-core | Apache-2.0 / MIT / MPL-2.0 | tests only, not shipped |

The project's own license has not been chosen by the owner; until it is, the repository carries no license grant.

## Public-service policies

| Service | Policy | What the pilot does |
|---|---|---|
| Overpass API (overpass-api.de) | shared resource; identify the application; keep load low; no end-user backend use at scale; no rotation to evade limits | one fixed envelope query every 6 hours while the stack runs (4 per day), operator refreshes share a 30 min cooldown, one request at a time, an identifying User-Agent, a 30 s pause after HTTP 429/406, bounded retries, no endpoint rotation; the register notes the move to the Geofabrik extract before any public rollout |
| Geofabrik downloads | public extracts and change files, be reasonable | one 385 MB download per weekly rebuild, checksum verified; since M10 one state request and the day's change file per day for the camera inventory (the worker seeds its copy from the graph's extract) |
| Protomaps build server, GitHub (basemap assets, timezone boundaries) | public downloads | one-time setup downloads and one per graph rebuild; no runtime traffic |
| OpenStreetMap Foundation Nominatim and tile servers | usage policies forbid heavy or application-backend use | not used at all; the planner reaches only this computer |
| U.S. Census Bureau TIGERweb (Colorado boundary) | public data service; no key or agreement needed for one download | one download per boundary version; attributed |

## Independence statement

DeFlockMigration is an independent project. It is not affiliated with or endorsed by DeFlock, Flock Safety,
OpenStreetMap, the OpenStreetMap Foundation, Protomaps, Geofabrik, the U.S. Census Bureau, or the City and County of Denver. It does not use
DeFlock's interface or branding; it reads the same public OpenStreetMap records through the documented Overpass API.
