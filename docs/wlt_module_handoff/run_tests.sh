#!/usr/bin/env bash
# Applies the schema to a scratch database and runs the assertion suite.
# Expected last line: ALL ASSERTIONS PASSED
set -euo pipefail

DB="${1:-wlt_scratch}"
DIR="$(cd "$(dirname "$0")/sql" && pwd)"

echo "Rebuilding $DB ..."
dropdb --if-exists "$DB"
createdb "$DB"

for f in 000_core_stubs.sql 001_wlt_schema.sql 002_constraints_indexes.sql \
         003_policy_seed.sql 004_reporting_views.sql 900_test_seed_and_assertions.sql; do
    echo "--- $f"
    psql -d "$DB" -v ON_ERROR_STOP=1 -q -f "$DIR/$f"
done
