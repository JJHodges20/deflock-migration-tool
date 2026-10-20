# Decision 0004: camera inventory from the Geofabrik extract with daily change files (M10, 2026-10-19)

- **Status:** implemented in M10 for the Colorado configuration; approved in principle by the owner on 2026-10-19 (decision 0003, item 3).
- **Related:** `docs/DATA_SOURCE_REGISTER.md` sections 1 and 2, `configs/regions/colorado.yaml`, `configs/providers.yaml`, `backend/src/deflockmigration/data_sources/osm_extract.py`, `backend/src/deflockmigration/ingestion/extract_elements.py`.

## Problem

Since M2 the camera inventory came from one bounded query to the public Overpass instance every 6 hours. That instance is shared infrastructure that discourages application backends, and the statewide query of M9 was heavy enough to be answered with HTTP 502/504 on its first attempt. The roadmap already named the way out: process regional extracts and their change files instead.

## Decision

1. **Source.** The Colorado configuration's camera source is the Geofabrik Colorado extract (`colorado-latest.osm.pbf`) kept current with the publisher's daily change files (`colorado-updates`, one `.osc.gz` per day, kept for about 100 days). The same tag filters as the Overpass query are applied to the whole extract with pyosmium; the output has the shape of Overpass elements, so the normalizer, the diff, the quality checks, the quarantine and promotion rules, and the review tools are unchanged.
2. **No second full download.** The sync worker seeds its own copy from the routing graph's extract, which the setup already downloads (a 1 s copy on the pilot machine), and then applies change files. A full extract download happens only when no seed exists or the change files the local file needs are no longer published; at most one per run, checksum verified.
3. **Cadence and politeness.** The worker checks once per `refresh_interval_hours` (24 h for Colorado: the publisher issues one change file per day); each check is one small state request plus the change files that are new. The client identifies the application, makes one request at a time, pauses 30 s after a rate-limit answer, retries a bounded number of times, and never rotates endpoints. Timeouts, pauses, attempts, and the full-download rule are the `camera_extract` block of `configs/providers.yaml` and are disclosed in Data Health.
4. **Coverage.** The extract is cut along the publisher's outline, which follows the state line within about 300 m, so records in neighbouring states are not in the inventory. The camera-data envelope therefore changes from v1 (20 km beyond the state line) to **v2** (`colorado-envelope-v2-extract`: v1 limited to the outline with a 500 m metric margin, 271,739.7 km², 61 vertices, containing the service boundary). A route that leaves the state is assessed only for the part inside the envelope and is not ranked for privacy, as before for routes leaving the envelope.
5. **Privacy.** Raw snapshots from the extract carry no contributor names or ids (the Overpass raw responses did). Snapshot ids start with `ext-` instead of `ovp-`.
6. **The Overpass adapter stays.** The Denver pilot configuration keeps `overpass_bounded`, and the Colorado query file stays on disk as a documented fallback (set `adapter: overpass_bounded` with the endpoint and query file again).

## Evidence (pilot machine, 2026-10-19)

- The extract in the volume carries the Osmosis replication headers (`colorado-updates`, sequence 4945, 2026-10-18T20:25:06Z).
- One key-filtered pass over the 385 MB extract: 4.4 s, 82,781 objects carrying a filter key reach Python, 2,875 nodes and 1 way match; the node-location pass 0.8 s; 192 MB resident.
- Applying three daily change files and rewriting the file with pyosmium: 13 s, 309 MB resident; a second 385 MB file exists for a moment. The worker's memory limit is raised to 1 GB.
- The outline (`colorado.poly`, 15 vertices) contains the service boundary except 0.8 km² of slivers; 40,624 km² of envelope v1 lay outside it.

## Consequences

- The planner depends on no shared public endpoint for its camera data; the only recurring external traffic is one small state request per day plus the day's change file.
- Camera counts near the state line can drop slightly compared with the M9 snapshot: records across the line were in the Overpass box but are not in the extract. The first extract snapshot carries them as "no longer mapped" for the retention period; they age out afterwards.
- Disk: one more copy of the extract (385 MB) in the `camera_extracts` volume.
- A new dependency in the backend image: pyosmium 4.3.2 (BSD-2) with `requests`, and the `libexpat1` system library.
