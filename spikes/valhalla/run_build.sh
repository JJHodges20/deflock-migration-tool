#!/usr/bin/env bash
# DeFlockMigration M0 spike - host side (Git Bash on Windows).
# Builds the Valhalla graph entirely inside the pinned container; the host needs only Docker.
set -euo pipefail
export MSYS_NO_PATHCONV=1

IMAGE="ghcr.io/valhalla/valhalla:3.9.1"
VOLUME="deflock_valhalla_spike"
NAME="deflock-valhalla-build"
PROJECT="C:/Users/jjhod/Documents/Claude Workspace/DeFlockMigration"
PBF_DIR="$PROJECT/data/raw/osm"
SPIKE_DIR="$PROJECT/spikes/valhalla"

docker volume create "$VOLUME" >/dev/null
docker rm -f "$NAME" >/dev/null 2>&1 || true

echo "host_build_start=$(date -u +%FT%TZ)"
docker run --rm --name "$NAME" \
  -e CONCURRENCY="${CONCURRENCY:-8}" \
  -v "$VOLUME:/data" \
  -v "$PBF_DIR:/pbf:ro" \
  -v "$SPIKE_DIR:/spike:ro" \
  --entrypoint /bin/bash "$IMAGE" /spike/container_build.sh
rc=$?
echo "host_build_end=$(date -u +%FT%TZ) rc=$rc"
exit $rc
