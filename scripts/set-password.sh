#!/usr/bin/env bash
# Change an account password on the dev stack, from the host.
#
# Thin wrapper around `manage.py set_password` — the command itself carries the
# behaviour (validators, §9 history, axes lockout reset). All this adds is the
# compose invocation and the -T decision: the hidden prompt needs a TTY, and
# --stdin needs the opposite.
#
#   scripts/set-password.sh cm1                     # prompt twice, hidden
#   scripts/set-password.sh cm1 --generate          # random, printed once
#   scripts/set-password.sh --role CASE_MANAGER --generate
#   echo 'correct-horse-battery' | scripts/set-password.sh cm1 --stdin
#
# See `scripts/set-password.sh --help` for the full argument list.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/infra"

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.dev.yml"

if ! $COMPOSE ps --status running --services 2>/dev/null | grep -qx web; then
    echo "The 'web' service is not running. Start the stack first:" >&2
    echo "  cd infra && $COMPOSE up -d" >&2
    exit 1
fi

# A TTY for the interactive prompt; -T when the password arrives on a pipe.
TTY_FLAG=()
if [[ " $* " == *" --stdin "* ]] || [[ ! -t 0 ]]; then
    TTY_FLAG=(-T)
fi

exec $COMPOSE exec "${TTY_FLAG[@]}" web python manage.py set_password "$@"
