"""M0 routing spike against a local pinned Valhalla service.

Proves, with real responses, which avoidance mechanisms the pinned build supports and
whether they change the path without breaking directions. Uses only public landmarks.

Usage: python -I spikes/valhalla/route_spike.py --base http://127.0.0.1:8002 --label 2026-10-15
Raw responses go to spikes/valhalla/output/ (not committed); summaries to spikes/valhalla/results/.
"""
import argparse
import json
import math
import time
import urllib.error
import urllib.request
from pathlib import Path

LANDMARKS = {
    "union_station": (39.7530, -105.0002),
    "denver_zoo": (39.7503, -104.9500),
    "state_capitol": (39.7393, -104.9848),
    "den_terminal": (39.8494, -104.6737),
    "washington_park": (39.7006, -104.9699),
}
MANEUVER_TYPE_NAMES = {
    0: "kNone", 1: "kStart", 2: "kStartRight", 3: "kStartLeft", 4: "kDestination", 5: "kDestinationRight",
    6: "kDestinationLeft", 7: "kBecomes", 8: "kContinue", 9: "kSlightRight", 10: "kRight", 11: "kSharpRight",
    12: "kUturnRight", 13: "kUturnLeft", 14: "kSharpLeft", 15: "kLeft", 16: "kSlightLeft", 17: "kRampStraight",
    18: "kRampRight", 19: "kRampLeft", 20: "kExitRight", 21: "kExitLeft", 22: "kStayStraight", 23: "kStayRight",
    24: "kStayLeft", 25: "kMerge", 26: "kRoundaboutEnter", 27: "kRoundaboutExit", 28: "kFerryEnter",
    29: "kFerryExit", 30: "kTransit", 31: "kTransitTransfer", 32: "kTransitRemainOn", 33: "kTransitConnectionStart",
    34: "kTransitConnectionTransfer", 35: "kTransitConnectionDestination", 36: "kPostTransitConnectionDestination",
    37: "kMergeRight", 38: "kMergeLeft", 39: "kElevatorEnter", 40: "kStepsEnter", 41: "kEscalatorEnter",
    42: "kBuildingEnter", 43: "kBuildingExit",
}


def decode_polyline6(s, prec=1e6):
    idx, lat, lng, coords = 0, 0, 0, []
    while idx < len(s):
        for which in (0, 1):
            shift = result = 0
            while True:
                b = ord(s[idx]) - 63
                idx += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            d = ~(result >> 1) if result & 1 else (result >> 1)
            if which == 0:
                lat += d
            else:
                lng += d
        coords.append((lat / prec, lng / prec))
    return coords


def encode_polyline6(coords, prec=1e6):
    out, plat, plng = [], 0, 0
    for lat, lng in coords:
        ilat, ilng = round(lat * prec), round(lng * prec)
        for v, p in ((ilat, plat), (ilng, plng)):
            d = v - p
            d = ~(d << 1) if d < 0 else (d << 1)
            while d >= 0x20:
                out.append(chr((0x20 | (d & 0x1F)) + 63))
                d >>= 5
            out.append(chr(d + 63))
        plat, plng = ilat, ilng
    return "".join(out)


def haversine_m(a, b):
    r = 6371008.8
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def point_segment_m(p, a, b):
    """Distance from p to segment ab in meters (local equirectangular approximation)."""
    k = math.cos(math.radians(p[0]))
    ax, ay = (a[1] - p[1]) * k, a[0] - p[0]
    bx, by = (b[1] - p[1]) * k, b[0] - p[0]
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        t = 0.0
    else:
        t = max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return math.sqrt(cx * cx + cy * cy) * 111320.0


def min_dist_to_shape_m(point, shape):
    return min(point_segment_m(point, shape[i], shape[i + 1]) for i in range(len(shape) - 1))


def shape_overlap_fraction(shape, reference, tol_m=15.0):
    if len(shape) < 2 or len(reference) < 2:
        return 0.0
    hits = sum(1 for p in shape if min_dist_to_shape_m(p, reference) <= tol_m)
    return hits / len(shape)


