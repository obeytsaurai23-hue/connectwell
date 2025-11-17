#!/usr/bin/env bash
# Restore a gzipped pg_dump file into the target DB
# Usage: pg_restore.sh /path/to/backup.sql.gz
set -euo pipefail
if [ "$#" -lt 1 ]; then
  echo "Usage: $0 /path/to/backup.sql.gz" >&2
  exit 2
fi
BACKUP="$1"
if [ ! -f "$BACKUP" ]; then
  echo "Backup file not found: $BACKUP" >&2
  exit 3
fi

# Environment variables: PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE
if [ -z "${PGDATABASE:-}" ]; then
  echo "PGDATABASE must be set to the target database name" >&2
  exit 2
fi

gunzip -c "$BACKUP" | psql --host="${PGHOST:-localhost}" --port="${PGPORT:-5432}" --username="${PGUSER:-postgres}" --dbname="$PGDATABASE"

if [ $? -eq 0 ]; then
  echo "Restore completed"
else
  echo "Restore failed" >&2
  exit 4
fi
