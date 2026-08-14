#!/bin/sh
set -eu

PORT="${PORT:-8000}"
WORKERS="${WEB_CONCURRENCY:-1}"

if [ -z "${DATABASE_URL:-}${DATABASE_SYNC_URL:-}" ]; then
  echo "ERROR: DATABASE_URL / DATABASE_SYNC_URL is not set. Link Postgres first."
  exit 1
fi

echo "Running database migrations..."
alembic upgrade head

echo "Starting API on 0.0.0.0:${PORT} (workers=${WORKERS})"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --workers "${WORKERS}"
