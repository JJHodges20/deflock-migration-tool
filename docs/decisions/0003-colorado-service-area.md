# Decision 0003: Colorado service area, personal use only, and the ingestion path (2026-10-19)

## Decisions by the owner

1. **No public use for now.** The v1.0 release candidate (tag `v1.0.0-rc1`) is used by the owner personally on the pilot machine. Any public deployment needs its own, separate approval, as the roadmap requires. No invitation to pilot users has been made.
2. **Expand the service area to all of Colorado.** Trips may start and end anywhere in the state. Neighbouring states stay outside even where the routing graph has roads near the state line.
3. **Two milestones:** M9 (this record) makes Colorado the configured service area; M10 moves camera ingestion from the public Overpass instance to the Geofabrik extract that the project already downloads, with daily diffs, so the planner no longer depends on a shared public endpoint.
4. **Licensing is deferred.** The repository carries no license grant until the owner chooses one; for personal use none is needed.

## M9 choices (recommended by Claude, approved by the owner)

- **Boundary source:** the U.S. Census Bureau TIGERweb state boundary (layer "States", GEOID 08, January 1, 2026 vintage), public domain, retrieved 2026-10-19T21:45:57Z. The local geocoder does not hold the state relation, and a public-domain official source matches how the Denver boundary was obtained. Service boundary `colorado-service-v1`: 269,604.5 km², 7,519 vertices, kept at full resolution.
- **Envelope:** `colorado-envelope-v1-20km`, a metric 20 km buffer (EPSG:26913) simplified to 25 m and clipped to the routing graph's tileset extent, built in PostGIS: 311,081 km², 190 vertices; it contains the service boundary and reaches into neighbouring states so that records just across the line are assessed.
- **Camera inventory first via Overpass, statewide:** one fixed query over the envelope's bounding box every 6 hours while the stack runs, with the same policy behaviour as before (identifying User-Agent, one request at a time, pause after a rate limit, bounded retries, manual cooldown). This is a configuration change only. M10 replaces it with extract-based ingestion.
- **Routing graph and geocoder:** unchanged; both already cover the whole Colorado extract.
- **Basemap:** a statewide Protomaps extract at zoom 15 (`colorado.pmtiles`, 561 MB, extracted in 44 s); the Denver extract stays in the volume.
- **Configuration:** `configs/regions/colorado.yaml` is the default region; `denver.yaml` remains loadable through `DEFLOCK_REGION_CONFIG` for the pilot area. The plan request's `region_id` is now optional and defaults to the configured region.

## Consequences

- Every wording that named the Denver pilot now comes from the region configuration (display name, boundary attribution, outside-area messages).
- The review fixture set grows from Denver-only trips to statewide cases (Colorado Springs, Boulder, Fort Collins, Pueblo, Grand Junction, the I-70 mountain corridor, Front Range intercity, Denver to Grand Junction) plus out-of-state rejections (Cheyenne, Santa Fe).
- Mapping density outside the Denver area is lower, so counts will often be small and the "unmapped cameras may exist" caveat matters more statewide. Mountain corridors frequently have no alternative road, so "no better route within your limit" will be a common honest answer.
- The M8 audit's statements about the Denver pilot area remain true for the Denver configuration; the Colorado results are recorded in the M9 entry of `docs/DEVELOPMENT_LOG.md`.
