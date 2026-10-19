#!/usr/bin/env bash
# Nightly backup: database dump, encrypted files and audit anchors, and (separately, mode 600) the secrets and keys
# needed to read them. Keeps 14 days in <repo>/backups. Copy that folder off the server regularly.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
ENVF="$REPO/.env.production"
OUT="$REPO/backups"; TS="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"; chmod 700 "$OUT"
DOCKER="docker"; docker info >/dev/null 2>&1 || DOCKER="sudo docker"
set -a; . "$ENVF"; set +a
cd "$HERE"
$DOCKER compose --env-file "$ENVF" exec -T mongodb mongodump --quiet --archive --gzip \
  -u "$MONGO_ROOT_USER" -p "$MONGO_ROOT_PASSWORD" --authenticationDatabase admin > "$OUT/db-$TS.archive.gz"
tar -czf "$OUT/files-$TS.tgz" -C "$REPO/backend" storage-production logs-production
tar -czf "$OUT/secrets-$TS.tgz" -C "$REPO" .env.production backend/keys-production
chmod 600 "$OUT"/*-"$TS".*
find "$OUT" -type f -mtime +14 -delete
echo "$(date -Is) backup $TS done: $(du -sh "$OUT" | cut -f1) in $OUT"
