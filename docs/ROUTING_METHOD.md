# Routing and assessment method (M4 state)

This page describes exactly how the application computes a route and how it decides which mapped camera records count as encounters. Everything here is implemented and tested; nothing is a claim about physical cameras.

## 1. Standard route

- The engine is a pinned, self-hosted Valhalla 3.9.1 with the Geofabrik Colorado extract. Only documented request options are used: `locations`, `costing=auto`, `units`, `alternates`, `id`. Legality options (`ignore_restrictions`, `ignore_oneways`, `ignore_access`, `ignore_closures`) stay at their defaults.
- The engine returns a primary route and up to two alternates. The **Standard route is the fastest of these by the engine's reported time** (decision 0001 D6), because the engine's primary result minimises an internal cost that its reported time does not include.
- Every candidate must have valid directions: a start maneuver first, a destination maneuver last, ordered shape indices covering the whole shape, and maneuver lengths within 3 % of the route length.
- Endpoint snapping is disclosed: the distance from each chosen point to the engine's actual start and end.

## 2. Encounter assessment of a route

### Stage A - proximity in meters

PostGIS geography (`ST_DWithin`, `ST_Distance`) finds every ALPR record of the active snapshot within the largest sensitivity radius (100 m) of the route line. Distances are meters on the spheroid; nothing is ever measured in degrees. The fraction of the route length inside the camera-data envelope is computed the same way; a route that leaves the envelope is only **partially** assessed.

### Stage B - road association

For each nearby record the application asks the engine which drivable roads lie within the counting radius (50 m) of the record (`/locate`, auto costing), keeps the nearest candidate per OpenStreetMap way, and compares them with the roads the route actually traverses near that point (`/trace_attributes` with `edge_walk`; only the route edges within 150 m along the route of the record's closest pass are considered). Roads are identified by their name set when they are named and by way id otherwise: OpenStreetMap splits one street into many consecutive ways, so two candidates with the same names near the same pass are the same road, while a same-named street elsewhere on the route is not.

| Outcome | Status | Counted as |
|---|---|---|
| the record's nearest road is one the route traverses and no other road is about as close | `associated` | matched |
| the route traverses the nearest road but a *different* road (by name set, or way id when unnamed) is within 10 m of being as close | `nearby_unresolved` (ambiguous) | uncertain |
| the nearest road is not on the route, but a route road is also within the radius; the two differ in bridge/tunnel status | `nearby_unresolved` (grade-separated crossing) | uncertain |
| the nearest road is not on the route, but a route road is within the radius | `nearby_unresolved` (parallel or frontage road) | uncertain |
| no drivable road within the radius, or the route road is not among the candidates | `nearby_unresolved` | uncertain |
| record is carried as "no longer mapped" | `no_longer_mapped` | uncertain |
| record lies outside the camera-data envelope | `outside_envelope` | uncertain |
| record is within 100 m but beyond 50 m | `beyond_radius` | sensitivity only |
| record is not in the selected scope (Flock-only) | `excluded_scope` | listed, not counted |

### Counting rules

- Each canonical record is counted once per route; repeated passes (loops) are reported as `pass_count`.
- Records within 10 m of each other form a *site group* for display; they are still counted individually.
- Mapped direction tags are reported as information (`heading_relation`) and never used to exclude a record in v1.
- Sensitivity: the number of in-scope records within 25, 50, and 100 m is reported next to the headline count.
- Zero matched records reads: "No mapped encounters detected by this assessment. Unmapped or mislocated cameras may still be present."
- When the database, the snapshot, the graph version, or the engine's edge services are unavailable, the result is `not_assessed` with null counts, never zero.

### Versions and cache

Every assessment records the snapshot id, the routing-graph version (`<graph id>@<tileset build time>`), the counting method version (`assess-1.0`), and the radius. Nearest-road candidates are cached per record and graph version (`camera_road_associations`); the cache is rebuilt by `scripts/associate_cameras.ps1` after a new snapshot or graph (`-Recompute` drops and rebuilds the current graph's rows after a method change) and is pruned when the graph changes. Uncached records are looked up live. The cached data are the raw candidates; the association verdict is always recomputed from them with the current rules.

## 3. What is not done yet

- Camera-aware candidate generation and comparison (Balanced, Fewest mapped cameras) is M5; the assessment above is reported for the Standard route only.
- Line of sight, lens orientation, capture direction, and physical detection range are not modelled and are not claimed.
