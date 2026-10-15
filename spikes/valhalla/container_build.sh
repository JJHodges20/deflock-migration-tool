#!/bin/bash
# DeFlockMigration M0 spike - runs INSIDE the pinned Valhalla container.
# Builds a routing graph from a Geofabrik extract mounted at /pbf and writes
# everything to /data (a named Docker volume). Records per-stage timing.
set -uo pipefail

PBF=${PBF:-/pbf/colorado-latest.osm.pbf}
D=${DATA_DIR:-/data}
CONC=${CONCURRENCY:-8}
TIMING="$D/stage_timing.csv"

log() { echo "[$(date -u +%FT%TZ)] $*"; }

stage() {
  local name=$1; shift
  local t0=$(date +%s)
  log "START $name"
  "$@"
  local rc=$?
  local secs=$(( $(date +%s) - t0 ))
  log "END $name rc=$rc seconds=$secs"
  echo "$name,$secs,$rc" >> "$TIMING"
  if [ "$rc" -ne 0 ]; then log "stage $name failed; aborting"; exit "$rc"; fi
}

mkdir -p "$D/tiles"
: > "$TIMING"
log "valhalla version: $(valhalla_build_tiles --version 2>&1 | head -1)"
log "pbf: $PBF ($(stat -c %s "$PBF") bytes)"
log "concurrency: $CONC"

stage build_config bash -c "valhalla_build_config \
  --mjolnir-tile-dir $D/tiles \
  --mjolnir-tile-extract $D/tiles.tar \
  --mjolnir-timezone $D/timezones.sqlite \
  --mjolnir-admin $D/admins.sqlite \
  --mjolnir-concurrency $CONC \
  > $D/valhalla.json"

# Allow verbose /status so the spike can read the tileset's bounding box and dates.
sed -i 's/"allow_verbose": false/"allow_verbose": true/' "$D/valhalla.json"
grep -c '"allow_verbose": true' "$D/valhalla.json" >/dev/null && log "status.allow_verbose enabled"

stage build_timezones bash -c "valhalla_build_timezones > $D/timezones.sqlite"
stage build_admins valhalla_build_admins -c "$D/valhalla.json" "$PBF"
stage build_tiles valhalla_build_tiles -c "$D/valhalla.json" "$PBF"
stage build_extract valhalla_build_extract -c "$D/valhalla.json" -v

log "sizes:"
du -sh "$D/tiles" "$D/tiles.tar" "$D/admins.sqlite" "$D/timezones.sqlite" 2>&1
log "tile count: $(find "$D/tiles" -type f -name '*.gph' | wc -l)"
log "BUILD COMPLETE"
