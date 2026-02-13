#!/usr/bin/env bash
# Phase 1: Build baseline lexicon from raw sources (OEWN + SyntagNet + VerbNet + Familiarity).
#
# Run only when raw data sources update. For normal enrichment, use enrich.sh.
#
# Usage:
#   ./import_raw.sh              Build baseline DB only
#   ./import_raw.sh --dump       Build and export baseline_lexicon.sql
#
# Raw sources required in data-pipeline/raw/:
#   - sqlunet_master.db        SQLunet integrated database
#   - wiki-news-300d-1M.vec    FastText 300d word vectors (not used here, but validated)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIPELINE_DIR="$SCRIPT_DIR"
SCRIPTS_DIR="$PIPELINE_DIR/scripts"
RAW_DIR="$PIPELINE_DIR/raw"
OUTPUT_DIR="$PIPELINE_DIR/output"

DUMP=false
if [[ "${1:-}" == "--dump" ]]; then
    DUMP=true
fi

# --- Validation -----------------------------------------------------------

echo "=== Metaforge: Import Raw Sources ==="
echo ""

errors=0

if [[ ! -f "$RAW_DIR/sqlunet_master.db" ]]; then
    echo "ERROR: Missing $RAW_DIR/sqlunet_master.db"
    errors=1
fi

SCHEMA_FILE="$(cd "$PIPELINE_DIR/.." && pwd)/docs/designs/schema-v2.sql"
if [[ ! -f "$SCHEMA_FILE" ]]; then
    echo "ERROR: Missing schema file: $SCHEMA_FILE"
    errors=1
fi

if [[ $errors -ne 0 ]]; then
    echo ""
    echo "Aborting due to missing prerequisites."
    exit 1
fi

echo "All prerequisites found."
echo ""

# --- Build ----------------------------------------------------------------

step=0
run_step() {
    step=$((step + 1))
    echo "--- Step $step: $1 ---"
    shift
    "$@"
    echo ""
}

DB_PATH="$OUTPUT_DIR/lexicon_v2.db"

run_step "Create empty database with schema" \
    bash -c "rm -f '$DB_PATH' && sqlite3 '$DB_PATH' < '$SCHEMA_FILE'"

run_step "Import OEWN synsets, lemmas, relations" \
    python "$SCRIPTS_DIR/import_oewn.py"

run_step "Import SyntagNet collocations" \
    python "$SCRIPTS_DIR/import_syntagnet.py"

run_step "Import VerbNet classes and roles" \
    python "$SCRIPTS_DIR/import_verbnet.py"

run_step "Import Brysbaert GPT familiarity" \
    python "$SCRIPTS_DIR/import_familiarity.py"

run_step "Backfill SUBTLEX-UK frequency data" \
    python "$SCRIPTS_DIR/import_subtlex.py"

# --- Optional dump --------------------------------------------------------

if [[ "$DUMP" == true ]]; then
    run_step "Export baseline_lexicon.sql" \
        bash -c "sqlite3 '$DB_PATH' .dump > '$OUTPUT_DIR/baseline_lexicon.sql'"
    echo "Baseline dump: $OUTPUT_DIR/baseline_lexicon.sql"
fi

echo "=== Import complete ==="
echo "Database: $DB_PATH"
