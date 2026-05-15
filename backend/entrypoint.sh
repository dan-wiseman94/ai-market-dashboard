#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] waiting for postgres at ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}..."
until pg_isready -h "${POSTGRES_HOST:-db}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER}" > /dev/null 2>&1; do
  sleep 0.5
done
echo "[entrypoint] postgres is ready"

echo "[entrypoint] running migrations..."
uv run python manage.py migrate --noinput

echo "[entrypoint] launching: $*"
exec uv run "$@"
