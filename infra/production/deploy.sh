#!/usr/bin/env bash
#
# Deploy EOPP to production: dev -> GitHub -> prod.
#
# Run from a workstation. It never copies code over SSH — the server pulls the
# commit from GitHub, so what runs in production is a named commit anyone can
# check out, not whatever happened to be in someone's working tree.
#
#   ./infra/production/deploy.sh
#
# Assumes, once:
#   - the repo exists on GitHub, private, and the server can read it
#   - infra/.env exists ON THE SERVER with the secrets (never in git)
#   - the Apache vhost is installed and certbot has issued a certificate
set -euo pipefail

HOST="${EOPP_HOST:-prod}"
DIR="${EOPP_DIR:-/home/jmwebaze/eopp}"
BRANCH="${EOPP_BRANCH:-master}"
COMPOSE="docker compose -f docker-compose.yml"

say() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

say "Checking the working tree is clean and pushed"
if [ -n "$(git status --porcelain)" ]; then
  echo "Working tree is dirty. Commit or stash first — production runs a commit, not a draft." >&2
  exit 1
fi
git push origin "$BRANCH"
LOCAL_SHA="$(git rev-parse HEAD)"
echo "deploying $LOCAL_SHA"

say "Pulling on the server"
ssh "$HOST" "set -euo pipefail
  cd '$DIR'
  git fetch --all --prune
  git checkout '$BRANCH'
  git reset --hard '$LOCAL_SHA'
  git rev-parse HEAD"

say "Building and starting"
# Only docker-compose.yml. The dev overlay carries development defaults and
# publishes ports this host must not expose.
ssh "$HOST" "set -euo pipefail
  cd '$DIR/infra'
  $COMPOSE build web
  $COMPOSE up -d --remove-orphans"

say "Migrating"
ssh "$HOST" "cd '$DIR/infra' && $COMPOSE exec -T web python manage.py migrate --noinput"

say "Collecting static files"
ssh "$HOST" "cd '$DIR/infra' && $COMPOSE exec -T web python manage.py collectstatic --noinput" >/dev/null

say "Smoke test"
# The forwarded-protocol header is what the proxy sets; without it Django's
# SECURE_SSL_REDIRECT answers 301 and the line reads like a failure.
ssh "$HOST" "curl -fsS -o /dev/null \
  -H 'X-Forwarded-Proto: https' -H 'Host: eopp.johnsonmwebaze.info' \
  -w 'healthz via loopback: %{http_code}\n' http://127.0.0.1:8007/healthz/"

for path in / /login /api/docs/ /admin/login/; do
  curl -fsS -o /dev/null -w "  https://eopp.johnsonmwebaze.info$path -> %{http_code}\n" \
    "https://eopp.johnsonmwebaze.info$path"
done
curl -fsS -o /dev/null -w "  https://eopp.johnsonmwebaze.info/healthz/ -> %{http_code}\n" "https://eopp.johnsonmwebaze.info/healthz/"

say "Deployed $LOCAL_SHA"
