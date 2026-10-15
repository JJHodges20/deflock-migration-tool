"""M0 boundary review for the Denver pilot.

Inputs (read-only):
  - official City and County of Denver "County Boundary" GeoJSON (EPSG:4326 export)
  - Geofabrik colorado.poly (routing-graph extract outline)
  - raw Overpass ALPR snapshot (for zone counts)

Outputs:
  - data/boundaries/denver_service_boundary_v1.geojson
  - data/boundaries/denver_camera_envelope_v1.geojson (20 km buffer)
  - docs/evidence/boundary_analysis_<label>.json / .md

Run with the scratch geometry venv (shapely + pyproj); never part of the app runtime.
"""
import argparse
import json
from pathlib import Path

import pyproj
from shapely.geometry import MultiPolygon, Point, Polygon, box, mapping, shape
from shapely.ops import transform, unary_union

WGS84 = pyproj.CRS.from_epsg(4326)
UTM13N = pyproj.CRS.from_epsg(26913)
TO_UTM = pyproj.Transformer.from_crs(WGS84, UTM13N, always_xy=True).transform
TO_WGS = pyproj.Transformer.from_crs(UTM13N, WGS84, always_xy=True).transform

# Public landmarks only (approximate coordinates typed from general knowledge; not personal addresses).
PROBE_POINTS = [
    ("Denver Union Station", 39.7530, -105.0002, "inside"),
    ("Colorado State Capitol", 39.7393, -104.9848, "inside"),
    ("Denver Zoo", 39.7503, -104.9500, "inside"),
    ("DEN Jeppesen Terminal (airport arm)", 39.8494, -104.6737, "inside"),
    ("Glendale city centre (enclave)", 39.7047, -104.9339, "outside"),
    ("Holly Hills (enclave)", 39.6686, -104.9178, "outside"),
    ("Aurora city centre", 39.7294, -104.8319, "outside"),
    ("Lakewood Belmar", 39.7047, -105.0814, "outside"),
    ("Englewood civic centre", 39.6478, -104.9878, "outside"),
    ("Red Rocks Amphitheatre", 39.6654, -105.2057, "outside"),
]


