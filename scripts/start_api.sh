#!/bin/sh
set -eu

PORT="${PORT:-8000}"
WORKERS="${WEB_CONCURRENCY:-2}"

echo "Running database migrations..."
alembic upgrade head

echo "Starting API on 0.0.0.0:${PORT} (workers=${WORKERS})"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --workers "${WORKERS}"
