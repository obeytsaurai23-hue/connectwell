#!/usr/bin/env bash
set -euo pipefail

# Run migrations and collectstatic, then exec the CMD
python manage.py migrate --noinput || true
python manage.py collectstatic --noinput || true

# Execute the passed command (daphne by default in Dockerfile)
exec "$@"
