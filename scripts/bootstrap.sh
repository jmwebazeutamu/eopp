#!/usr/bin/env bash
# First-run setup for a fresh checkout. Idempotent — safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/infra"

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.dev.yml"

if [[ ! -f .env ]]; then
    echo "==> Creating infra/.env with generated secrets"
    python3 - <<'PY'
import pathlib, secrets

template = pathlib.Path(".env.example").read_text()
generated = {
    "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
    "DB_PASSWORD": secrets.token_urlsafe(24),
    "MINIO_ROOT_USER": "yepadmin",
    "MINIO_ROOT_PASSWORD": secrets.token_urlsafe(24),
}
lines = []
for line in template.splitlines():
    key = line.split("=", 1)[0]
    lines.append(f"{key}={generated[key]}" if key in generated and line.endswith("=") else line)
pathlib.Path(".env").write_text("\n".join(lines) + "\n")
PY
    chmod 600 .env
else
    echo "==> infra/.env already exists, leaving it alone"
fi

echo "==> Building and starting the stack"
$COMPOSE up -d --build

echo "==> Waiting for the database"
until $COMPOSE exec -T db pg_isready -q; do sleep 2; done

echo "==> Applying migrations"
$COMPOSE exec -T web python manage.py migrate --noinput

echo
echo "Stack is up:"
echo "  API / admin    http://localhost:8007/admin/"
echo "  API docs       http://localhost:8007/api/docs/"
echo "  Health         http://localhost:8007/healthz/"
echo "  MinIO console  http://localhost:8008/"
echo
echo "Create your first administrator:"
echo "  $COMPOSE exec web python manage.py createsuperuser"
