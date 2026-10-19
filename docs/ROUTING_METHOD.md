# Routing and assessment method (M5 state)

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

## 3. Camera-aware candidate search and comparison (M5)

The engine does all path finding. The application only decides what to ask it, assesses every answer over its whole path, and ranks honestly.

### Candidate generation (decision 0001 D5)

1. **Baseline:** one request with default costing and `alternates: 2`. The fastest candidate by reported time is the Standard route (`T0`). Every valid baseline candidate is assessed.
2. **Targets:** every counted encounter (matched or uncertain) of every assessed candidate becomes a short piece of that candidate's own geometry (60 m on each side of the pass). Records within 100 m of the start or destination cannot be avoided by any route; they are reported, never targeted.
3. **Soft penalties:** `linear_cost_factors` on all target pieces with an escalating factor (10, then 40, then 160). The factor is an artificial search cost; the engine's reported time stays physical (verified in M0 and re-checked by the synthetic tests).
4. **Hard exclusions:** one `exclude_locations` request (at most 50 points, never inside the endpoint margin) targeting the counted encounters of the current best candidate, used after the strongest penalties stop producing new candidates. If the engine reports no drivable route for that request, the fact is disclosed and the search converges.
5. **Repeat** penalized requests at the maximum factor while new candidates keep appearing. Targets accumulate, so the search learns the cameras along the corridor rather than only those on the first route.
6. **Stop** when a fully assessed candidate with zero exposure exists within the tightest requested limit, when no request produces a new candidate (converged), when the routing-call budget (8 per trip, baseline included) is used up, or when the planning deadline (20 s) is reached.

Every engine answer is de-duplicated by geometry, validated (start and destination maneuvers, ordered indices covering the whole shape), and assessed over its entire path against the whole camera envelope exactly like the Standard route. Legality options are never touched.

### Ranking (roadmap section 10.4)

Exposure `E(r)` is the matched plus uncertain record count of a route, each record once. For each preference, among fully assessed candidates with `T(r) <= min(T0 + max_extra, factor x T0)`:

| Preference | Default limit | Rule |
|---|---|---|
| Standard | none | the engine's time-focused reference |
| Balanced | 600 s or 1.50 x `T0` (the user's extra-time control replaces both) | minimise `E(r)`, then duration, then distance, then a geometry key |
| Fewest mapped cameras found | 1,200 s or 1.75 x `T0`, never tighter than the user's limit | same rule |

Ties never favour a longer route, so a longer route with unchanged exposure is never presented as a benefit. Candidates that leave the assessed envelope are excluded from ranking and reported as not ranked. A preference whose best feasible candidate is the Standard route is labelled on the Standard card with the message that no lower-exposure route was found within the limit. Preferences that choose the same path share one card. When the camera assessment is unavailable the preferences are reported as `not_assessed`; nothing degrades silently to the Standard route.

### Disclosure

Every response carries a `search` block: status (`completed`, `budget_exhausted`, `partial`, `not_run`), routing calls used and budget, deadline and elapsed time, candidates generated and assessed, notes (convergence, budget, deadline, engine failures, unavoidable records, unranked partial candidates), one outcome per requested preference with its limit and bound, and the method version (`search-1.0`). The result is always "best among the candidates evaluated", never a proof of a globally optimal camera-minimum path.

## 4. What is not done yet

- Line of sight, lens orientation, capture direction, and physical detection range are not modelled and are not claimed.
- The complete trip-planning experience (M6), scheduled operations (M7), and the pilot audit (M8) follow.
