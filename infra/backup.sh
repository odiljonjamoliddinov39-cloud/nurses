#!/usr/bin/env bash
# Daily PostgreSQL backup; schedule with cron on the VPS. Keeps the last $KEEP_DAYS days.
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEEP_DAYS="${KEEP_DAYS:-14}"
mkdir -p "$ROOT/backups"
OUT="$ROOT/backups/nurses-$(date +%F).sql.gz"
docker compose -f "$ROOT/infra/docker-compose.yml" exec -T postgres pg_dump -U nurses nurses | gzip > "$OUT.tmp"
mv "$OUT.tmp" "$OUT"
find "$ROOT/backups" -name 'nurses-*.sql.gz' -mtime "+$KEEP_DAYS" -delete
