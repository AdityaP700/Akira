#!/bin/sh
set -e

echo "==> Running database migrations via Alembic..."
alembic upgrade head

echo "==> Starting Akira API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --proxy-headers
