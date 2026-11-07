#!/usr/bin/env bash
# Backup: database dump + data folder (inbox, feeds, secrets key) into BACKUP_DIR, keeping the newest KEEP backups.
# Usage: DATABASE_URL=postgresql://... DATA_DIR=./data BACKUP_DIR=./backups KEEP=14 scripts/backup.sh
# Restore: createdb vmo_restore; pg_restore -d vmo_restore backups/<stamp>/db.dump; tar -xzf backups/<stamp>/data.tar.gz -C <target>
set -euo pipefail
: "${DATABASE_URL:?set DATABASE_URL (postgresql://user:pass@host/db)}"
DATA_DIR="${DATA_DIR:-./data}"; BACKUP_DIR="${BACKUP_DIR:-./backups}"; KEEP="${KEEP:-14}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"; out="$BACKUP_DIR/$stamp"; mkdir -p "$out"
pg_dump --format=custom --file "$out/db.dump" "${DATABASE_URL/postgresql+psycopg/postgresql}"
tar -czf "$out/data.tar.gz" -C "$(dirname "$DATA_DIR")" "$(basename "$DATA_DIR")"
(cd "$out" && sha256sum db.dump data.tar.gz > SHA256SUMS)
ls -1dt "$BACKUP_DIR"/*/ | tail -n +"$((KEEP + 1))" | xargs -r rm -rf
echo "backup written to $out"
