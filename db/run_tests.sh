#!/usr/bin/env bash
# Apply pending migrations, then run the constraint suite.
#
#   ./db/run_tests.sh                      # PGHOST/PGPORT for a local cluster
#   DATABASE_URL=postgres://... ./db/run_tests.sh
#   FRESH=1 ./db/run_tests.sh              # recreate the database first
#
# Migrations are tracked in schema_migrations and are skipped once applied.
# A file whose checksum changed after being applied is an error: edit-in-place
# on an applied migration means environments have silently diverged.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -n "${DATABASE_URL:-}" ]]; then
  PSQL=(psql "$DATABASE_URL")
else
  : "${PGHOST:?set DATABASE_URL, or PGHOST/PGPORT for a local cluster}"
  PSQL=(psql -h "$PGHOST" -p "${PGPORT:-5432}" -U "${PGUSER:-consensus}" -d "${PGDATABASE:-consensus_test}")
fi

echo "==> migrations"
for f in db/migrations/*.sql; do
  name=$(basename "$f")
  sum=$(shasum -a 256 "$f" | cut -d' ' -f1)
  applied=$("${PSQL[@]}" -tAc \
    "SELECT checksum FROM schema_migrations WHERE filename='$name'" 2>/dev/null || true)

  if [[ -n "$applied" ]]; then
    if [[ "$applied" != "$sum" ]]; then
      echo "    ERROR $name was applied with a different checksum — never edit an applied migration" >&2
      exit 1
    fi
    echo "    skip  $name"
    continue
  fi

  echo "    apply $name"
  "${PSQL[@]}" -v ON_ERROR_STOP=1 -q -f "$f"
  "${PSQL[@]}" -v ON_ERROR_STOP=1 -q -c \
    "INSERT INTO schema_migrations (filename, checksum) VALUES ('$name', '$sum')"
done

echo "==> constraint suite"
"${PSQL[@]}" -v ON_ERROR_STOP=1 -q -f db/tests/constraints_test.sql 2>&1 \
  | sed 's/^psql:[^ ]*: //' | grep -E "PASS|FAIL|ALL CONSTRAINT|^[a-z]" || true
