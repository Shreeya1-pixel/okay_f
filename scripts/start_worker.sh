#!/bin/sh
set -eu

CONCURRENCY="${CELERY_CONCURRENCY:-2}"
QUEUES="${CELERY_QUEUES:-ingestion,nlp,gti,default,market}"

echo "Starting Celery worker (concurrency=${CONCURRENCY}, queues=${QUEUES})"
exec celery -A app.tasks.celery_app worker --loglevel=info --concurrency="${CONCURRENCY}" -Q "${QUEUES}"
