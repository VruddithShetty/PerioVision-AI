#!/usr/bin/env bash
# Update to the latest code on GitHub: pull, rebuild, copy and re-sign any new model files, restart.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
ENVF="$REPO/.env.production"
DOCKER="docker"; docker info >/dev/null 2>&1 || DOCKER="sudo docker"
cd "$REPO" && git pull --ff-only
cd "$HERE"
bash backup.sh
$DOCKER build -t periovision-backend "$REPO/backend"
$DOCKER run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e YOLO_CONFIG_DIR=/tmp/yolo -v "$REPO":/repo -w /repo/backend \
  --entrypoint python periovision-backend scripts/make_production_env.py --resign
$DOCKER compose --env-file "$ENVF" up -d --build
echo "Updated. Check https://$(grep '^DOMAIN=' "$ENVF" | cut -d= -f2)/health"
