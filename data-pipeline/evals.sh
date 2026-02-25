#!/usr/bin/env bash
# Concreteness regression: model shootout, gap-fill, and revert.
#
# Thin wrapper around predict_concreteness.py that activates the venv
# and provides default paths. Delegates all argument parsing to argparse.
#
# Run ./evals.sh --help for usage, or ./evals.sh <command> --help for
# subcommand help.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$SCRIPT_DIR/scripts"

# --- Usage -------------------------------------------------------------------

usage() {
    cat >&2 <<'USAGE'
Usage: evals.sh <command> [options]

Commands:
  shootout       Train and evaluate 4 regression models (no DB writes)
  fill           Fill concreteness gaps using the shootout winner
  revert         Delete regression predictions, restore Brysbaert-only state

Common options:
  --db PATH          Target lexicon database    (default: output/lexicon_v2.db)
  --fasttext PATH    FastText .vec file         (default: raw/wiki-news-300d-1M.vec)
  --verbose, -v      Enable debug logging
  --help, -h         Show this message

Shootout options:
  --output, -o FILE  Path for results JSON      (required)

Fill options:
  --shootout FILE    Path to shootout JSON       (required)

Examples:
  # Evaluate models (pure, no DB writes):
  ./evals.sh shootout -o output/concreteness_shootout.json

  # Fill gaps with the winner:
  ./evals.sh fill --shootout output/concreteness_shootout.json

  # Revert to Brysbaert-only:
  ./evals.sh revert

  # Full cycle:
  ./evals.sh shootout -o output/concreteness_shootout.json
  ./evals.sh fill --shootout output/concreteness_shootout.json
USAGE
    exit 1
}

# --- Activate venv -----------------------------------------------------------

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
    VENV_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/.venv"
    if [[ -f "$VENV_DIR/bin/activate" ]]; then
        # shellcheck disable=SC1091
        source "$VENV_DIR/bin/activate"
    else
        echo "ERROR: Python venv not found at $VENV_DIR" >&2
        echo "  Run: python3 -m venv .venv && pip install -r data-pipeline/requirements.txt" >&2
        exit 1
    fi
fi

# --- Route command -----------------------------------------------------------

if [[ $# -eq 0 ]]; then
    usage
fi

case "$1" in
    shootout|fill|revert) ;;
    --help|-h) usage ;;
    *) echo "Unknown command: $1" >&2; echo >&2; usage ;;
esac

# Delegate to Python — argparse handles all argument parsing and --help
exec python -u "$SCRIPTS_DIR/predict_concreteness.py" "$@"
