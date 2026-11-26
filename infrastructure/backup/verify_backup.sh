#!/bin/sh
# Proves a backup is usable: restores it into a scratch database and checks the money tables. Run quarterly AND after changing backup config.
# Usage: verify_backup.sh <dump file>
set -eu
FILE="${1:?dump file}"; SCRATCH="verify_$(date +%s)"
"$(dirname "$0")/restore.sh" "$FILE" "$SCRATCH"
trap 'dropdb "$SCRATCH"' EXIT
q() { psql -d "$SCRATCH" -tAc "$1"; }
echo "users=$(q 'select count(*) from users') ledger_rows=$(q 'select count(*) from credit_transactions') orders=$(q 'select count(*) from payment_orders')"
# Ledger integrity: no bucket may be negative, and the append-only trigger must have survived the restore.
NEG=$(q "select count(*) from (select bucket_id from credit_transactions group by bucket_id having sum(amount) < 0) x")
[ "$NEG" = "0" ] || { echo "FAIL: $NEG negative buckets" >&2; exit 1; }
TRG=$(q "select count(*) from pg_trigger where tgname in ('credit_ledger_no_update','credit_ledger_no_overdraft','audit_logs_no_change')")
[ "$TRG" = "3" ] || { echo "FAIL: ledger/audit triggers missing after restore ($TRG/3)" >&2; exit 1; }
echo "BACKUP VERIFIED"