def read_poly(path: Path):
    """Parse an Osmosis .poly file into a (Multi)Polygon."""
    rings, current = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        if s == "END":
            if current:
                rings.append(current)
            current = None
            continue
        parts = s.split()
        if len(parts) == 2:
            try:
                current.append((float(parts[0]), float(parts[1])))
            except (ValueError, AttributeError):
                pass
        elif current is None and not s.startswith("!"):
            current = []
    polys = [Polygon(r) for r in rings if len(r) >= 4]
    return unary_union(polys)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boundary", required=True)
    ap.add_argument("--poly", required=True)
    ap.add_argument("--overpass", required=True)
    ap.add_argument("--query-bbox", required=True, help="south,west,north,east")
    ap.add_argument("--label", required=True)
    ap.add_argument("--retrieved-at", required=True)
    ap.add_argument("--out-dir", default="data/boundaries")
    ap.add_argument("--evidence-dir", default="docs/evidence")
    args = ap.parse_args()

    gj = json.loads(Path(args.boundary).read_text(encoding="utf-8"))
    feats = gj["features"]
    by_county = {}
    for f in feats:
        by_county.setdefault(f["properties"].get("COUNTY"), []).append(f)

    denver_parts = [shape(f["geometry"]) for f in by_county.get("Denver", [])]
    service = unary_union(denver_parts)
    if not service.is_valid:
        service = service.buffer(0)
    service_utm = transform(TO_UTM, service)
    polys = list(service.geoms) if isinstance(service, MultiPolygon) else [service]

    part_report = []
    for p in polys:
        pu = transform(TO_UTM, p)
        part_report.append({
            "exterior_vertices": len(p.exterior.coords),
            "interior_rings": len(p.interiors),
            "area_km2": round(pu.area / 1e6, 2),
            "bbox": [round(v, 5) for v in p.bounds],
        })

    enclaves = []
    for county, fs in by_county.items():
        if county == "Denver":
            continue
        for f in fs:
            g = shape(f["geometry"])
            gu = transform(TO_UTM, g)
            overlap = gu.intersection(service_utm).area
            enclaves.append({
                "objectid": f["properties"].get("OBJECTID"),
                "county": county,
                "area_km2": round(gu.area / 1e6, 3),
                "overlap_with_service_km2": round(overlap / 1e6, 4),
                "surrounded_by_service_boundary": bool(service_utm.buffer(5).contains(gu.exterior) if gu.geom_type == "Polygon" else False),
            })

    probes = []
    for name, lat, lon, expected in PROBE_POINTS:
        inside = service.contains(Point(lon, lat))
        probes.append({"name": name, "lat": lat, "lon": lon, "expected": expected,
                       "actual": "inside" if inside else "outside",
                       "agrees": (inside and expected == "inside") or (not inside and expected == "outside")})

    envelopes = {}
    for km in (10, 15, 20):
        env_utm = service_utm.buffer(km * 1000)
        env = transform(TO_WGS, env_utm.simplify(25))
        envelopes[km] = {"geom": env, "utm": env_utm, "area_km2": round(env_utm.area / 1e6, 1),
                         "bbox": [round(v, 5) for v in env.bounds]}

    s, w, n, e = [float(x) for x in args.query_bbox.split(",")]
    query_box = box(w, s, e, n)

    colorado = read_poly(Path(args.poly))
    colorado_utm = transform(TO_UTM, colorado)

    snap = json.loads(Path(args.overpass).read_text(encoding="utf-8"))
    nodes = [el for el in snap["elements"] if el["type"] == "node"]
    counts = {}
    for km, env in envelopes.items():
        c = {"total": 0, "flock": 0, "non_flock_or_unknown": 0}
        for el in nodes:
            if env["geom"].contains(Point(el["lon"], el["lat"])):
                c["total"] += 1
                man = (el.get("tags") or {}).get("manufacturer", "").lower()
                c["flock" if "flock" in man else "non_flock_or_unknown"] += 1
        counts[f"envelope_{km}km"] = c
    in_service = {"total": 0, "flock": 0, "non_flock_or_unknown": 0}
    outside_env20 = 0
    for el in nodes:
        pt = Point(el["lon"], el["lat"])
        if service.contains(pt):
            in_service["total"] += 1
            man = (el.get("tags") or {}).get("manufacturer", "").lower()
            in_service["flock" if "flock" in man else "non_flock_or_unknown"] += 1
        if not envelopes[20]["geom"].contains(pt):
            outside_env20 += 1
    counts["service_boundary"] = in_service
    counts["in_query_bbox_but_outside_envelope_20km"] = outside_env20

    env20 = envelopes[20]
    report = {
        "label": args.label,
        "source_boundary_file": args.boundary.replace("\\", "/"),
        "retrieved_at": args.retrieved_at,
        "feature_counts_by_county": {k: len(v) for k, v in by_county.items()},
        "service_boundary": {
            "geometry_type": service.geom_type,
            "polygon_count": len(polys),
            "parts": part_report,
            "total_area_km2": round(service_utm.area / 1e6, 2),
            "total_area_sq_mi": round(service_utm.area / 2.58999e6, 2),
            "bbox_west_south_east_north": [round(v, 5) for v in service.bounds],
            "is_valid": service.is_valid,
        },
        "enclaves_in_source": enclaves,
        "probe_points": probes,
        "envelopes": {f"{km}km": {"area_km2": v["area_km2"], "bbox_west_south_east_north": v["bbox"]} for km, v in envelopes.items()},
        "camera_record_counts_by_zone": counts,
        "overpass_query_bbox_contains_envelope_20km": bool(query_box.contains(env20["geom"])),
        "colorado_extract_contains_envelope_20km": bool(colorado.contains(env20["geom"])),
        "min_distance_envelope_20km_to_colorado_edge_km": round(env20["utm"].exterior.distance(colorado_utm.boundary) / 1000, 1),
        "notes": [
            "Areas computed in EPSG:26913 (UTM zone 13N). Buffers are metric, never degree-based.",
            "Service boundary = union of the source polygons with COUNTY='Denver'; enclave rings are preserved as holes.",
            "The envelope defines where a snapshot was assessed; it is not a claim of camera coverage.",
        ],
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    service_fc = {
        "type": "FeatureCollection",
        "name": "denver_service_boundary_v1",
        "features": [{
            "type": "Feature",
            "properties": {
                "boundary_id": "denver-service-v1",
                "role": "service_boundary",
                "source": "City and County of Denver Open Data Catalog, 'County Boundary' (ODC_ENG_SRVCCDBOUNDARY_A, layer 40), features with COUNTY='Denver'",
                "source_item_id": "53a0ae35c018471788efe36b6f730a79",
                "source_crs_original": "EPSG:2877",
                "export_crs": "EPSG:4326",
                "retrieved_at": args.retrieved_at,
                "source_terms": "Custom City and County of Denver use constraints (provided as is, without warranty, not for engineering purposes). Not ODbL.",
                "area_km2": report["service_boundary"]["total_area_km2"],
                "enclaves_handled_as": "holes (interior rings) kept from the source geometry",
            },
            "geometry": mapping(service),
        }],
    }
    (out_dir / "denver_service_boundary_v1.geojson").write_text(json.dumps(service_fc), encoding="utf-8")
    env_fc = {
        "type": "FeatureCollection",
        "name": "denver_camera_envelope_v1",
        "features": [{
            "type": "Feature",
            "properties": {
                "envelope_id": "denver-envelope-v1-20km",
                "role": "camera_data_envelope",
                "based_on": "denver-service-v1",
                "buffer_m": 20000,
                "method": "shapely buffer in EPSG:26913, simplified with 25 m tolerance, reprojected to EPSG:4326",
                "area_km2": env20["area_km2"],
                "bbox_west_south_east_north": env20["bbox"],
                "meaning": "Area within which camera records of a snapshot are assessed. Not a claim of complete physical camera coverage.",
            },
            "geometry": mapping(env20["geom"]),
        }],
    }
    (out_dir / "denver_camera_envelope_v1.geojson").write_text(json.dumps(env_fc), encoding="utf-8")

    ev = Path(args.evidence_dir)
    ev.mkdir(parents=True, exist_ok=True)
    (ev / f"boundary_analysis_{args.label}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    md = [f"# Denver boundary analysis ({args.label})", "",
          "Generated by `scripts/m0/analyze_boundary.py`. Source: City and County of Denver 'County Boundary' layer (EPSG:4326 export) retrieved " + args.retrieved_at + ".", "",
          f"- Source features by county: {report['feature_counts_by_county']}",
          f"- Service boundary: {service.geom_type}, {len(polys)} polygon(s), area {report['service_boundary']['total_area_km2']} km² ({report['service_boundary']['total_area_sq_mi']} sq mi), valid={service.is_valid}",
          f"- Service bbox (W,S,E,N): {report['service_boundary']['bbox_west_south_east_north']}",
          "", "## Parts", "", "| exterior vertices | interior rings | area km² | bbox |", "|---:|---:|---:|---|"]
    for p in part_report:
        md.append(f"| {p['exterior_vertices']} | {p['interior_rings']} | {p['area_km2']} | {p['bbox']} |")
    md += ["", "## Enclaves present in the source layer", "", "| objectid | county | area km² | overlap with service km² | surrounded |", "|---:|---|---:|---:|---|"]
    for enc in enclaves:
        md.append(f"| {enc['objectid']} | {enc['county']} | {enc['area_km2']} | {enc['overlap_with_service_km2']} | {enc['surrounded_by_service_boundary']} |")
    md += ["", "## Probe points (public landmarks, approximate coordinates)", "", "| landmark | expected | actual | agrees |", "|---|---|---|---|"]
    for pr in probes:
        md.append(f"| {pr['name']} | {pr['expected']} | {pr['actual']} | {pr['agrees']} |")
    md += ["", "## Envelope options (metric buffer of the service boundary)", "", "| buffer | area km² | bbox (W,S,E,N) | mapped records in zone (total / flock / other-or-unknown) |", "|---|---:|---|---|"]
    for km in (10, 15, 20):
        c = counts[f"envelope_{km}km"]
        md.append(f"| {km} km | {envelopes[km]['area_km2']} | {envelopes[km]['bbox']} | {c['total']} / {c['flock']} / {c['non_flock_or_unknown']} |")
    sc = counts["service_boundary"]
    md += ["", f"- Records inside the service boundary itself: {sc['total']} (flock {sc['flock']}, other/unknown {sc['non_flock_or_unknown']})",
           f"- Records inside the query bbox but outside the 20 km envelope: {outside_env20}",
           f"- Overpass query bbox contains the 20 km envelope: {report['overpass_query_bbox_contains_envelope_20km']}",
           f"- Geofabrik Colorado extract outline contains the 20 km envelope: {report['colorado_extract_contains_envelope_20km']} (minimum distance from envelope edge to extract edge: {report['min_distance_envelope_20km_to_colorado_edge_km']} km)",
           "", "Counts describe mapped OpenStreetMap records in a snapshot, not physical devices or coverage."]
    (ev / f"boundary_analysis_{args.label}.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("enclaves_in_source",)}, indent=1))
    print("enclaves:", json.dumps(enclaves))


if __name__ == "__main__":
    main()
