#!/usr/bin/env bash
# Phase 2: Enrich a baseline lexicon DB with LLM-extracted properties.
#
# Restores PRE_ENRICH.sql → fresh DB, then runs enrichment pipeline.
#
# Usage:
#   # From existing enrichment JSON (one or more files):
#   ./enrich.sh --db output/lexicon_v2.db --from-json output/enrichment_*.json
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

BASELINE_SQL="$OUTPUT_DIR/PRE_ENRICH.sql"
FASTTEXT_VEC="$RAW_DIR/wiki-news-300d-1M.vec"

# --- Parse arguments ------------------------------------------------------

DB_PATH=""
ENRICH=false
FROM_JSON_FILES=()
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
        --from-json)
            shift
            while [[ $# -gt 0 && ! "$1" == --* ]]; do
                FROM_JSON_FILES+=("$1")
                shift
            done
            ;;
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

if [[ "$ENRICH" == false && ${#FROM_JSON_FILES[@]} -eq 0 ]]; then
    echo "ERROR: specify --enrich or --from-json FILE [FILE ...]" >&2
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

for f in "${FROM_JSON_FILES[@]}"; do
    if [[ ! -f "$f" ]]; then
        echo "ERROR: JSON file not found: $f"
        errors=1
    fi
done

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

ENRICHMENT_FILES=()

if [[ "$ENRICH" == true ]]; then
    if [[ -z "$OUTPUT_JSON" ]]; then
        echo "ERROR: --output FILE is required with --enrich (e.g. --output enrichment_2000_sonnet_20260220.json)" >&2
        exit 1
    fi
    echo "--- Running LLM enrichment (size=$SIZE, model=$MODEL) ---"

    ENRICH_ARGS=(
        python "$SCRIPTS_DIR/enrich_properties.py"
        --size "$SIZE"
        --batch-size "$BATCH_SIZE"
        --model "$MODEL"
        --delay "$DELAY"
        --output "$OUTPUT_JSON"
    )
    if [[ -n "$SYNSET_IDS" ]]; then
        ENRICH_ARGS+=(--synset-ids "$SYNSET_IDS")
    fi

    "${ENRICH_ARGS[@]}"
    ENRICHMENT_FILES+=("$OUTPUT_JSON")
    echo ""
elif [[ ${#FROM_JSON_FILES[@]} -gt 0 ]]; then
    ENRICHMENT_FILES=("${FROM_JSON_FILES[@]}")
    echo "--- Using existing enrichment: ${#ENRICHMENT_FILES[@]} file(s) ---"
    for f in "${ENRICHMENT_FILES[@]}"; do
        echo "  $f"
    done
    echo ""
fi

# --- Step 3: Downstream pipeline ------------------------------------------

echo "--- Running downstream enrichment pipeline ---"
python "$SCRIPTS_DIR/enrich_pipeline.py" \
    --db "$DB_PATH" \
    --enrichment "${ENRICHMENT_FILES[@]}" \
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
