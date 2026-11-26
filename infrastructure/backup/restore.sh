#!/bin/sh
# Restore a dump INTO A DATABASE YOU NAME (never the live one by accident).
# Usage: restore.sh <dump file> <target database name>      (target is created; refuses if it already exists)
set -eu
FILE="${1:?dump file}"; TARGET="${2:?target database}"
TMP=$(mktemp); trap 'rm -f "$TMP"' EXIT
case "$FILE" in
  *.enc) openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_PASSPHRASE -in "$FILE" -out "$TMP" ;;
  *)     cp "$FILE" "$TMP" ;;
esac
if psql -d postgres -tAc "select 1 from pg_database where datname='$TARGET'" | grep -q 1; then echo "database $TARGET already exists; refusing" >&2; exit 1; fi
createdb "$TARGET"
pg_restore --no-owner --dbname="$TARGET" "$TMP"
echo "restored into $TARGET"
