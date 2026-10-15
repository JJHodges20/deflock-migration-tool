"""M0 geocoder spike: query a local self-hosted Nominatim (Colorado extract) with public landmarks
and public office addresses only. Records latency and the top result for each query.

Usage: python -I spikes/nominatim/test_queries.py --base http://127.0.0.1:8081 --label 2026-10-15
"""
import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

QUERIES = [
    ("search", "Union Station, Denver, CO"),
    ("search", "Denver Zoo"),
    ("search", "Colorado State Capitol, Denver"),
    ("search", "Denver International Airport"),
    ("search", "Red Rocks Amphitheatre"),
    ("search", "1437 Bannock St, Denver, CO"),          # City and County Building (public office address)
    ("search", "200 E Colfax Ave, Denver, CO 80203"),   # Colorado State Capitol street address
    ("search", "1701 Wynkoop St, Denver, CO"),          # Union Station street address
    ("search", "2300 Steele St, Denver, CO"),           # Denver Zoo street address
    ("search", "Washington Park, Denver"),
    ("search", "Glendale, Colorado"),
    ("search", "Nonexistent Street 99999, Denver"),
    ("reverse", (39.7393, -104.9848)),
    ("reverse", (39.8494, -104.6737)),
]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "DeFlockMigration-M0-feasibility/0.1 (local self-hosted instance)"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read()
            status = resp.status
    except urllib.error.HTTPError as err:
        body, status = err.read(), err.code
    ms = round((time.perf_counter() - t0) * 1000, 1)
    try:
        return status, json.loads(body.decode("utf-8")), ms
    except json.JSONDecodeError:
        return status, {"_unparsed": body[:300].decode("utf-8", "replace")}, ms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8081")
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    out = {"label": args.label, "base": args.base, "status": None, "queries": []}
    status, payload, ms = get(args.base + "/status?format=json")
    out["status"] = {"http": status, "payload": payload, "ms": ms}
    for kind, q in QUERIES:
        if kind == "search":
            url = args.base + "/search?" + urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 3, "countrycodes": "us"})
        else:
            url = args.base + "/reverse?" + urllib.parse.urlencode({"lat": q[0], "lon": q[1], "format": "jsonv2"})
        # warm the query once, then time it
        get(url)
        status, payload, ms = get(url)
        results = payload if isinstance(payload, list) else [payload]
        top = results[0] if results and isinstance(results[0], dict) else None
        out["queries"].append({
            "kind": kind, "query": q, "http": status, "ms": ms, "result_count": len(results) if isinstance(payload, list) else (1 if top and "error" not in top else 0),
            "top": {k: top.get(k) for k in ("display_name", "lat", "lon", "category", "type", "addresstype", "importance", "name")} if top else None,
            "error": (top or {}).get("error") if top else payload,
        })
    results_dir = Path("spikes/nominatim/results")
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / f"queries_{args.label}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out["status"], indent=1)[:600])
    for q in out["queries"]:
        top = q["top"] or {}
        print(f"{q['kind']:7} {str(q['query'])[:40]:40} http={q['http']} n={q['result_count']} {q['ms']:6} ms -> {str(top.get('display_name'))[:95]} [{top.get('addresstype')}] ({top.get('lat')}, {top.get('lon')})")


if __name__ == "__main__":
    main()
