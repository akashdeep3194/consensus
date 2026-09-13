#!/usr/bin/env bash
# One command to a running game.
#
#   ./scripts/dev.sh            start (reuses existing data)
#   ./scripts/dev.sh --fresh    wipe the database and seed a played round first
#
# Uses a local PostgreSQL cluster under .devdata so nothing external is needed.
set -euo pipefail
cd "$(dirname "$0")/.."

# Local-only secrets this script has no opinion on (Google OAuth credentials,
# an explicit SESSION_SECRET) — everything below that dev.sh *does* manage
# (PG*, DEV_LOGIN, DEMO_ROUND_MINUTES) still wins even if this file sets it.
[[ -f .env.dev ]] && set -a && source .env.dev && set +a

PORT=${PORT:-8099}
PGPORT=${PGPORT:-55432}
DATA=.devdata
FRESH=0
[[ "${1:-}" == "--fresh" ]] && FRESH=1

PGBIN=$(ls -d /opt/homebrew/opt/postgresql@1*/bin 2>/dev/null | sort -r | head -1 || true)
[[ -n "$PGBIN" ]] && export PATH="$PGBIN:$PATH"
command -v pg_ctl >/dev/null || { echo "PostgreSQL not found. brew install postgresql@17"; exit 1; }

# ── database ───────────────────────────────────────────────────────────────
if [[ ! -d $DATA/pgdata ]]; then
  echo "==> initialising cluster in $DATA"
  mkdir -p $DATA
  initdb -D $DATA/pgdata -U consensus --auth=trust -E UTF8 >/dev/null
fi

# The socket directory is remembered in $DATA/socket. A macOS unix socket path
# is capped at ~103 bytes, so it must live in /tmp rather than beside the repo.
if pg_ctl -D $DATA/pgdata status >/dev/null 2>&1 && [[ -S "$(cat $DATA/socket 2>/dev/null)/.s.PGSQL.$PGPORT" ]]; then
  SOCK=$(cat $DATA/socket)
  echo "==> postgres already running on :$PGPORT"
else
  pg_ctl -D $DATA/pgdata stop >/dev/null 2>&1 || true
  SOCK=$(mktemp -d /tmp/cx.XXXX)
  echo "==> starting postgres on :$PGPORT"
  pg_ctl -D $DATA/pgdata -o "-p $PGPORT -k $SOCK -c listen_addresses=''" \
         -l $DATA/pg.log start >/dev/null
  for _ in $(seq 1 25); do
    [[ -S "$SOCK/.s.PGSQL.$PGPORT" ]] && break
    sleep 0.3
  done
  echo "$SOCK" > $DATA/socket
fi

export PGHOST=$SOCK PGPORT PGUSER=consensus PGPASSWORD=consensus PGDATABASE=consensus
export DEV_LOGIN=1 DEMO_ROUND_MINUTES=${DEMO_ROUND_MINUTES:-10}

# Stop any running api first: it holds connections to the database we may drop.
pkill -f "uvicorn api.main" 2>/dev/null || true
sleep 1

psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='consensus'" | grep -q 1 \
  || psql -d postgres -q -c "CREATE DATABASE consensus;"

if [[ $FRESH == 1 ]]; then
  echo "==> resetting database"
  # WITH (FORCE) evicts an api process still holding a connection; without it a
  # re-run of --fresh fails whenever the previous server has not fully exited.
  psql -d postgres -q \
    -c "DROP DATABASE IF EXISTS consensus WITH (FORCE);" \
    -c "CREATE DATABASE consensus;"
fi

# A fixed anchor keeps cycle numbers stable across restarts.
if [[ $FRESH == 1 || ! -f $DATA/anchor ]]; then
  .venv/bin/python -c "from datetime import datetime,UTC;print(datetime.now(UTC).isoformat())" > $DATA/anchor
fi
export ROUND_ANCHOR=$(cat $DATA/anchor)

# ── server ─────────────────────────────────────────────────────────────────
echo "==> starting api on :$PORT"
.venv/bin/uvicorn api.main:app --port $PORT --log-level warning > $DATA/api.log 2>&1 &
for _ in $(seq 1 30); do
  curl -sf localhost:$PORT/api/health >/dev/null && break
  sleep 0.4
done

if [[ $FRESH == 1 ]]; then
  echo "==> seeding a completed round and a live one"
  .venv/bin/python scripts/demo_round.py "http://localhost:$PORT" > $DATA/demo.log 2>&1 \
    && grep -E "WINNING NUMBER" $DATA/demo.log | sed 's/^/    /'
  .venv/bin/python scripts/seed_live.py "http://localhost:$PORT" | sed 's/^/    /'
fi

echo
echo "  ▸ play:      http://localhost:$PORT/dev/login?handle=akash"
echo "  ▸ api docs:  http://localhost:$PORT/docs"
echo "  ▸ logs:      tail -f $DATA/api.log"
echo "  ▸ stop:      pkill -f 'uvicorn api.main'"