def cumulative_point(shape, fraction):
    total = sum(haversine_m(shape[i], shape[i + 1]) for i in range(len(shape) - 1))
    target, acc = total * fraction, 0.0
    for i in range(len(shape) - 1):
        seg = haversine_m(shape[i], shape[i + 1])
        if acc + seg >= target:
            return i, shape[i], total
        acc += seg
    return len(shape) - 1, shape[-1], total


def box_around(point, half_m):
    dlat = half_m / 111320.0
    dlon = half_m / (111320.0 * math.cos(math.radians(point[0])))
    lat, lon = point
    return [[lon - dlon, lat - dlat], [lon + dlon, lat - dlat], [lon + dlon, lat + dlat], [lon - dlon, lat + dlat], [lon - dlon, lat - dlat]]


class Client:
    def __init__(self, base, out_dir):
        self.base = base
        self.out_dir = out_dir
        self.calls = []

    def route(self, name, body):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + "/route", data=data, headers={"Content-Type": "application/json"})
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                status = resp.status
        except urllib.error.HTTPError as err:
            raw = err.read()
            status = err.code
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {"_unparsed": raw[:500].decode("utf-8", "replace")}
        (self.out_dir / f"{name}.request.json").write_text(json.dumps(body, indent=1), encoding="utf-8")
        (self.out_dir / f"{name}.response.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
        rec = {"name": name, "http_status": status, "elapsed_ms": elapsed_ms, "response_bytes": len(raw)}
        self.calls.append(rec)
        return status, payload, rec


def loc(latlon):
    return {"lat": latlon[0], "lon": latlon[1]}


def summarize_trip(payload):
    trip = payload.get("trip") or {}
    legs = trip.get("legs") or []
    if not legs:
        return None
    shape = decode_polyline6(legs[0]["shape"])
    mans = legs[0].get("maneuvers") or []
    problems = []
    last_idx = -1
    for i, m in enumerate(mans):
        if not m.get("instruction"):
            problems.append(f"maneuver {i} has empty instruction")
        if m.get("type") not in MANEUVER_TYPE_NAMES:
            problems.append(f"maneuver {i} has unknown type {m.get('type')}")
        if m.get("begin_shape_index", 0) < last_idx:
            problems.append(f"maneuver {i} shape index decreases")
        last_idx = m.get("begin_shape_index", last_idx)
    if mans and mans[0].get("type") not in (1, 2, 3):
        problems.append("first maneuver is not a start type")
    if mans and mans[-1].get("type") not in (4, 5, 6):
        problems.append("last maneuver is not a destination type")
    summ = trip.get("summary") or {}
    return {
        "time_s": summ.get("time"), "length_km": summ.get("length"), "units": trip.get("units"),
        "has_highway": summ.get("has_highway"), "has_toll": summ.get("has_toll"),
        "maneuver_count": len(mans), "shape_points": len(shape),
        "instructions": [f"{MANEUVER_TYPE_NAMES.get(m.get('type'), '?')}: {m.get('instruction')} ({m.get('length')} km, {m.get('time')} s)" for m in mans],
        "maneuver_problems": problems,
        "warnings": payload.get("warnings") or trip.get("warnings") or [],
        "_shape": shape,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8002")
    ap.add_argument("--label", required=True)
    ap.add_argument("--out-dir", default="spikes/valhalla/output")
    ap.add_argument("--results-dir", default="spikes/valhalla/results")
    args = ap.parse_args()
    out_dir, results_dir = Path(args.out_dir), Path(args.results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    c = Client(args.base, out_dir)
    results = {"label": args.label, "base": args.base, "tests": {}}
    geo_features = []

    A, B = LANDMARKS["union_station"], LANDMARKS["denver_zoo"]
    base_body = {"locations": [loc(A), loc(B)], "costing": "auto", "units": "kilometers", "id": "m0-reference"}

    # T0 cold request, then T1 warm reference
    c.route("t0_cold_reference", base_body)
    status, payload, rec = c.route("t1_reference", base_body)
    ref = summarize_trip(payload)
    assert status == 200 and ref, f"reference route failed: {status} {payload}"
    results["tests"]["t1_reference"] = {**{k: v for k, v in ref.items() if k != "_shape"}, **rec}
    ref_shape = ref["_shape"]
    geo_features.append({"type": "Feature", "properties": {"name": "reference"}, "geometry": {"type": "LineString", "coordinates": [[p[1], p[0]] for p in ref_shape]}})

    # Synthetic avoidance target: the shape point nearest 50% of the reference route length.
    idx, target, total_m = cumulative_point(ref_shape, 0.5)
    results["synthetic_target"] = {"lat": target[0], "lon": target[1], "shape_index": idx, "reference_length_m": round(total_m)}
    geo_features.append({"type": "Feature", "properties": {"name": "synthetic_target"}, "geometry": {"type": "Point", "coordinates": [target[1], target[0]]}})

    def avoidance_test(name, extra, feature_name):
        status, payload, rec = c.route(name, {**base_body, "id": name, **extra})
        s = summarize_trip(payload) if status == 200 else None
        entry = {"http_status": status, **rec}
        if s:
            entry.update({k: v for k, v in s.items() if k != "_shape"})
            entry["min_distance_to_target_m"] = round(min_dist_to_shape_m(target, s["_shape"]), 1)
            entry["overlap_with_reference_fraction"] = round(shape_overlap_fraction(s["_shape"], ref_shape), 3)
            entry["route_changed"] = entry["overlap_with_reference_fraction"] < 0.98
            entry["extra_time_s"] = round((s["time_s"] or 0) - (ref["time_s"] or 0), 1)
            entry["extra_length_km"] = round((s["length_km"] or 0) - (ref["length_km"] or 0), 3)
            geo_features.append({"type": "Feature", "properties": {"name": feature_name}, "geometry": {"type": "LineString", "coordinates": [[p[1], p[0]] for p in s["_shape"]]}})
        else:
            entry["error"] = payload
        results["tests"][name] = entry
        return s

    # T2 hard exclusion of the closest road(s) to the target
    avoidance_test("t2_exclude_locations", {"exclude_locations": [loc(target)]}, "exclude_locations")

    # T3 small exclusion polygon (about 80 m square, perimeter ~320 m)
    poly = box_around(target, 40)
    geo_features.append({"type": "Feature", "properties": {"name": "exclude_polygon_80m"}, "geometry": {"type": "Polygon", "coordinates": [poly]}})
    avoidance_test("t3_exclude_polygon", {"exclude_polygons": [poly]}, "exclude_polygon")

    # T4 soft linear cost factor along the reference shape around the target
    lo, hi = max(0, idx - 3), min(len(ref_shape) - 1, idx + 3)
    segment = ref_shape[lo:hi + 1]
    geo_features.append({"type": "Feature", "properties": {"name": "linear_cost_segment"}, "geometry": {"type": "LineString", "coordinates": [[p[1], p[0]] for p in segment]}})
    avoidance_test("t4_linear_cost_factor_1", {"linear_cost_factors": [{"shape": encode_polyline6(segment), "factor": 1.0}]}, "linear_factor_1")
    avoidance_test("t4_linear_cost_factor_50", {"linear_cost_factors": [{"shape": encode_polyline6(segment), "factor": 50.0}]}, "linear_factor_50")

    # T5 ETA contamination check: trip that must start on the penalized segment.
    forced = {"locations": [loc(target), loc(B)], "costing": "auto", "units": "kilometers"}
    s1 = summarize_trip(c.route("t5_forced_factor_1", {**forced, "id": "t5a", "linear_cost_factors": [{"shape": encode_polyline6(segment), "factor": 1.0}]})[1])
    s2 = summarize_trip(c.route("t5_forced_factor_1000", {**forced, "id": "t5b", "linear_cost_factors": [{"shape": encode_polyline6(segment), "factor": 1000.0}]})[1])
    results["tests"]["t5_eta_contamination"] = {
        "factor_1": {"time_s": s1["time_s"], "length_km": s1["length_km"]} if s1 else None,
        "factor_1000": {"time_s": s2["time_s"], "length_km": s2["length_km"]} if s2 else None,
        "same_geometry": bool(s1 and s2 and shape_overlap_fraction(s2["_shape"], s1["_shape"]) > 0.98),
        "reported_time_equal": bool(s1 and s2 and s1["time_s"] == s2["time_s"]),
    }

    # T6 alternates on the reference trip
    status, payload, rec = c.route("t6_alternates", {**base_body, "id": "t6", "alternates": 2})
    alts = payload.get("alternates") or []
    alt_entries = []
    for i, alt in enumerate(alts):
        s = summarize_trip(alt)
        if s:
            alt_entries.append({"time_s": s["time_s"], "length_km": s["length_km"], "overlap_with_reference_fraction": round(shape_overlap_fraction(s["_shape"], ref_shape), 3), "min_distance_to_target_m": round(min_dist_to_shape_m(target, s["_shape"]), 1)})
            geo_features.append({"type": "Feature", "properties": {"name": f"alternate_{i}"}, "geometry": {"type": "LineString", "coordinates": [[p[1], p[0]] for p in s["_shape"]]}})
    results["tests"]["t6_alternates"] = {"http_status": status, "alternates_returned": len(alts), "alternates": alt_entries, **rec}

    # T7 warnings for clamped / ignored inputs
    status, payload, rec = c.route("t7_warnings", {**base_body, "id": "t7", "locations": [{**loc(A), "radius": 1000}, loc(B)], "costing_options": {"auto": {"exclude_highways": True}}})
    results["tests"]["t7_warnings"] = {"http_status": status, "warnings": payload.get("warnings") or (payload.get("trip") or {}).get("warnings"), **rec}

    # T8 limits: too many exclude_locations; oversized exclude polygon perimeter
    many = [loc((target[0] + i * 0.0002, target[1])) for i in range(51)]
    status, payload, rec = c.route("t8_limit_exclude_locations", {**base_body, "id": "t8a", "exclude_locations": many})
    results["tests"]["t8_limit_exclude_locations_51"] = {"http_status": status, "error": {k: payload.get(k) for k in ("error_code", "error", "status_code")}, **rec}
    status, payload, rec = c.route("t8_limit_exclude_polygon", {**base_body, "id": "t8b", "exclude_polygons": [box_around(target, 3000)]})
    results["tests"]["t8_limit_exclude_polygon_12km_perimeter"] = {"http_status": status, "error": {k: payload.get(k) for k in ("error_code", "error", "status_code")}, **rec}

    # T9 longer trip and a trip to a point outside the service boundary (graph covers Colorado)
    for name, a, b in (("t9_long_union_to_den", A, LANDMARKS["den_terminal"]), ("t9_capitol_to_washington_park", LANDMARKS["state_capitol"], LANDMARKS["washington_park"])):
        status, payload, rec = c.route(name, {"locations": [loc(a), loc(b)], "costing": "auto", "units": "kilometers", "id": name})
        s = summarize_trip(payload) if status == 200 else None
        results["tests"][name] = {"http_status": status, **rec, **({k: v for k, v in s.items() if k not in ("_shape", "instructions")} if s else {"error": payload})}

    # T10 no-route case: a destination with no drivable access (deliberately in open water of a reservoir is not available here;
    # use a location far outside the graph instead to see the engine's error contract).
    status, payload, rec = c.route("t10_outside_graph", {"locations": [loc(A), {"lat": 36.1699, "lon": -115.1398}], "costing": "auto", "units": "kilometers", "id": "t10"})
    results["tests"]["t10_outside_graph"] = {"http_status": status, "error": {k: payload.get(k) for k in ("error_code", "error", "status_code")}, **rec}

    results["calls"] = c.calls
    (results_dir / f"route_spike_{args.label}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (results_dir / f"route_spike_{args.label}_routes.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": geo_features}), encoding="utf-8")
    print(json.dumps({k: v for k, v in results.items() if k != "calls"}, indent=1, default=str)[:12000])


if __name__ == "__main__":
    main()
