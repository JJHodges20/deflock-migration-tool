# Data dictionary (camera inventory, M2)

All tables hold public OpenStreetMap-derived data (ODbL) and this project's own bookkeeping. No table stores a trip, an address query, or a person's location. Counts always describe mapped records, never physical devices.

## `camera_snapshots` - one row per fetched source result

| Column | Meaning |
|---|---|
| `snapshot_id` | `ovp-<region>-<timestamp_osm_base>-<sha8>`; stable identity of one fetch |
| `region_id`, `source`, `endpoint`, `query_sha256`, `query_bbox` | which fixed query produced the snapshot |
| `generator`, `timestamp_osm_base` | the Overpass build and the OSM data timestamp reported upstream (source "as of") |
| `downloaded_at_start/_end` | when this project fetched it (not an inspection date) |
| `element_count`, `record_count` | raw elements returned; normalized records stored (includes carried no-longer-mapped rows) |
| `alpr_count`, `flock_count`, `unknown_manufacturer_count` | ALPR-typed records present in the source; of those, manufacturer Flock Safety; manufacturer absent |
| `in_envelope_alpr_count` | ALPR records inside the camera-data envelope (the only ones assessed against routes) |
| `no_longer_mapped_count` | records carried from the previous snapshot because they vanished from the source (retained as uncertain) |
| `raw_sha256`, `raw_bytes`, `raw_path` | provenance of the raw payload kept in the `camera_snapshots` volume |
| `parser_version`, `license` | normalizer version; data license |
| `quality` | validation report (`quarantine_reason` when applicable, drop fraction versus the active snapshot) |
| `promotion_state` | `staged` → `active` → `superseded`; or `quarantined` → (`active` on accept / `rejected` on reject) |
| `previous_active_snapshot_id`, `promoted_at` | promotion lineage |
| `review_note`, `reviewed_at` | operator decision text for quarantined snapshots |

## `camera_records` - one row per source record per snapshot

| Column | Meaning |
|---|---|
| `source_key` | `osm:<node|way|relation>:<id>`; node and way ids never collide |
| `source_type`, `source_id`, `source_version`, `source_timestamp` | OSM identity, element version, and last edit time (not a field check) |
| `geom` | `geography(Point, 4326)`; meters in PostGIS, never degrees |
| `geometry_quality` | `point`, or `representative_point` for non-point elements |
| `raw_tags` | the element's tags verbatim (never rendered as HTML) |
| `is_alpr`, `alpr_evidence` | ALPR typing per decision 0001 D8 and the tag that proves it |
| `manufacturer_raw`, `manufacturer_normalized`, `is_flock` | manufacturer as mapped, normalized key, Flock scope (manufacturer only; brand/operator are evidence) |
| `operator` | operator tag as mapped |
| `direction_raw`, `camera_direction_raw`, `direction_parsed_deg`, `direction_conflict` | mapped orientation (stored, never used to exclude a camera in v1) |
| `lifecycle_state`, `lifecycle_evidence` | `mapped`, `removed`, `was`, `destroyed`, `disused`, `planned` from lifecycle prefixes; `no_longer_mapped` when absent from a later successful query |
| `check_date` | `check_date` or `survey:date` tag when mapped (rare) |
| `parse_warnings` | normalizer notes (conflicts, multi-valued directions, carried-over status) |
| `in_envelope` | inside the camera-data envelope |
| `missing_since`, `last_seen_snapshot_id` | for `no_longer_mapped` rows: first absence time and the last snapshot that contained the record |

A record stays `no_longer_mapped` for `data_quality.snapshot_validation.retain_missing_hours` (72 h by default) and is then dropped. "No longer mapped" is not "removed": physical removal is only recorded when contributors add a lifecycle prefix.

## `snapshot_diffs` - what changed versus the previous active snapshot

| Column | Meaning |
|---|---|
| `added_count`, `changed_count`, `missing_count`, `reappeared_count`, `carried_count`, `expired_count` | exact counts: newly mapped keys; same key with a new version; present before, absent now; previously missing, present again; missing keys carried as uncertain; carried keys dropped after retention |
| `added_keys`, `changed`, `missing_keys` | key lists bounded by `retention.max_diff_keys_stored` |

## `camera_road_associations` - cached nearest-road candidates per record and graph version (M4)

| Column | Meaning |
|---|---|
| `source_key`, `graph_version`, `radius_m` | unique key; `graph_version` is `<routing graph id>@<tileset build time>` so associations never outlive a graph |
| `method` | `valhalla_locate_nearest_way` |
| `computed_at` | when the engine was asked |
| `nearest_way_id`, `nearest_road_names`, `nearest_distance_m` | the record's most plausible road (nearest drivable way within the radius) |
| `candidate_count`, `ambiguous` | how many ways lie within the radius; whether a different road (by name set, or way id when unnamed) is within 10 m of being as close; informational, the assessment recomputes the verdict from `candidates` |
| `candidates` | one entry per way: id, names, distance, road class, use, bridge, tunnel, correlated point, side of street |

Associations are explanations, not truths: the route assessment reports why a record was or was not counted (`docs/ROUTING_METHOD.md`).

## `sync_jobs` - every refresh attempt and review action

| Column | Meaning |
|---|---|
| `trigger` | `scheduled`, `manual`, `setup`, `review`, or `rollback` |
| `status` | `running`, `succeeded`, `failed`, `quarantined`, `skipped` |
| `http_status`, `attempts` | upstream response and retries (502/429 are routine) |
| `added_count`, `changed_count`, `no_longer_present_count` | diff summary for the fetched snapshot |
| `message` | sanitized outcome; never payload content |

M7 additions: `status = skipped` records a manual refresh refused by the shared cooldown (with the active snapshot id and the reason); `trigger = rollback` records an operator restoring a previously active snapshot (the message names both snapshot ids and the note).

## Retention

After each successful sync the service keeps the newest `keep_superseded_snapshots` superseded snapshots and `keep_quarantined_snapshots` quarantined or rejected ones; older snapshots, their records, their diffs, and their raw files are deleted. Record history (`GET /api/v1/cameras/record?source_key=...`) spans the retained snapshots.
