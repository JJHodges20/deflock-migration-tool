"""Follow-up probes for the M0 routing spike.

P1  Why is the default reference slower than its alternates? Compare costing options and
    hierarchy pruning on the same trip (requires service_limits.max_distance_disable_hierarchy_culling > 0).
P2  Local detour on surface streets: exclude one point on a surface-street route and measure the change.
P3  Legality evidence: map-match the avoidance route with edge_walk and read per-edge traversability.

Usage: python -I spikes/valhalla/route_spike_extra.py --label 2026-10-15
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from route_spike import (LANDMARKS, Client, cumulative_point, decode_polyline6, encode_polyline6,  # noqa: E402
                         loc, min_dist_to_shape_m, shape_overlap_fraction, summarize_trip)


def post_json(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def brief(s):
    return {"time_s": s["time_s"], "length_km": s["length_km"], "has_highway": s["has_highway"], "maneuvers": s["maneuver_count"]} if s else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8002")
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    out_dir, results_dir = Path("spikes/valhalla/output"), Path("spikes/valhalla/results")
    c = Client(args.base, out_dir)
    res = {"label": args.label, "p1_reference_quality": {}, "p2_local_detour": {}, "p3_legality": {}}
    geo = []

    A, B = LANDMARKS["union_station"], LANDMARKS["denver_zoo"]
    trips = {
        "union_to_zoo": (A, B),
        "zoo_to_union": (B, A),
        "capitol_to_zoo": (LANDMARKS["state_capitol"], B),
        "union_to_washington_park": (A, LANDMARKS["washington_park"]),
    }
    variants = {
        "default": {},
        "disable_hierarchy_pruning": {"costing_options": {"auto": {"disable_hierarchy_pruning": True}}},
        "use_highways_0.3": {"costing_options": {"auto": {"use_highways": 0.3}}},
        "use_highways_0.0": {"costing_options": {"auto": {"use_highways": 0.0}}},
        "shortest": {"costing_options": {"auto": {"shortest": True}}},
    }
    for tname, (a, b) in trips.items():
        row = {}
        status, payload, rec = c.route(f"p1_{tname}_alternates", {"locations": [loc(a), loc(b)], "costing": "auto", "units": "kilometers", "alternates": 2})
        main_s = summarize_trip(payload) if status == 200 else None
        alts = [summarize_trip(x) for x in (payload.get("alternates") or [])]
        row["default_with_alternates"] = {"primary": brief(main_s), "alternates": [brief(x) for x in alts if x],
                                          "fastest_is_primary": bool(main_s and all((x["time_s"] >= main_s["time_s"]) for x in alts if x)),
                                          "elapsed_ms": rec["elapsed_ms"]}
        for vname, extra in variants.items():
            status, payload, rec = c.route(f"p1_{tname}_{vname}", {"locations": [loc(a), loc(b)], "costing": "auto", "units": "kilometers", **extra})
            s = summarize_trip(payload) if status == 200 else None
            row[vname] = {**(brief(s) or {"error": payload}), "warnings": (s or {}).get("warnings", payload.get("warnings")), "elapsed_ms": rec["elapsed_ms"]}
        res["p1_reference_quality"][tname] = row

    # P2: surface-street local detour. Reference = union->zoo with use_highways 0.0 if it avoids highways, else the alternates' first.
    status, payload, rec = c.route("p2_surface_reference", {"locations": [loc(A), loc(B)], "costing": "auto", "units": "kilometers", "costing_options": {"auto": {"use_highways": 0.0}}})
    ref = summarize_trip(payload)
    if ref and ref["has_highway"]:
        status, payload, rec = c.route("p2_surface_reference_alt", {"locations": [loc(A), loc(B)], "costing": "auto", "units": "kilometers", "alternates": 2})
        cands = [summarize_trip(payload)] + [summarize_trip(x) for x in payload.get("alternates", [])]
        ref = next((x for x in cands if x and not x["has_highway"]), ref)
    ref_shape = ref["_shape"]
    idx, target, total_m = cumulative_point(ref_shape, 0.55)
    geo.append({"type": "Feature", "properties": {"name": "p2_reference"}, "geometry": {"type": "LineString", "coordinates": [[p[1], p[0]] for p in ref_shape]}})
    geo.append({"type": "Feature", "properties": {"name": "p2_target"}, "geometry": {"type": "Point", "coordinates": [target[1], target[0]]}})
    res["p2_local_detour"]["reference"] = {**brief(ref), "instructions": ref["instructions"], "target": {"lat": target[0], "lon": target[1]}, "length_m": round(total_m)}
    for name, extra in (("exclude_locations", {"exclude_locations": [loc(target)]}),
                        ("linear_factor_10", {"linear_cost_factors": [{"shape": encode_polyline6(ref_shape[max(0, idx - 2):idx + 3]), "factor": 10.0}]})):
        status, payload, rec = c.route(f"p2_{name}", {"locations": [loc(A), loc(B)], "costing": "auto", "units": "kilometers", "costing_options": {"auto": {"use_highways": 0.0}}, **extra})
        s = summarize_trip(payload) if status == 200 else None
        if s:
            geo.append({"type": "Feature", "properties": {"name": f"p2_{name}"}, "geometry": {"type": "LineString", "coordinates": [[p[1], p[0]] for p in s["_shape"]]}})
            res["p2_local_detour"][name] = {**brief(s), "instructions": s["instructions"], "warnings": s["warnings"],
                                            "min_distance_to_target_m": round(min_dist_to_shape_m(target, s["_shape"]), 1),
                                            "overlap_with_reference_fraction": round(shape_overlap_fraction(s["_shape"], ref_shape), 3),
                                            "extra_time_s": round(s["time_s"] - ref["time_s"], 1), "extra_length_km": round(s["length_km"] - ref["length_km"], 3),
                                            "elapsed_ms": rec["elapsed_ms"]}
        else:
            res["p2_local_detour"][name] = {"error": payload}

    # P3: legality evidence via trace_attributes (edge_walk on the engine's own shape).
    for name in ("p2_exclude_locations", "p2_linear_factor_10"):
        resp_file = out_dir / f"{name}.response.json"
        if not resp_file.exists():
            continue
        shape = decode_polyline6(json.loads(resp_file.read_text(encoding="utf-8"))["trip"]["legs"][0]["shape"])
        body = {"shape": [{"lat": p[0], "lon": p[1]} for p in shape], "costing": "auto", "shape_match": "edge_walk",
                "filters": {"attributes": ["edge.names", "edge.traversability", "edge.use", "edge.road_class", "edge.length", "edge.toll", "edge.drive_on_right"], "action": "include"}}
        try:
            ta = post_json(args.base, "/trace_attributes", body)
            edges = ta.get("edges") or []
            trav = {}
            for e in edges:
                trav[e.get("traversability", "<absent>")] = trav.get(e.get("traversability", "<absent>"), 0) + 1
            uses = {}
            for e in edges:
                uses[e.get("use", "<absent>")] = uses.get(e.get("use", "<absent>"), 0) + 1
            res["p3_legality"][name] = {"edge_count": len(edges), "traversability_counts": trav, "use_counts": uses,
                                        "sample_edge_keys": sorted((edges[0] if edges else {}).keys()),
                                        "note": "edge_walk matching of the engine's own route shape; traversability is relative to the matched direction"}
            (out_dir / f"p3_{name}.trace_attributes.json").write_text(json.dumps(ta, indent=1), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            res["p3_legality"][name] = {"error": str(exc)}

    res["calls"] = c.calls
    (results_dir / f"route_spike_extra_{args.label}.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    (results_dir / f"route_spike_extra_{args.label}_routes.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": geo}), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "calls"}, indent=1, default=str))


if __name__ == "__main__":
    main()
