#!/usr/bin/env bash
#
# Resumable gloss-backfill across all corpus cohorts. Runs the per-topic driver
# over each cohort file; the driver is idempotent (skips topics already in its
# output), so a kill/restart never loses or repeats work. On a full pass that
# makes no progress (a session-limit window), sleeps then retries.
#
#   nohup data-pipeline/scripts/run_gloss_backfill_loop.sh \
#       > data-pipeline/output/gloss_backfill_loop.log 2>&1 &
#
# Originals are never touched: outputs are NEW *_glossed.jsonl files.
set -u

cd "$(dirname "$0")/../.." || exit 1            # repo root
ROOT="$(pwd)"
PY="$ROOT/data-pipeline/.venv/bin/python"
GB="$ROOT/data-pipeline/scripts/gloss_backfill.py"
DB="$ROOT/data-pipeline/output/lexicon_v2.db"

if [ -f "$ROOT/data-pipeline/.env.ntfy" ]; then set -a; . "$ROOT/data-pipeline/.env.ntfy"; set +a; fi

G="$ROOT/data-pipeline/grading"
O="$ROOT/data-pipeline/output"
PAIRS=(
  "$G/chain-topics_spike_r1.jsonl:$O/chain-topics_spike_r1_glossed.jsonl"
  "$G/chain-topics_spike_r2.jsonl:$O/chain-topics_spike_r2_glossed.jsonl"
  "$G/chain-topics_curated.jsonl:$O/chain-topics_curated_glossed.jsonl"
  "$G/stock/chain-topics_stock.jsonl:$O/stock/chain-topics_stock_glossed.jsonl"
)
mkdir -p "$O/stock"

pending_total() {
  "$PY" - "$@" <<'PY'
import json, sys
def topics(path):
    s=set()
    try:
        for l in open(path):
            l=l.strip()
            if l:
                try: t=json.loads(l).get("topic_synset_id")
                except: continue
                if t: s.add(str(t))
    except FileNotFoundError: pass
    return s
total=0
for pair in sys.argv[1:]:
    inp,out=pair.split(":",1)
    total+=len(topics(inp)-topics(out))
print(total)
PY
}

for iter in $(seq 1 60); do
  echo "=== [pass $iter] $(date -u +%FT%TZ) ==="
  before=$(pending_total "${PAIRS[@]}")
  for pair in "${PAIRS[@]}"; do
    IN="${pair%%:*}"; OUT="${pair##*:}"
    echo "--- $(basename "$IN") ---"
    "$PY" "$GB" --in "$IN" --out "$OUT" --db "$DB" --model sonnet
  done
  after=$(pending_total "${PAIRS[@]}")
  echo "=== [pass $iter] pending: $before -> $after ==="
  [ "$after" -eq 0 ] && { echo "ALL COHORTS DONE."; exit 0; }
  if [ "$after" -ge "$before" ]; then
    echo "no progress (session limit?) — sleeping 1800s then retrying"
    sleep 1800
  fi
done
echo "hit max passes without finishing (runaway guard)."; exit 1
