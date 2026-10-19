#!/bin/bash
# Setup job: build the Valhalla routing graph from the regional extract, entirely inside the pinned container.
# Idempotent: skips when the current graph was built from the same extract (by SHA-256) unless FORCE_REBUILD=1.
# Ported from the M0 spike (spikes/valhalla/container_build.sh) with the same stages and timing record.
set -uo pipefail

PBF=${PBF:-/pbf/colorado-latest.osm.pbf}
D=${DATA_DIR:-/data}
CONC=${CONCURRENCY:-8}
FORCE=${FORCE_REBUILD:-0}
MANIFEST="$D/graph_manifest.json"
TIMING="$D/stage_timing.csv"

log() { echo "[$(date -u +%FT%TZ)] [deflock-graph-build] $*"; }

if [ ! -f "$PBF" ]; then
  log "extract not found at $PBF; run the osm-download job first"
  exit 2
fi

RECORD="${PBF}.download_record.json"
if [ -f "$RECORD" ]; then
  PBF_SHA=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['sha256'])" "$RECORD")
else
  log "no download record; hashing the extract"
  PBF_SHA=$(sha256sum "$PBF" | cut -d' ' -f1)
fi

if [ "$FORCE" != "1" ] && [ -f "$MANIFEST" ] && [ -f "$D/tiles.tar" ]; then
  CURRENT=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('pbf_sha256',''))" "$MANIFEST")
  if [ "$CURRENT" = "$PBF_SHA" ]; then
    log "graph already built from this extract (sha256 $PBF_SHA); skipping. Set GRAPH_FORCE_REBUILD=1 to rebuild."
    exit 0
  fi
fi

# Build into a staging directory so a failed rebuild never destroys the active graph.
STAGE="$D/staging"
rm -rf "$STAGE"
mkdir -p "$STAGE/tiles"
: > "$TIMING"
BUILD_START=$(date +%s)

stage() {
  local name=$1; shift
  local t0=$(date +%s)
  log "START $name"
  "$@"
  local rc=$?
  local secs=$(( $(date +%s) - t0 ))
  log "END $name rc=$rc seconds=$secs"
  echo "$name,$secs,$rc" >> "$TIMING"
  if [ "$rc" -ne 0 ]; then log "stage $name failed; active graph left untouched"; exit "$rc"; fi
}

stage build_config bash -c "valhalla_build_config \
  --mjolnir-tile-dir $D/tiles \
  --mjolnir-tile-extract $D/tiles.tar \
  --mjolnir-timezone $D/timezones.sqlite \
  --mjolnir-admin $D/admins.sqlite \
  --mjolnir-concurrency $CONC \
  > $STAGE/valhalla.json"
# Verbose /status exposes tileset dates and the bounding box to Data Health.
sed -i 's/"allow_verbose": false/"allow_verbose": true/' "$STAGE/valhalla.json"
# Build into staging paths first (the config above points at the final paths; override for the build).
python3 - "$STAGE/valhalla.json" "$STAGE" <<'PY'
import json, sys
path, stage = sys.argv[1], sys.argv[2]
cfg = json.load(open(path))
cfg["mjolnir"]["tile_dir"] = f"{stage}/tiles"
cfg["mjolnir"]["tile_extract"] = f"{stage}/tiles.tar"
cfg["mjolnir"]["timezone"] = f"{stage}/timezones.sqlite"
cfg["mjolnir"]["admin"] = f"{stage}/admins.sqlite"
json.dump(cfg, open(f"{stage}/build.json", "w"), indent=1)
PY

stage build_timezones bash -c "valhalla_build_timezones > $STAGE/timezones.sqlite"
stage build_admins valhalla_build_admins -c "$STAGE/build.json" "$PBF"
stage build_tiles valhalla_build_tiles -c "$STAGE/build.json" "$PBF"
stage build_extract valhalla_build_extract -c "$STAGE/build.json" -v

TILE_COUNT=$(find "$STAGE/tiles" -type f -name '*.gph' | wc -l)
if [ "$TILE_COUNT" -lt 1 ] || [ ! -s "$STAGE/tiles.tar" ]; then
  log "build produced no tiles; active graph left untouched"
  exit 3
fi

# Promote: swap staging into place. The graph being replaced is kept as the last-good graph in $D/previous
# (tar, config, manifest, and databases; its tile directory is dropped, the tar is what the service reads), so
# rollback_graph.sh can put it back without a rebuild. A running valhalla keeps serving the files it already
# opened until it is restarted, so routes computed during this promotion are unaffected.
rm -rf "$D/previous.new"
mkdir -p "$D/previous.new"
for f in tiles.tar valhalla.json graph_manifest.json timezones.sqlite admins.sqlite; do
  [ -f "$D/$f" ] && mv "$D/$f" "$D/previous.new/$f"
done
rm -rf "$D/tiles"
mv "$STAGE/tiles" "$D/tiles"
mv "$STAGE/tiles.tar" "$D/tiles.tar"
mv "$STAGE/timezones.sqlite" "$D/timezones.sqlite"
mv "$STAGE/admins.sqlite" "$D/admins.sqlite"
mv "$STAGE/valhalla.json" "$D/valhalla.json"
if [ -f "$D/previous.new/graph_manifest.json" ]; then
  rm -rf "$D/previous"
  mv "$D/previous.new" "$D/previous"
else
  rm -rf "$D/previous.new"
fi
rm -rf "$D/rolled_back" "$STAGE"

python3 - "$MANIFEST" "$PBF" "$PBF_SHA" "$TILE_COUNT" "$(( $(date +%s) - BUILD_START ))" "$CONC" <<'PY'
import json, sys, datetime, subprocess
manifest, pbf, sha, tiles, seconds, conc = sys.argv[1:]
version = subprocess.run(["valhalla_build_tiles", "--version"], capture_output=True, text=True).stdout.strip()
json.dump({
    "graph_id": f"valhalla-{version}-{sha[:12]}",
    "valhalla_version": version,
    "pbf": pbf,
    "pbf_sha256": sha,
    "tile_count": int(tiles),
    "build_seconds": int(seconds),
    "concurrency": int(conc),
    "built_at": datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
}, open(manifest, "w"), indent=1)
PY
log "BUILD COMPLETE: $(cat "$MANIFEST")"
