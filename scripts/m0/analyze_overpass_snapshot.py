"""M0 inspection of a raw Overpass ALPR snapshot.

Read-only on the raw file. Produces:
  - a tag summary (markdown + json) for docs/evidence
  - a snapshot manifest for data/manifests
  - a sanitized sample fixture (contributor identity fields stripped)

Usage:
  python -I scripts/m0/analyze_overpass_snapshot.py --raw <raw.json> --query <query.overpassql>
      --downloaded-start <iso> --downloaded-end <iso> --endpoint <url> --label <YYYY-MM-DD>
"""
import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

LIFECYCLE = ("disused", "removed", "was", "abandoned", "planned", "proposed",
             "construction", "demolished")
STRIP_FIELDS = ("user", "uid", "changeset")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def classify_direction(v: str) -> str:
    v = v.strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", v):
        return "numeric_degrees"
    if re.fullmatch(r"-?\d+(\.\d+)?\s*-\s*-?\d+(\.\d+)?", v):
        return "numeric_range"
    if re.fullmatch(r"[NSEWnsew]{1,3}", v):
        return "cardinal"
    if ";" in v:
        return "multi_value"
    if v.lower() in ("forward", "backward", "both", "all", "clockwise", "anticlockwise"):
        return "relative_or_rotational"
    return "other"


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def alpr_type_keys(tags):
    """Keys that end in surveillance:type (plain or lifecycle-prefixed)."""
    return [k for k in tags if k == "surveillance:type" or k.endswith(":surveillance:type")]


