#!/usr/bin/env bash
# Phase 2: Enrich a baseline lexicon DB with LLM-extracted properties.
#
# Restores PRE_ENRICH.sql → fresh DB, then runs enrichment pipeline.
#
# Run ./enrich.sh --help for full usage.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIPELINE_DIR="$SCRIPT_DIR"
SCRIPTS_DIR="$PIPELINE_DIR/scripts"
RAW_DIR="$PIPELINE_DIR/raw"
OUTPUT_DIR="$PIPELINE_DIR/output"

BASELINE_SQL="$OUTPUT_DIR/PRE_ENRICH.sql"
FASTTEXT_VEC="$RAW_DIR/wiki-news-300d-1M.vec"

# --- Usage ----------------------------------------------------------------

usage() {
    cat >&2 <<'USAGE'
Usage: enrich.sh --db PATH (--enrich [opts] | --from-json FILE [FILE ...])

Modes (mutually exclusive):
  --enrich              Run LLM enrichment (requires claude CLI on PATH)
  --from-json F [F ...] Import one or more pre-computed enrichment JSONs

Required:
  --db PATH             Target lexicon database

Enrichment options (--enrich only):
  --output FILE         Output JSON path (required with --enrich)
  --size N              Number of synsets to enrich  (default: 2000)
  --batch-size N        Synsets per LLM batch        (default: 20)
  --model NAME          Claude model alias           (default: haiku)
  --delay SECS          Seconds between batches      (default: 1.0)
  --strategy STR        Selection strategy: random|frequency (default: random)
  --schema-version VER  v1 (plain) or v2 (structured)       (default: v1)
  --synset-ids FILE     JSON array of specific synset IDs
  --offset N            Skip top N synsets (frequency strategy only, default: 0)
  --resume              Resume from checkpoint
  --verbose             Enable debug logging

General:
  --no-dump             Skip exporting lexicon_v2.sql after pipeline
  --help                Show this message

Examples:
  # Import existing JSON:
  ./enrich.sh --db output/lexicon_v2.db --from-json output/enrichment_*.json

  # Full LLM enrichment:
  ./enrich.sh --db output/lexicon_v2.db --enrich --size 2000 --model sonnet \
              --output output/enrichment_2000_sonnet_20260223.json

  # Resume interrupted enrichment:
  ./enrich.sh --db output/lexicon_v2.db --enrich --resume --model sonnet \
              --output output/enrichment_2000_sonnet_20260223.json
USAGE
    exit 1
}

# --- Parse arguments ------------------------------------------------------

DB_PATH=""
ENRICH=false
FROM_JSON_FILES=()
SIZE=2000
BATCH_SIZE=20
MODEL="haiku"
DELAY=1.0
STRATEGY="random"
SCHEMA_VERSION="v1"
SYNSET_IDS=""
OFFSET=0
OUTPUT_JSON=""
RESUME=false
VERBOSE=false
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
        --size)       SIZE="$2"; shift 2 ;;
        --batch-size) BATCH_SIZE="$2"; shift 2 ;;
        --model)      MODEL="$2"; shift 2 ;;
        --delay)      DELAY="$2"; shift 2 ;;
        --strategy)   STRATEGY="$2"; shift 2 ;;
        --schema-version) SCHEMA_VERSION="$2"; shift 2 ;;
        --synset-ids) SYNSET_IDS="$2"; shift 2 ;;
        --offset)     OFFSET="$2"; shift 2 ;;
        --output)     OUTPUT_JSON="$2"; shift 2 ;;
        --resume|-r)  RESUME=true; shift ;;
        --verbose|-v) VERBOSE=true; shift ;;
        --no-dump)    DUMP_SQL=false; shift ;;
        --help|-h)    usage ;;
        *)            echo "Unknown option: $1" >&2; echo >&2; usage ;;
    esac
done

if [[ -z "$DB_PATH" ]]; then
    echo "ERROR: --db PATH is required" >&2
    echo >&2
    usage
fi

if [[ "$ENRICH" == false && ${#FROM_JSON_FILES[@]} -eq 0 ]]; then
    echo "ERROR: specify --enrich or --from-json FILE [FILE ...]" >&2
    echo >&2
    usage
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
        python -u "$SCRIPTS_DIR/enrich_properties.py"
        --size "$SIZE"
        --batch-size "$BATCH_SIZE"
        --model "$MODEL"
        --delay "$DELAY"
        --strategy "$STRATEGY"
        --schema-version "$SCHEMA_VERSION"
        --output "$OUTPUT_JSON"
    )
    if [[ -n "$SYNSET_IDS" ]]; then
        ENRICH_ARGS+=(--synset-ids "$SYNSET_IDS")
    fi
    if [[ "$OFFSET" -gt 0 ]]; then
        ENRICH_ARGS+=(--offset "$OFFSET")
    fi
    if [[ "$RESUME" == true ]]; then
        ENRICH_ARGS+=(--resume)
    fi
    if [[ "$VERBOSE" == true ]]; then
        ENRICH_ARGS+=(--verbose)
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
python -u "$SCRIPTS_DIR/enrich_pipeline.py" \
    --db "$DB_PATH" \
    --enrichment "${ENRICHMENT_FILES[@]}" \
    --fasttext "$FASTTEXT_VEC"
echo ""

# --- Step 4: Concreteness fill --------------------------------------------

SHOOTOUT_JSON="$OUTPUT_DIR/concreteness_shootout.json"

if [[ -f "$SHOOTOUT_JSON" ]]; then
    echo "--- Filling concreteness gaps (k-NN regression) ---"
    python -u "$SCRIPTS_DIR/predict_concreteness.py" fill \
        --db "$DB_PATH" \
        --fasttext "$FASTTEXT_VEC" \
        --shootout "$SHOOTOUT_JSON"
    echo ""
else
    echo "--- Skipping concreteness fill (no shootout JSON at $SHOOTOUT_JSON) ---"
    echo "  Run: ./evals.sh shootout -o $SHOOTOUT_JSON"
    echo ""
fi

# --- Step 5: Export SQL dump ----------------------------------------------

if [[ "$DUMP_SQL" == true ]]; then
    echo "--- Exporting lexicon_v2.sql ---"
    sqlite3 "$DB_PATH" .dump > "$OUTPUT_DIR/lexicon_v2.sql"
    echo "  Dump: $OUTPUT_DIR/lexicon_v2.sql"
fi

echo ""
echo "=== Enrichment pipeline complete ==="
echo "Database: $DB_PATH"
