#!/usr/bin/env bash
# Simple Postgres backup script using pg_dump
# Expects environment variables: PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE
# Or a DATABASE_URL in the form postgres://user:pass@host:port/dbname

set -euo pipefail

if [ -z "${PGDATABASE:-}" ]; then
  # try to parse DATABASE_URL
  if [ -n "${DATABASE_URL:-}" ]; then
    echo "Parsing DATABASE_URL"
    export PGHOST=$(echo "$DATABASE_URL" | sed -E 's#.*@([^:/]+).*#\1#')
    export PGPORT=$(echo "$DATABASE_URL" | sed -E 's#.*:([0-9]+)/.*#\1#')
    export PGUSER=$(echo "$DATABASE_URL" | sed -E 's#postgres://([^:]+):.*@.*#\1#')
    export PGPASSWORD=$(echo "$DATABASE_URL" | sed -E 's#postgres://[^:]+:([^@]+)@.*#\1#')
    export PGDATABASE=$(echo "$DATABASE_URL" | sed -E 's#.*/([^/?]+).*#\1#')
  else
    echo "PGDATABASE or DATABASE_URL must be set" >&2
    exit 2
  fi
fi

OUT_DIR=${1:-/backups}
mkdir -p "$OUT_DIR"
FNAME="${PGDATABASE}_$(date -u +%Y%m%dT%H%M%SZ).sql.gz"

echo "Creating backup to $OUT_DIR/$FNAME"
pg_dump --host="$PGHOST" --port="${PGPORT:-5432}" --username="$PGUSER" --format=plain "$PGDATABASE" | gzip > "$OUT_DIR/$FNAME"
if [ $? -eq 0 ]; then
  echo "Backup succeeded: $OUT_DIR/$FNAME"
else
  echo "Backup failed" >&2
  exit 3
fi

# optional: keep N backups
KEEP=${2:-7}
ls -1t "$OUT_DIR"/*.sql.gz 2>/dev/null | tail -n +$((KEEP+1)) | xargs -r rm -f
echo "Rotated backups, kept $KEEP latest files"
