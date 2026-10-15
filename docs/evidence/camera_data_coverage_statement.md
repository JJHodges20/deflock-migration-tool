# Camera-data coverage statement (snapshot of 2026-10-15)

This statement describes what the Milestone 0 camera-data snapshot covers. It is a statement about mapped records, not about physical cameras.

## What was assessed

- **Source:** OpenStreetMap records fetched through one bounded Overpass query (`overpass-alpr-denver-envelope-2026-10-15`, data as of 2026-10-15T20:18:00Z).
- **Query area:** bounding box 39.40 N to 40.12 N, 105.40 W to 104.35 W, which fully contains the proposed 20 km camera-data envelope around the City and County of Denver.
- **Records found:** 1,591 nodes. 1,538 carry `surveillance:type=ALPR`; the remaining 53 matched only through Flock branding and include 37 generic cameras and 14 gunshot detectors that must not be counted as ALPRs.

| Zone | Mapped records | of which manufacturer Flock Safety |
|---|---:|---:|
| Service boundary (City and County of Denver, 400 km²) | 196 | 119 |
| 10 km envelope | 968 | 770 |
| 15 km envelope | 1,181 | 962 |
| 20 km envelope (proposed) | 1,325 | 1,078 |
| Inside query box but outside the 20 km envelope | 266 | - |

## What this does not mean

- It does not mean that 1,325 cameras exist, operate, or are correctly placed. It means that 1,325 records were mapped by OpenStreetMap contributors and matched the query on that date.
- It does not mean that the area holds no other cameras. Unmapped, mislocated, or newly installed devices are not detectable from this source.
- Only 4 of the 1,591 records carry a `check_date`; the source edit timestamp of a record is the last time anyone edited it, not an inspection date. The oldest last-edit in the snapshot is from 2024 (96 records), 703 were last edited in 2025, and 792 in 2026.
- 178 records have no manufacturer tag. They stay in the "All mapped ALPRs" scope and are never labelled Flock.
- 98 pairs of records lie within 10 m of each other (multi-camera poles or duplicates). They are kept as separate records and may be grouped for display only.
- Direction tags describe where contributors believe a device points. They are not evidence of which traffic direction is recorded, and 5 of the 7 records that carry both `direction` and `camera:direction` disagree.

## How the product must phrase it

- Zero encounters: "No mapped encounters detected by this assessment. Unmapped or mislocated cameras may still be present."
- Coverage: only "portion of route inside our assessed data area" (a geometric statement about the envelope), never a percentage of physical cameras.
- Freshness: show the snapshot's `timestamp_osm_base` and download time separately from any `check_date`.