def md_table(title, d, limit=None):
    items = list(d.items())[:limit] if limit else list(d.items())
    out = [f"### {title}", "", "| value | count |", "|---|---:|"]
    for k, v in items:
        key = str(k).replace("|", "\\|")
        out.append(f"| `{key}` | {v} |")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--downloaded-start", required=True)
    ap.add_argument("--downloaded-end", required=True)
    ap.add_argument("--endpoint", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--note", default="")
    ap.add_argument("--evidence-dir", default="docs/evidence")
    ap.add_argument("--manifest-dir", default="data/manifests")
    ap.add_argument("--fixture-dir", default="data/fixtures")
    args = ap.parse_args()

    raw_path = Path(args.raw)
    query_path = Path(args.query)
    data = json.loads(raw_path.read_text(encoding="utf-8"))
    elements = data.get("elements", [])
    query_text = query_path.read_text(encoding="utf-8")

    match_reasons = Counter()
    type_counter = Counter(e["type"] for e in elements)
    key_presence = Counter()
    surveillance_type = Counter()
    lifecycle_keys = Counter()
    man_made = Counter()
    surveillance_kind = Counter()
    camera_type = Counter()
    camera_mount = Counter()
    manufacturer_raw = Counter()
    manufacturer_norm = Counter()
    operator = Counter()
    brand = Counter()
    direction_fmt = Counter()
    camera_direction_fmt = Counter()
    both_direction_keys = 0
    both_direction_conflict = 0
    check_date_years = Counter()
    survey_date_years = Counter()
    version_counter = Counter()
    edit_years = Counter()
    class_matrix = Counter()
    timestamps = []
    lats, lons = [], []
    no_tags = 0

    for e in elements:
        tags = e.get("tags") or {}
        if not tags:
            no_tags += 1
        for k in tags:
            key_presence[k] += 1
        tkeys = alpr_type_keys(tags)
        plain_alpr = "alpr" in (tags.get("surveillance:type", "").lower())
        life_alpr_keys = [k for k in tkeys if k != "surveillance:type" and "alpr" in tags[k].lower()]
        man = tags.get("manufacturer", "")
        man_flock = "flock" in man.lower()
        op_flock = "flock" in tags.get("operator", "").lower()
        br_flock = "flock" in tags.get("brand", "").lower()
        ct_alpr = "alpr" in tags.get("camera:type", "").lower()
        if plain_alpr:
            match_reasons["surveillance:type contains ALPR"] += 1
        if life_alpr_keys:
            match_reasons["lifecycle-prefixed surveillance:type contains ALPR"] += 1
        if man_flock:
            match_reasons["manufacturer contains flock"] += 1
        if op_flock:
            match_reasons["operator contains flock"] += 1
        if br_flock:
            match_reasons["brand contains flock"] += 1
        if ct_alpr:
            match_reasons["camera:type contains ALPR"] += 1
        if "surveillance:type" in tags:
            surveillance_type[tags["surveillance:type"]] += 1
        for k in tags:
            pre = k.split(":")[0]
            if pre in LIFECYCLE and k.count(":") >= 1:
                lifecycle_keys[k] += 1
        man_made[tags.get("man_made", "<absent>")] += 1
        surveillance_kind[tags.get("surveillance", "<absent>")] += 1
        camera_type[tags.get("camera:type", "<absent>")] += 1
        camera_mount[tags.get("camera:mount", "<absent>")] += 1
        manufacturer_raw[man if man else "<absent>"] += 1
        manufacturer_norm[(re.sub(r"[^a-z0-9]+", " ", man.lower()).strip() or "<absent>")] += 1
        operator[tags.get("operator", "<absent>")] += 1
        brand[tags.get("brand", "<absent>")] += 1
        d = tags.get("direction")
        cd = tags.get("camera:direction")
        direction_fmt[classify_direction(d) if d is not None else "<absent>"] += 1
        camera_direction_fmt[classify_direction(cd) if cd is not None else "<absent>"] += 1
        if d is not None and cd is not None:
            both_direction_keys += 1
            if d.strip() != cd.strip():
                both_direction_conflict += 1
        if "check_date" in tags:
            check_date_years[tags["check_date"][:4]] += 1
        if "survey:date" in tags:
            survey_date_years[tags["survey:date"][:4]] += 1
        version_counter[e.get("version")] += 1
        ts = e.get("timestamp")
        if ts:
            timestamps.append(ts)
            edit_years[ts[:4]] += 1
        any_alpr = plain_alpr or bool(life_alpr_keys)
        class_matrix[(
            "ALPR-typed" if any_alpr else "not ALPR-typed",
            "manufacturer=flock" if man_flock else ("manufacturer=other" if man else "manufacturer absent"),
        )] += 1
        if "lat" in e:
            lats.append(e["lat"])
            lons.append(e["lon"])

    pts = [(e["id"], e["lat"], e["lon"]) for e in elements if e["type"] == "node"]
    within = {3: 0, 10: 0, 25: 0}
    pairs_10 = []
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            if abs(pts[i][1] - pts[j][1]) > 0.0005 or abs(pts[i][2] - pts[j][2]) > 0.0007:
                continue
            dist = haversine_m(pts[i][1], pts[i][2], pts[j][1], pts[j][2])
            for r in within:
                if dist <= r:
                    within[r] += 1
            if dist <= 10:
                pairs_10.append((pts[i][0], pts[j][0], round(dist, 1)))

    timestamps.sort()

    summary = {
        "label": args.label,
        "element_count": len(elements),
        "element_types": dict(type_counter),
        "elements_without_tags": no_tags,
        "match_reasons": dict(match_reasons),
        "classification_matrix": {f"{a} / {b}": n for (a, b), n in class_matrix.items()},
        "surveillance_type_values": dict(surveillance_type.most_common()),
        "lifecycle_prefixed_keys": dict(lifecycle_keys.most_common()),
        "man_made_values": dict(man_made.most_common()),
        "surveillance_values": dict(surveillance_kind.most_common()),
        "camera_type_values": dict(camera_type.most_common()),
        "camera_mount_values": dict(camera_mount.most_common()),
        "manufacturer_raw_top": dict(manufacturer_raw.most_common(25)),
        "manufacturer_normalized": dict(manufacturer_norm.most_common()),
        "operator_top": dict(operator.most_common(20)),
        "brand_values": dict(brand.most_common()),
        "direction_formats": dict(direction_fmt.most_common()),
        "camera_direction_formats": dict(camera_direction_fmt.most_common()),
        "elements_with_both_direction_and_camera_direction": both_direction_keys,
        "elements_where_direction_differs_from_camera_direction": both_direction_conflict,
        "check_date_years": dict(sorted(check_date_years.items())),
        "survey_date_years": dict(sorted(survey_date_years.items())),
        "source_edit_years": dict(sorted(edit_years.items())),
        "source_edit_timestamp_min": timestamps[0] if timestamps else None,
        "source_edit_timestamp_max": timestamps[-1] if timestamps else None,
        "version_distribution": {str(k): v for k, v in sorted(version_counter.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))},
        "key_presence_top": dict(key_presence.most_common(40)),
        "record_bbox": {"south": min(lats), "west": min(lons), "north": max(lats), "east": max(lons)} if lats else None,
        "co_located_pairs_within_m": {str(k): v for k, v in within.items()},
        "co_located_pairs_within_10m_sample": pairs_10[:15],
    }

    evidence_dir = Path(args.evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / f"overpass_alpr_tag_summary_{args.label}.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")

    md = [
        f"# Overpass ALPR snapshot tag summary ({args.label})",
        "",
        "Generated by `scripts/m0/analyze_overpass_snapshot.py` from the raw snapshot listed in the manifest.",
        "Counts describe mapped OpenStreetMap records inside the query bounding box, not physical devices,",
        "and not a complete inventory. Contributor identity fields are not reported.",
        "",
        f"- Elements: **{len(elements)}** ({dict(type_counter)}); without tags: {no_tags}",
        f"- Source edit timestamps: {summary['source_edit_timestamp_min']} to {summary['source_edit_timestamp_max']}",
        f"- Record bounding box: {summary['record_bbox']}",
        f"- Elements with both `direction` and `camera:direction`: {both_direction_keys}; differing values: {both_direction_conflict}",
        f"- Co-located pairs within 3 m / 10 m / 25 m: {within[3]} / {within[10]} / {within[25]}",
        "",
        md_table("Why each element matched the query (an element can match several clauses)", summary["match_reasons"]),
        md_table("ALPR typing vs manufacturer", summary["classification_matrix"]),
        md_table("surveillance:type values", summary["surveillance_type_values"]),
        md_table("Lifecycle-prefixed keys present", summary["lifecycle_prefixed_keys"]),
        md_table("man_made", summary["man_made_values"]),
        md_table("surveillance", summary["surveillance_values"]),
        md_table("camera:type", summary["camera_type_values"]),
        md_table("camera:mount", summary["camera_mount_values"]),
        md_table("manufacturer (normalized)", summary["manufacturer_normalized"]),
        md_table("manufacturer (raw, top 25)", summary["manufacturer_raw_top"]),
        md_table("operator (top 20)", summary["operator_top"]),
        md_table("brand", summary["brand_values"]),
        md_table("direction value formats", summary["direction_formats"]),
        md_table("camera:direction value formats", summary["camera_direction_formats"]),
        md_table("check_date by year", summary["check_date_years"]),
        md_table("survey:date by year", summary["survey_date_years"]),
        md_table("source edit year (last edit of the element)", summary["source_edit_years"]),
        md_table("element version", summary["version_distribution"]),
        md_table("key presence (top 40)", summary["key_presence_top"]),
    ]
    (evidence_dir / f"overpass_alpr_tag_summary_{args.label}.md").write_text("\n".join(md), encoding="utf-8")

    manifest = {
        "snapshot_id": f"overpass-alpr-denver-envelope-{args.label}",
        "source": "OpenStreetMap via Overpass API",
        "endpoint": args.endpoint,
        "query_file": str(query_path).replace("\\", "/"),
        "query_sha256": hashlib.sha256(query_text.encode("utf-8")).hexdigest(),
        "query_bbox_south_west_north_east": re.search(r"\[bbox:([^\]]+)\]", query_text).group(1),
        "generator": data.get("generator"),
        "timestamp_osm_base": (data.get("osm3s") or {}).get("timestamp_osm_base"),
        "downloaded_at_start": args.downloaded_start,
        "downloaded_at_end": args.downloaded_end,
        "raw_file": str(raw_path).replace("\\", "/"),
        "raw_sha256": sha256_file(raw_path),
        "raw_bytes": raw_path.stat().st_size,
        "element_count": len(elements),
        "remark": data.get("remark"),
        "license": "ODbL 1.0 (OpenStreetMap contributors)",
        "copyright_statement_from_response": (data.get("osm3s") or {}).get("copyright"),
        "parser_version": "m0-inspection-0.1",
        "note": args.note,
    }
    manifest_dir = Path(args.manifest_dir)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / f"overpass_snapshot_{args.label}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def sanitized(e):
        return {k: v for k, v in e.items() if k not in STRIP_FIELDS}

    buckets = defaultdict(list)
    for e in elements:
        tags = e.get("tags") or {}
        man = tags.get("manufacturer", "").lower()
        tkeys = alpr_type_keys(tags)
        life = [k for k in tkeys if k != "surveillance:type"]
        if life:
            buckets["lifecycle"].append(e)
        elif "flock" in man and "camera:direction" in tags:
            buckets["flock_camera_direction"].append(e)
        elif "flock" in man and "direction" in tags:
            buckets["flock_direction"].append(e)
        elif "flock" in man:
            buckets["flock_no_direction"].append(e)
        elif man:
            buckets["other_manufacturer"].append(e)
        else:
            buckets["manufacturer_absent"].append(e)
        if "direction" in tags and classify_direction(tags["direction"]) in ("multi_value", "numeric_range", "other"):
            buckets["unusual_direction"].append(e)
        if "direction" in tags and "camera:direction" in tags and tags["direction"] != tags["camera:direction"]:
            buckets["direction_conflict"].append(e)
    sample, seen = [], set()
    for name in ("flock_camera_direction", "flock_direction", "flock_no_direction", "other_manufacturer",
                 "manufacturer_absent", "lifecycle", "unusual_direction", "direction_conflict"):
        for e in sorted(buckets[name], key=lambda x: x["id"])[:4]:
            if e["id"] not in seen:
                seen.add(e["id"])
                s = sanitized(e)
                s["_fixture_bucket"] = name
                sample.append(s)
    fixture = {
        "fixture_note": "Sanitized sample of real OpenStreetMap records (ODbL) selected for parser coverage. "
                        "Contributor user/uid/changeset fields removed. Not a complete inventory. "
                        "Coordinates are as mapped, not field-verified by this project.",
        "snapshot_id": manifest["snapshot_id"],
        "timestamp_osm_base": manifest["timestamp_osm_base"],
        "bucket_sizes": {k: len(v) for k, v in buckets.items()},
        "elements": sample,
    }
    fixture_dir = Path(args.fixture_dir)
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / f"overpass_alpr_sample_{args.label}.json").write_text(json.dumps(fixture, indent=2), encoding="utf-8")

    keys = ("element_count", "match_reasons", "classification_matrix", "surveillance_type_values",
            "lifecycle_prefixed_keys", "manufacturer_normalized", "direction_formats", "camera_direction_formats",
            "elements_with_both_direction_and_camera_direction",
            "elements_where_direction_differs_from_camera_direction",
            "check_date_years", "source_edit_years", "co_located_pairs_within_m", "record_bbox")
    print(json.dumps({k: summary[k] for k in keys}, indent=1))
    print("operator_top:", json.dumps(summary["operator_top"], indent=1))
    print("camera_mount:", summary["camera_mount_values"])
    print("surveillance:", summary["surveillance_values"])
    print("man_made:", summary["man_made_values"])
    print("camera_type:", summary["camera_type_values"])
    print("fixture buckets:", fixture["bucket_sizes"], "sample size:", len(sample))


if __name__ == "__main__":
    main()
