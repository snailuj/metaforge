#!/usr/bin/env bash
# Restore lexicon_v2.db from the SQL text dump.
# Idempotent: always creates a fresh database from the dump.
#
# Usage: ./restore_db.sh [sql_file] [db_file]
#   Defaults:
#     sql_file = data-pipeline/output/lexicon_v2.sql
#     db_file  = data-pipeline/output/lexicon_v2.db

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

SQL_FILE="${1:-$PROJECT_ROOT/data-pipeline/output/lexicon_v2.sql}"
DB_FILE="${2:-$PROJECT_ROOT/data-pipeline/output/lexicon_v2.db}"

if [ ! -f "$SQL_FILE" ]; then
  echo "Error: SQL dump not found: $SQL_FILE" >&2
  exit 1
fi

echo "Restoring database from: $SQL_FILE"
echo "                     to: $DB_FILE"

# Remove existing db to ensure clean restore
rm -f "$DB_FILE"

sqlite3 "$DB_FILE" < "$SQL_FILE"

echo "Done. Restored $(sqlite3 "$DB_FILE" "SELECT count(*) FROM sqlite_master WHERE type='table';") tables."
