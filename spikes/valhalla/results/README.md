# Valhalla M0 spike results (2026-10-15)

Everything here was produced against `ghcr.io/valhalla/valhalla:3.9.1` serving a graph built from the Geofabrik Colorado extract (data as of 2026-10-14T20:21:12Z) on the pilot machine. Endpoints were public landmarks only. Raw request/response pairs are in `spikes/valhalla/output/` (not committed); the summaries here are committed as evidence.

## Reproduce

1. Download `colorado-latest.osm.pbf` into `data/raw/osm/` and verify its MD5 against Geofabrik's `.md5`.
2. `bash spikes/valhalla/run_build.sh` (Docker only; builds config, time zones, admins, tiles, and the tar inside the container into the `deflock_valhalla_spike` volume).
3. `docker run -d --name deflock-valhalla-spike -p 127.0.0.1:8002:8002 -v deflock_valhalla_spike:/data --entrypoint valhalla_service ghcr.io/valhalla/valhalla:3.9.1 /data/valhalla.json 2`
4. `python -I spikes/valhalla/route_spike.py --label <date>` and `python -I spikes/valhalla/route_spike_extra.py --label <date>` (host Python is used only for this development script).

## Build measurements (Colorado extract, concurrency 8, Docker Desktop with 8 GB allocated)

| Stage | Seconds |
|---|---:|
| valhalla_build_config | 0 |
| valhalla_build_timezones | 8 |
| valhalla_build_admins | 12 |
| valhalla_build_tiles | 105 |
| valhalla_build_extract | 2 |

Peak container memory 3.03 GiB (sampled every 10 s). Outputs: 599 tiles, 482 MB tile directory plus a 482 MB `tiles.tar`, 117 MB time-zone database, 6.7 MB admin database. Service idle memory about 55 MB. `/status` verbose reported `has_tiles`, `has_admins`, `has_timezones` all true and `tileset_last_modified` 2026-10-15T20:28:48Z.

## Synthetic avoidance test (Union Station to Denver Zoo)

Target: the shape point at 50 % of the reference route's length (39.779969, -104.966795), which lies on I-70.

| Request | Time s | Length km | Highway | Min distance to target m | Overlap with reference | Maneuver problems |
|---|---:|---:|---|---:|---:|---|
| reference (default auto) | 730.7 | 12.414 | yes | 0 | 1.000 | none |
| `exclude_locations` = target | 627.4 | 6.373 | no | 2140 | 0.146 | none |
| `exclude_polygons` = 80 m box | 627.4 | 6.373 | no | 2140 | 0.146 | none |
| `linear_cost_factors` factor 1 | 730.7 | 12.414 | yes | 0 | 1.000 | none |
| `linear_cost_factors` factor 50 | 627.4 | 6.373 | no | 2140 | 0.146 | none |

All avoidance responses carry complete maneuver lists with non-empty instructions (start type first, destination type last, monotonic shape indices). Full instruction lists are in `route_spike_2026-10-15.json`; the geometries are in `route_spike_2026-10-15_routes.geojson`.

## Other verified behaviours

- **ETA contamination:** a trip forced to start on a segment penalised with factor 1000 reported exactly the same time (420.987 s) and length as with factor 1. Soft penalties change path choice, not the reported travel time.
- **Alternates:** `alternates: 2` returned two genuinely different routes (overlap 0.146 and 0.056 with the primary).
- **Warnings:** requesting `exclude_highways` without server permission returned warning 208 "Hard exclusions are not allowed on this server, ignoring hard excludes". A location `radius` of 1000 m (above the 200 m default limit) produced no warning in this build.
- **Limits:** 51 `exclude_locations` returned HTTP 400 error 157 "Exceeded max avoid locations: 50"; an exclusion polygon with a 12 km perimeter returned error 167 "Exceeded maximum circumference for exclude_polygons: 10000 meters"; a destination outside the graph returned error 171 "No suitable edges near location".
- **Latency and payload (warm):** 30 to 146 ms per request across 6 to 40 km trips; responses 7 to 22 KB.
- **Legality evidence:** map-matching the avoidance routes with `trace_attributes` (`edge_walk`) showed 246 edges, traversability `forward` 203 and `both` 43, none `backward`; edge uses were `road` 241 and `driveway` 5 (destination access).

## Finding that changes the design: the engine's primary route is not always its fastest

For Union Station to Denver Zoo the default primary route (12.4 km via I-25 and I-70, 730.7 s) was slower than both alternates (627.4 s and 618.1 s on surface streets); `use_highways` 0.3 or 0.0 returned the 627.4 s route; `disable_hierarchy_pruning` did not change the primary; `shortest` returned a 4.99 km route reporting 542.9 s. The same pattern appeared for Zoo to Union Station (primary 687.1 s, alternate 581.1 s). For Capitol to Zoo and Union Station to Washington Park the primary was the fastest. Valhalla minimises an internal cost that includes turn and road-class preferences, and the reported time does not include those preferences. Consequence for the product: define the Standard route and the detour reference `T0` from the fastest reported time among the baseline candidates (primary plus alternates), and never present an avoidance route as "faster than standard" without that normalisation.

## Local detour on surface streets

With the surface-street route (via Stout Street) as reference and a target at 55 % of its length, `exclude_locations` and a factor-10 linear penalty both moved the whole route to 17th Street, Broadway, and Colfax Avenue (min distance 1408 m, 9 s faster). One-way grids make "small" detours unlikely; the candidate-search design must therefore assess every candidate's complete path rather than assume local changes.
