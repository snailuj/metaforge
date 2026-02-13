#!/usr/bin/env bash
# Crash-recovery wrapper for evolutionary prompt optimisation.
# Runs explore then exploit phases, restarting on crash with --resume.
#
# Usage: ./evolve_trials.sh --model sonnet --size 700 --port 9091
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EVOLVE="$SCRIPT_DIR/scripts/evolve_prompts.py"
ARGS=("$@")
MAX_RETRIES=50
RETRY_DELAY=30

for PHASE in explore exploit; do
    echo "=== $PHASE phase ==="
    attempt=0
    while true; do
        attempt=$((attempt + 1))
        echo "  Attempt $attempt..."
        python -u "$EVOLVE" --phase "$PHASE" --resume "${ARGS[@]}"
        rc=$?
        [[ $rc -eq 0 ]] && break
        echo "  Crashed (exit $rc, attempt $attempt). Retrying in ${RETRY_DELAY}s..."
        [[ $attempt -ge $MAX_RETRIES ]] && { echo "  Max retries ($MAX_RETRIES) reached for $PHASE. Aborting."; exit 1; }
        sleep $RETRY_DELAY
    done
done
echo "=== All phases complete ==="
