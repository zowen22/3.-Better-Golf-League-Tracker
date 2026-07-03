#!/bin/bash
# Makes the web app actually runnable at the start of a Claude Code on the
# web session:
#   1. Installs Python deps into a project-local venv (avoids fighting the
#      system's OS-managed packages, e.g. Debian's PyJWT).
#   2. Starts the local PostgreSQL server and provisions a disposable dev
#      database/role, writing DATABASE_URL to $CLAUDE_ENV_FILE.
#
# Postgres, not SQLite, on purpose: the app's entire query surface (casts,
# ON CONFLICT, RETURNING, Postgres-strict GROUP BY, etc.) is written for
# Postgres semantics per the project's own migration — database.py's SQLite
# fallback path only ever worked for schema creation, not for actually
# running routes (every route uses %s placeholders, which raw sqlite3
# rejects outright). Postgres is the only path that faithfully runs this
# app locally.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r app/requirements.txt

if command -v pg_lsclusters >/dev/null 2>&1; then
  if ! pg_lsclusters 2>/dev/null | grep -q "online"; then
    service postgresql start >/dev/null 2>&1 || true
    sleep 2
  fi

  if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='golf_dev'" 2>/dev/null | grep -q 1; then
    sudo -u postgres psql -c "CREATE USER golf_dev WITH PASSWORD 'golf_dev_local' SUPERUSER;" >/dev/null 2>&1 || true
  fi
  if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='golf_league_dev'" 2>/dev/null | grep -q 1; then
    sudo -u postgres psql -c "CREATE DATABASE golf_league_dev OWNER golf_dev;" >/dev/null 2>&1 || true
  fi

  echo 'export DATABASE_URL="postgresql://golf_dev:golf_dev_local@localhost:5432/golf_league_dev"' >> "$CLAUDE_ENV_FILE"
fi
