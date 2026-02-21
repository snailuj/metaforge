#!/usr/bin/env bash
# Export enriched lexicon DB as SQL text dump.
#
# Usage:
#   ./export.sh --db output/lexicon_v2.db
#
# Output: output/lexicon_v2.sql (overwritten)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/output"

# --- Parse arguments ---------------------------------------------------------
DB_PATH=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --db) DB_PATH="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$DB_PATH" ]]; then
  echo "Usage: $0 --db PATH" >&2
  exit 1
fi

if [[ ! -f "$DB_PATH" ]]; then
  echo "Error: DB not found: $DB_PATH" >&2
  exit 1
fi

# --- Validate expected tables ------------------------------------------------
REQUIRED_TABLES="synsets lemmas enrichment property_vocabulary synset_properties"
for table in $REQUIRED_TABLES; do
  count=$(sqlite3 -list -noheader "$DB_PATH" "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='$table'")
  if [[ "$count" -eq 0 ]]; then
    echo "Error: missing required table '$table' in $DB_PATH" >&2
    exit 1
  fi
done

# --- Compact and dump --------------------------------------------------------
echo "VACUUMing $DB_PATH..."
sqlite3 "$DB_PATH" "VACUUM;"

SQL_FILE="$OUTPUT_DIR/lexicon_v2.sql"
echo "Dumping to $SQL_FILE..."
sqlite3 "$DB_PATH" .dump > "$SQL_FILE"

# --- Summary -----------------------------------------------------------------
echo ""
echo "=== Export Summary ==="
echo "Source: $DB_PATH"
echo "Output: $SQL_FILE"
echo ""
for table in synsets enrichment property_vocab_curated synset_properties_curated property_vocabulary synset_properties; do
  count=$(sqlite3 -list -noheader "$DB_PATH" "SELECT count(*) FROM $table" 2>/dev/null || echo "N/A")
  printf "  %-30s %s\n" "$table" "$count"
done
echo ""
echo "Done."
