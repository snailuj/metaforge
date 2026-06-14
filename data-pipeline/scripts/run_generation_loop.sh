#!/usr/bin/env bash
#
# Autonomous resume loop for the metaphor-edge generation runner.
#
# Runs generate_metaphor_edges repeatedly, sleeping across each 429 session-limit
# window until the topic list is exhausted (or a real stop condition fires).
# This is the turnkey driver for the multi-day 10k run: launch once, walk away.
#
#   nohup data-pipeline/scripts/run_generation_loop.sh \
#       > data-pipeline/output/generation_loop.log 2>&1 &
#
# Each generator invocation is idempotent/resumable (resume-by-topic_synset_id),
# so a kill/restart of THIS wrapper never double-bills or loses work.
#
# Stop conditions (the loop exits):
#   - completed        : topic list exhausted          -> exit 0
#   - cost_cap         : --max-cost-usd reached         -> exit 0 (deliberate)
#   - tripwire         : live-rate collapse             -> exit 3 (needs a look)
#   - session_limit_*  : unrecognised 429 reset format  -> exit 2 (LOUD; server change?)
# A graceful `session_limit` (parseable reset) is NOT a stop — it sleeps then resumes.
# Every pause also pushes an NTFY alert from the generator itself.
set -u

cd "$(dirname "$0")/../.." || exit 1            # repo root
ROOT="$(pwd)"
PY="$ROOT/data-pipeline/.venv/bin/python"
GEN="$ROOT/data-pipeline/scripts/generate_metaphor_edges.py"

# NTFY channel (gitignored token file) — so pause alerts reach you.
if [ -f "$ROOT/data-pipeline/.env.ntfy" ]; then
  set -a; . "$ROOT/data-pipeline/.env.ntfy"; set +a
else
  echo "WARN: data-pipeline/.env.ntfy not found — NTFY pause alerts disabled" >&2
fi

# --- generation parameters (edit for the target run) -------------------------
TOPICS="${TOPICS:-$ROOT/data-pipeline/output/generation_topics_10k.json}"
OUTPUT="${OUTPUT:-$ROOT/data-pipeline/grading/sonnet_chains_provisional_r2_10k.jsonl}"
DB="${DB:-$ROOT/data-pipeline/output/lexicon_v2.db}"
ROUND="${ROUND:-2}"
BATCH_SIZE="${BATCH_SIZE:-20}"
JUDGE_SAMPLE="${JUDGE_SAMPLE:-3}"
MAX_TOPICS="${MAX_TOPICS:-7500}"            # hard deterministic budget cap
MAX_COST_USD="${MAX_COST_USD:-2000}"        # soft spend guard
HAIKU_JSONL="${HAIKU_JSONL:-}"              # set to reuse a stored Haiku dump (else live Haiku)
AVOID_VEHICLES="${AVOID_VEHICLES:-}"        # set to a JSON list of over-used vehicles to soft-discourage
MAX_ITERS="${MAX_ITERS:-400}"              # runaway guard (windows), not the real bound
SLEEP_BUFFER="${SLEEP_BUFFER:-90}"          # seconds added past the stated reset

SUMMARY="$(mktemp)"
trap 'rm -f "$SUMMARY"' EXIT

iter=0
while [ "$iter" -lt "$MAX_ITERS" ]; do
  iter=$((iter + 1))
  echo "=== [loop $iter] $(date -u +%FT%TZ) launching generator ==="

  haiku_arg=()
  [ -n "$HAIKU_JSONL" ] && haiku_arg=(--haiku-jsonl "$HAIKU_JSONL")
  avoid_arg=()
  [ -n "$AVOID_VEHICLES" ] && avoid_arg=(--avoid-vehicles "$AVOID_VEHICLES")

  "$PY" "$GEN" \
    --topics "$TOPICS" --output "$OUTPUT" --db "$DB" \
    --round "$ROUND" --batch-size "$BATCH_SIZE" --judge-sample "$JUDGE_SAMPLE" \
    --max-topics "$MAX_TOPICS" --max-cost-usd "$MAX_COST_USD" \
    --summary-out "$SUMMARY" "${haiku_arg[@]}" "${avoid_arg[@]}"
  rc=$?

  if [ ! -s "$SUMMARY" ]; then
    echo "ERROR: no summary written (generator rc=$rc) — stopping." >&2
    exit "${rc:-1}"
  fi

  reason="$("$PY" -c "import json;print(json.load(open('$SUMMARY')).get('pause_reason') or '')")"
  reset_text="$("$PY" -c "import json;print(json.load(open('$SUMMARY')).get('reset_text') or '')")"

  case "$reason" in
    "")
      echo "=== [loop $iter] completed — topic list exhausted. Done. ==="
      exit 0
      ;;
    cost_cap)
      echo "=== [loop $iter] cost cap reached (--max-cost-usd). Stopping. ==="
      exit 0
      ;;
    tripwire)
      echo "=== [loop $iter] tripwire pause (live-rate collapse). Stopping for a look. ===" >&2
      exit 3
      ;;
    session_limit_unparseable)
      echo "=== [loop $iter] LOUD: 429 with unrecognised reset format (server change?). Stopping. ===" >&2
      exit 2
      ;;
    session_limit)
      secs="$("$PY" -c "
import sys, datetime
sys.path.insert(0, '$ROOT/lib')
from claude_client import parse_reset_time
try:
    h, m = parse_reset_time(sys.argv[1])
except Exception:
    print(-1); raise SystemExit
now = datetime.datetime.now(datetime.timezone.utc)
t = now.replace(hour=h, minute=m, second=0, microsecond=0)
if t <= now:
    t += datetime.timedelta(days=1)
print(int((t - now).total_seconds()))
" "$reset_text")"
      if [ "$secs" -lt 0 ] 2>/dev/null; then
        echo "ERROR: session_limit but reset_text unparseable in wrapper: '$reset_text'. Stopping." >&2
        exit 2
      fi
      secs=$((secs + SLEEP_BUFFER))
      echo "=== [loop $iter] session limit ($reset_text). Sleeping ${secs}s until reset, then resuming. ==="
      sleep "$secs"
      ;;
    *)
      echo "ERROR: unknown pause_reason '$reason'. Stopping." >&2
      exit 1
      ;;
  esac
done

echo "ERROR: hit MAX_ITERS=$MAX_ITERS windows without finishing. Stopping (runaway guard)." >&2
exit 1
