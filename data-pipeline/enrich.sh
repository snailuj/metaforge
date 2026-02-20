#!/usr/bin/env bash
# Phase 2: Enrich a baseline lexicon DB with LLM-extracted properties.
#
# Restores baseline_lexicon.sql → fresh DB, then runs enrichment pipeline.
#
# Usage:
#   # From existing enrichment JSON:
#   ./enrich.sh --db output/lexicon_v2.db --from-json output/enrichment_2000_gemini-flash_20260215.json
#
#   # Full LLM enrichment:
#   ./enrich.sh --db output/lexicon_v2.db --enrich --size 2000 --model haiku \
#               --output output/enrichment_2000_haiku_20260220.json
#
#   # With targeted synset IDs:
#   ./enrich.sh --db output/lexicon_v2.db --enrich --size 500 --synset-ids ids.json \
#               --output output/enrichment_500_haiku_20260220.json

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIPELINE_DIR="$SCRIPT_DIR"
SCRIPTS_DIR="$PIPELINE_DIR/scripts"
RAW_DIR="$PIPELINE_DIR/raw"
OUTPUT_DIR="$PIPELINE_DIR/output"

BASELINE_SQL="$OUTPUT_DIR/baseline_lexicon.sql"
FASTTEXT_VEC="$RAW_DIR/wiki-news-300d-1M.vec"

# --- Parse arguments ------------------------------------------------------

DB_PATH=""
ENRICH=false
FROM_JSON=""
SIZE=2000
BATCH_SIZE=20
MODEL="haiku"
DELAY=1.0
SYNSET_IDS=""
OUTPUT_JSON=""
DUMP_SQL=true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db)       DB_PATH="$2"; shift 2 ;;
        --enrich)   ENRICH=true; shift ;;
        --from-json) FROM_JSON="$2"; shift 2 ;;
        --size)     SIZE="$2"; shift 2 ;;
        --batch-size) BATCH_SIZE="$2"; shift 2 ;;
        --model)    MODEL="$2"; shift 2 ;;
        --delay)    DELAY="$2"; shift 2 ;;
        --synset-ids) SYNSET_IDS="$2"; shift 2 ;;
        --output)   OUTPUT_JSON="$2"; shift 2 ;;
        --no-dump)  DUMP_SQL=false; shift ;;
        *)          echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

if [[ -z "$DB_PATH" ]]; then
    echo "ERROR: --db PATH is required" >&2
    exit 1
fi

if [[ "$ENRICH" == false && -z "$FROM_JSON" ]]; then
    echo "ERROR: specify --enrich or --from-json FILE" >&2
    exit 1
fi

# --- Validation -----------------------------------------------------------

echo "=== Metaforge: Enrichment Pipeline ==="
echo ""

errors=0

if [[ ! -f "$BASELINE_SQL" ]]; then
    echo "ERROR: Missing baseline dump: $BASELINE_SQL"
    errors=1
fi

if [[ ! -f "$FASTTEXT_VEC" ]]; then
    echo "ERROR: Missing FastText vectors: $FASTTEXT_VEC"
    errors=1
fi

if [[ -n "$FROM_JSON" && ! -f "$FROM_JSON" ]]; then
    echo "ERROR: JSON file not found: $FROM_JSON"
    errors=1
fi

if [[ "$ENRICH" == true ]] && ! command -v claude &>/dev/null; then
    echo "ERROR: claude CLI not found on PATH (required for --enrich)"
    errors=1
fi

if [[ $errors -ne 0 ]]; then
    echo ""
    echo "Aborting due to missing prerequisites."
    exit 1
fi

# --- Step 1: Restore baseline into target DB ------------------------------

echo "--- Restoring baseline into $DB_PATH ---"
rm -f "$DB_PATH"
sqlite3 "$DB_PATH" < "$BASELINE_SQL"
echo "  Restored $(sqlite3 "$DB_PATH" "SELECT count(*) FROM synsets;") synsets"
echo ""

# --- Step 2: Enrichment (LLM or pre-computed) -----------------------------

ENRICHMENT_JSON=""

if [[ "$ENRICH" == true ]]; then
    if [[ -z "$OUTPUT_JSON" ]]; then
        echo "ERROR: --output FILE is required with --enrich (e.g. --output enrichment_2000_sonnet_20260220.json)" >&2
        exit 1
    fi
    echo "--- Running LLM enrichment (size=$SIZE, model=$MODEL) ---"
    ENRICHMENT_JSON="$OUTPUT_JSON"

    ENRICH_ARGS=(
        python "$SCRIPTS_DIR/enrich_properties.py"
        --size "$SIZE"
        --batch-size "$BATCH_SIZE"
        --model "$MODEL"
        --delay "$DELAY"
        --output "$ENRICHMENT_JSON"
    )
    if [[ -n "$SYNSET_IDS" ]]; then
        ENRICH_ARGS+=(--synset-ids "$SYNSET_IDS")
    fi

    "${ENRICH_ARGS[@]}"
    echo ""
elif [[ -n "$FROM_JSON" ]]; then
    ENRICHMENT_JSON="$FROM_JSON"
    echo "--- Using existing enrichment: $FROM_JSON ---"
    echo ""
fi

# --- Step 3: Downstream pipeline ------------------------------------------

echo "--- Running downstream enrichment pipeline ---"
python "$SCRIPTS_DIR/enrich_pipeline.py" \
    --db "$DB_PATH" \
    --enrichment "$ENRICHMENT_JSON" \
    --fasttext "$FASTTEXT_VEC"
echo ""

# --- Step 4: Export SQL dump ----------------------------------------------

if [[ "$DUMP_SQL" == true ]]; then
    echo "--- Exporting lexicon_v2.sql ---"
    sqlite3 "$DB_PATH" .dump > "$OUTPUT_DIR/lexicon_v2.sql"
    echo "  Dump: $OUTPUT_DIR/lexicon_v2.sql"
fi

echo ""
echo "=== Enrichment pipeline complete ==="
echo "Database: $DB_PATH"
