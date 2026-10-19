#!/bin/bash
# Setup job: swap the active routing graph with the last-good one that build_graph.sh kept in $DATA_DIR/previous
# when it promoted the current graph. The replaced graph is kept as $DATA_DIR/rolled_back, and running this job
# again with no "previous" graph swaps that one back in (undo). Restart the valhalla service afterwards; a running
# service keeps serving the files it already opened.
set -uo pipefail

D=${DATA_DIR:-/data}
FILES="tiles.tar valhalla.json graph_manifest.json timezones.sqlite admins.sqlite"

log() { echo "[$(date -u +%FT%TZ)] [deflock-graph-rollback] $*"; }

complete() {  # all graph files present in the given directory
  for f in $FILES; do [ -f "$1/$f" ] || return 1; done
  return 0
}

if complete "$D/previous"; then
  SRC="$D/previous"; DEST="$D/rolled_back"; WHAT="previous (last-good) graph"
elif complete "$D/rolled_back"; then
  SRC="$D/rolled_back"; DEST="$D/previous"; WHAT="graph that was rolled back earlier (undoing the rollback)"
else
  log "no complete previous or rolled-back graph in $D; nothing to swap"
  exit 2
fi
if ! complete "$D"; then
  log "the active graph in $D is incomplete; refusing to guess"
  exit 2
fi

log "active graph: $(cat "$D/graph_manifest.json")"
log "swapping in the $WHAT: $(cat "$SRC/graph_manifest.json")"

rm -rf "$DEST.new"
mkdir -p "$DEST.new"
for f in $FILES; do mv "$D/$f" "$DEST.new/$f"; done
# The tile directory belongs to the current build only; a swapped-in graph is served from its tar.
rm -rf "$D/tiles"
for f in $FILES; do mv "$SRC/$f" "$D/$f"; done
rmdir "$SRC" 2>/dev/null || true
rm -rf "$DEST"
mv "$DEST.new" "$DEST"
log "SWAP COMPLETE: now serving $(cat "$D/graph_manifest.json"); the replaced graph is kept in $DEST. Restart the valhalla service to load it."
