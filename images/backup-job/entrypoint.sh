#!/bin/sh
set -e

# Minimal backup entrypoint. Expects the following env vars:
# POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_DB
# AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET, S3_REGION

: "${POSTGRES_HOST:?POSTGRES_HOST required}"
: "${POSTGRES_PORT:=5432}"
: "${POSTGRES_USER:?POSTGRES_USER required}"
: "${POSTGRES_DB:?POSTGRES_DB required}"

TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
BACKUP_FILE="/backup/connectwell-db-${TIMESTAMP}.sql.gz"

echo "Running pg_dump against ${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB} as ${POSTGRES_USER}"
# Use PGPASSWORD if provided (in k8s you'd mount a secret to POSTGRES_PASSWORD env var)
if [ -n "${POSTGRES_PASSWORD}" ]; then
  export PGPASSWORD=${POSTGRES_PASSWORD}
fi

pg_dump --host=${POSTGRES_HOST} --port=${POSTGRES_PORT} --username=${POSTGRES_USER} ${POSTGRES_DB} | gzip > ${BACKUP_FILE}

if [ -n "${S3_BUCKET}" ]; then
  echo "Uploading ${BACKUP_FILE} to s3://${S3_BUCKET}/"
  aws configure set aws_access_key_id "${AWS_ACCESS_KEY_ID}"
  aws configure set aws_secret_access_key "${AWS_SECRET_ACCESS_KEY}"
  aws configure set default.region "${S3_REGION}"
  aws s3 cp ${BACKUP_FILE} s3://${S3_BUCKET}/
else
  echo "S3_BUCKET not set — backup file is ${BACKUP_FILE}"
fi

# Clean up
rm -f ${BACKUP_FILE}

echo "Backup completed"
