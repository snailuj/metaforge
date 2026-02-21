#!/usr/bin/env bash
# Build the Metaforge lexicon database from raw linguistic sources.
#
# Creates lexicon_v2.db from SCHEMA.sql, imports OEWN + SyntagNet + VerbNet +
# Brysbaert familiarity + SUBTLEX-UK frequencies, then builds curated vocabulary
# and antonym pairs.
#
# Run only when raw data sources update or you need to recreate from scratch.
# For normal enrichment lifecycle, use the pipeline management skill.
#
# Usage:
#   ./import_raw.sh              Build baseline DB only
#   ./import_raw.sh --dump       Build and export PRE_ENRICH.sql
#
# Raw sources required:
#   data-pipeline/raw/sqlunet_master.db          SQLunet integrated database
#   data-pipeline/input/multilex-en/*.xlsx       Brysbaert GPT familiarity
#   data-pipeline/input/subtlex-uk/*.xlsx        SUBTLEX-UK frequencies
#
# See also:
#   data-pipeline/CLAUDE.md                      Pipeline overview
#   data-pipeline/SCHEMA.sql                     Canonical DDL
#   .claude/skills/metaforge-pipeline-creation/   Detailed build guide

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIPELINE_DIR="$SCRIPT_DIR"
SCRIPTS_DIR="$PIPELINE_DIR/scripts"
RAW_DIR="$PIPELINE_DIR/raw"
OUTPUT_DIR="$PIPELINE_DIR/output"
SCHEMA_FILE="$PIPELINE_DIR/SCHEMA.sql"

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

run_step "Create empty database from SCHEMA.sql" \
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

run_step "Build curated vocabulary (35k entries)" \
    python "$SCRIPTS_DIR/build_vocab.py" --db "$DB_PATH"

run_step "Build antonym pairs from WordNet relations" \
    python "$SCRIPTS_DIR/build_antonyms.py" --db "$DB_PATH"

# --- Verification ---------------------------------------------------------

echo "--- Verification ---"
sqlite3 "$DB_PATH" <<'SQL'
SELECT 'synsets' AS tbl, COUNT(*) FROM synsets
UNION ALL SELECT 'lemmas', COUNT(*) FROM lemmas
UNION ALL SELECT 'relations', COUNT(*) FROM relations
UNION ALL SELECT 'frequencies', COUNT(*) FROM frequencies
UNION ALL SELECT 'syntagms', COUNT(*) FROM syntagms
UNION ALL SELECT 'vn_classes', COUNT(*) FROM vn_classes
UNION ALL SELECT 'property_vocab_curated', COUNT(*) FROM property_vocab_curated
UNION ALL SELECT 'property_antonyms', COUNT(*) FROM property_antonyms
UNION ALL SELECT 'enrichment', COUNT(*) FROM enrichment
UNION ALL SELECT 'property_vocabulary', COUNT(*) FROM property_vocabulary
UNION ALL SELECT 'synset_properties', COUNT(*) FROM synset_properties;
SQL
echo ""

# --- Optional dump --------------------------------------------------------

if [[ "$DUMP" == true ]]; then
    run_step "Export PRE_ENRICH.sql" \
        bash -c "sqlite3 '$DB_PATH' .dump > '$OUTPUT_DIR/PRE_ENRICH.sql'"
    echo "Baseline dump: $OUTPUT_DIR/PRE_ENRICH.sql"
fi

echo "=== Import complete ==="
echo "Database: $DB_PATH"
