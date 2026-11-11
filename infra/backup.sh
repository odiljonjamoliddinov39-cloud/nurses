#!/bin/sh
# Daily PostgreSQL backup; schedule with cron on the VPS.
set -eu
mkdir -p backups
docker compose -f infra/docker-compose.yml exec -T postgres pg_dump -U nurses nurses | gzip > "backups/nurses-$(date +%F).sql.gz"
