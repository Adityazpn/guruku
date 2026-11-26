#!/bin/sh
# Compressed pg_dump, optionally AES-256 encrypted, pruned by age, optionally copied to S3. Requires PGHOST/PGUSER/PGPASSWORD/PGDATABASE.
set -eu
DIR="${BACKUP_DIR:-/backups}"; KEEP="${BACKUP_KEEP_DAYS:-14}"
mkdir -p "$DIR"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$DIR/guruku-$STAMP.dump"
pg_dump --format=custom --no-owner --file="$OUT.tmp"
if [ -n "${BACKUP_PASSPHRASE:-}" ]; then
  openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE -in "$OUT.tmp" -out "$OUT.enc"
  rm -f "$OUT.tmp"; OUT="$OUT.enc"
else
  mv "$OUT.tmp" "$OUT"
fi
[ -s "$OUT" ] || { echo "backup is empty" >&2; exit 1; }
echo "backup ok: $OUT ($(wc -c < "$OUT") bytes)"
find "$DIR" -name 'guruku-*' -mtime +"$KEEP" -delete
if [ -n "${BACKUP_S3_URI:-}" ]; then
  command -v aws >/dev/null && aws s3 cp "$OUT" "$BACKUP_S3_URI/" || echo "WARNING: BACKUP_S3_URI set but aws cli not available; off-site copy skipped" >&2
fi
