#!/usr/bin/env bash
# PerioVision AI - one-time setup of the full production stack on a fresh Ubuntu 22.04 / 24.04 server
# (x86_64 or ARM, e.g. Oracle Cloud Always Free Ampere A1). Run from deploy/server inside the cloned repository:
#     bash setup.sh your-name.duckdns.org
# It installs Docker, opens ports 80 / 443 in the server's own firewall, builds the images, creates fresh
# production secrets and signing keys ON THIS SERVER, starts MongoDB + backend + web, asks you to create the first
# admin account, and schedules a nightly backup. Safe to run again: existing secrets and keys are never replaced.
set -euo pipefail
DOMAIN="${1:?usage: bash setup.sh <domain, e.g. clinic.duckdns.org>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
ENVF="$REPO/.env.production"
cd "$HERE"

echo "== 1/7 Docker and firewall"
if ! command -v docker >/dev/null; then
  sudo apt-get update -y
  sudo apt-get install -y docker.io docker-compose-v2 git cron
  sudo usermod -aG docker "$USER" || true
fi
DOCKER="docker"; docker info >/dev/null 2>&1 || DOCKER="sudo docker"
for port in 80 443; do                     # Oracle Ubuntu images block everything but SSH in iptables
  sudo iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 1 -p tcp --dport "$port" -j ACCEPT
done
command -v netfilter-persistent >/dev/null && sudo netfilter-persistent save || true

echo "== 2/7 Build the backend image (the first build downloads PyTorch, about 10-20 minutes)"
$DOCKER build -t periovision-backend "$REPO/backend"

echo "== 3/7 Production secrets, keys and signed model copy (created here, never leave this server)"
if [ ! -f "$ENVF" ]; then
  mkdir -p "$REPO/backend/"{keys,weights,storage,logs}-production
  $DOCKER run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e YOLO_CONFIG_DIR=/tmp/yolo -v "$REPO":/repo -w /repo/backend \
    --entrypoint python periovision-backend scripts/make_production_env.py
else
  echo "   .env.production exists: kept"
fi
chmod 600 "$ENVF"
grep -q '^DOMAIN=' "$ENVF" && sed -i "s#^DOMAIN=.*#DOMAIN=$DOMAIN#" "$ENVF" || echo "DOMAIN=$DOMAIN" >> "$ENVF"

echo "== 4/7 Start MongoDB, backend and web (HTTPS certificate for $DOMAIN is requested automatically)"
$DOCKER compose --env-file "$ENVF" up -d --build

echo "== 5/7 Wait for the backend"
for i in $(seq 1 60); do
  $DOCKER compose --env-file "$ENVF" exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health', timeout=3)" 2>/dev/null && break
  sleep 5
done

echo "== 6/7 First admin account (you type the password; it is never stored in a file)"
if [ -t 0 ]; then
  $DOCKER compose --env-file "$ENVF" exec backend python scripts/create_admin.py || echo "   skipped (run it later: see README.md)"
fi

echo "== 7/7 Nightly backup at 02:30"
chmod +x "$HERE/backup.sh" "$HERE/update.sh"
echo "30 2 * * * $USER bash $HERE/backup.sh >> $REPO/backend/logs-production/backup.log 2>&1" | sudo tee /etc/cron.d/periovision-backup >/dev/null

echo
echo "Done. Open https://$DOMAIN  (the certificate can take a minute the first time)."
echo "Sign in as the admin, enrol MFA in Security center, then create the dentists' accounts in Admin."
echo "Back up .env.production and backend/keys-production somewhere safe: without them the encrypted data is lost."
