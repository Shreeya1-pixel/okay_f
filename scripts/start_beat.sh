#!/bin/sh
set -eu

echo "Starting Celery beat scheduler..."
exec celery -A app.tasks.celery_app beat --loglevel=info
