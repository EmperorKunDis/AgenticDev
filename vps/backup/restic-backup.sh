#!/usr/bin/env bash
# Denní záloha. Postgres přes pg_dumpall, zbytek jako soubory.
set -euo pipefail

: "${RESTIC_REPOSITORY:?}" "${RESTIC_PASSWORD:?}"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DUMP=/srv/agenticdev/backup/pg-${STAMP}.sql.gz

echo "▸ Dump Postgresu"
docker exec agenticdev-postgres-1 pg_dumpall -U agenticdev | gzip -9 > "$DUMP"

echo "▸ restic backup"
restic backup --tag agenticdev --tag "$STAMP" \
  --exclude '/srv/agenticdev/data/postgres' \
  /srv/agenticdev/data /srv/agenticdev/config "$DUMP"

echo "▸ Retence 7 denních / 4 týdenní / 12 měsíčních"
restic forget --prune --keep-daily 7 --keep-weekly 4 --keep-monthly 12

echo "▸ Namátková kontrola integrity (5 %)"
restic check --read-data-subset=5%

rm -f "$DUMP"
find /srv/agenticdev/backup -name 'pg-*.sql.gz' -mtime +2 -delete
echo "✓ Záloha hotová: $STAMP"
