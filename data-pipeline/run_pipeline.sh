#!/usr/bin/env bash
# Metaforge data pipeline runner.
#
# Regenerates lexicon_v2.db from raw sources and exports a SQL dump.
#
# Usage:
#   ./run_pipeline.sh          Rebuild using pre-computed LLM output
#   ./run_pipeline.sh --full   Rebuild everything (runs LLM extraction — costs API calls)
#   ./run_pipeline.sh --check  Validate prerequisites only (no execution)
#
# Raw sources required in data-pipeline/raw/:
#   - sqlunet_master.db        SQLunet integrated database
#   - wiki-news-300d-1M.vec    FastText 300d word vectors
#
# Pre-computed output (skipped with --full):
#   - data-pipeline/output/property_pilot_2k.json   LLM-extracted properties

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIPELINE_DIR="$SCRIPT_DIR"
SCRIPTS_DIR="$PIPELINE_DIR/scripts"
RAW_DIR="$PIPELINE_DIR/raw"
OUTPUT_DIR="$PIPELINE_DIR/output"

FULL=false
CHECK=false
if [[ "${1:-}" == "--full" ]]; then
    FULL=true
elif [[ "${1:-}" == "--check" ]]; then
    CHECK=true
fi

# --- Validation -----------------------------------------------------------

echo "=== Metaforge Data Pipeline ==="
echo ""

errors=0

if [[ ! -f "$RAW_DIR/sqlunet_master.db" ]]; then
    echo "ERROR: Missing $RAW_DIR/sqlunet_master.db"
    errors=1
fi

if [[ ! -f "$RAW_DIR/wiki-news-300d-1M.vec" ]]; then
    echo "ERROR: Missing $RAW_DIR/wiki-news-300d-1M.vec"
    errors=1
fi

if [[ "$FULL" == false && "$CHECK" == false && ! -f "$OUTPUT_DIR/property_pilot_2k.json" ]]; then
    echo "ERROR: Missing $OUTPUT_DIR/property_pilot_2k.json"
    echo "       Run with --full to regenerate via LLM, or restore from backup."
    errors=1
fi

SCHEMA_CHECK="$(cd "$PIPELINE_DIR/.." && pwd)/docs/designs/schema-v2.sql"
if [[ ! -f "$SCHEMA_CHECK" ]]; then
    echo "ERROR: Missing schema file: $SCHEMA_CHECK"
    errors=1
fi

if [[ "$FULL" == true && -z "${GEMINI_API_KEY:-}" ]]; then
    echo "ERROR: GEMINI_API_KEY not set (required for --full)"
    errors=1
fi

if [[ $errors -ne 0 ]]; then
    echo ""
    echo "Aborting due to missing prerequisites."
    exit 1
fi

if [[ "$CHECK" == true ]]; then
    echo "All prerequisites found. Ready to run."
    exit 0
elif [[ "$FULL" == true ]]; then
    echo "MODE: Full rebuild (including LLM extraction)"
    read -rp "This will consume Gemini API calls. Continue? [y/N] " confirm
    if [[ "${confirm,,}" != "y" ]]; then
        echo "Aborted."
        exit 0
    fi
else
    echo "MODE: Rebuild using pre-computed LLM output"
fi

echo ""

# --- Helper ----------------------------------------------------------------

step=0
run_step() {
    step=$((step + 1))
    echo "--- Step $step: $1 ---"
    shift
    "$@"
    echo ""
}

# NOTE: SUBTLEX-UK frequency import is pending (needs re-downloading).
# The 'frequencies' table exists in the schema but is not populated.
# See PRD-2 open questions and schema-v2.sql for context.

# --- Phase 1: Schema from raw sources -------------------------------------

SCHEMA_FILE="$(cd "$PIPELINE_DIR/.." && pwd)/docs/designs/schema-v2.sql"

run_step "Create empty database with schema" \
    bash -c "rm -f '$OUTPUT_DIR/lexicon_v2.db' && sqlite3 '$OUTPUT_DIR/lexicon_v2.db' < '$SCHEMA_FILE'"

run_step "Import OEWN synsets, lemmas, relations" \
    python "$SCRIPTS_DIR/import_oewn.py"

run_step "Import SyntagNet collocations" \
    python "$SCRIPTS_DIR/import_syntagnet.py"

run_step "Import VerbNet classes and roles" \
    python "$SCRIPTS_DIR/import_verbnet.py"

# --- Phase 2: Property enrichment -----------------------------------------

if [[ "$FULL" == true ]]; then
    run_step "Extract properties via LLM (Gemini)" \
        python "$SCRIPTS_DIR/spike_property_vocab.py" --pilot-size 2000 --batch-size 20
fi

run_step "Curate properties and add FastText embeddings" \
    python "$SCRIPTS_DIR/curate_properties.py"

run_step "Populate synset-property junction table" \
    python "$SCRIPTS_DIR/populate_synset_properties.py"

# --- Phase 3: Compute metrics ---------------------------------------------

run_step "Compute property IDF weights" \
    python "$SCRIPTS_DIR/06_compute_property_idf.py"

run_step "Compute pairwise property similarity" \
    python "$SCRIPTS_DIR/07_compute_property_similarity.py" --threshold 0.5

run_step "Compute synset centroids" \
    python "$SCRIPTS_DIR/08_compute_synset_centroids.py"

# --- Export SQL dump -------------------------------------------------------

run_step "Export SQL dump for version control" \
    bash -c "sqlite3 '$OUTPUT_DIR/lexicon_v2.db' .dump > '$OUTPUT_DIR/lexicon_v2.sql'"

echo "=== Pipeline complete ==="
echo "Database: $OUTPUT_DIR/lexicon_v2.db"
echo "SQL dump: $OUTPUT_DIR/lexicon_v2.sql"
