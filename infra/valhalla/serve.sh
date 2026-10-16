#!/bin/bash
# Serve the routing graph. Waits for a completed build instead of crash-looping, and says why.
set -uo pipefail
DATA=${DATA_DIR:-/data}
THREADS=${VALHALLA_THREADS:-2}
until [ -f "$DATA/graph_manifest.json" ] && [ -f "$DATA/valhalla.json" ] && [ -f "$DATA/tiles.tar" ]; do
  echo "[deflock-valhalla] no completed routing graph in $DATA yet. Run the setup profile (graph-build) first. Checking again in 30 s."
  sleep 30
done
echo "[deflock-valhalla] serving graph: $(cat "$DATA/graph_manifest.json")"
exec valhalla_service "$DATA/valhalla.json" "$THREADS"
