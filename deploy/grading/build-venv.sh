#!/usr/bin/env bash
# Builds (or brings back in step) the grading sidecar's own venv from its hashed lock.
#
#   deploy/grading/build-venv.sh [sidecar-dir]
#
# Idempotent: re-running syncs the venv to the lock exactly, so a package that is not
# locked (a dev dependency installed by hand, say) is removed. Every wheel must match
# a hash in requirements.lock. The base interpreter must be the system one: the unit
# hides /home, so a venv linked to a uv- or pyenv-managed python would not start.
set -euo pipefail

SIDECAR_DIR="${1:-$(cd "$(dirname "$0")/../../data-pipeline/grading_sidecar" && pwd)}"
VENV="${SIDECAR_DIR}/.venv"
LOCK="${SIDECAR_DIR}/requirements.lock"
PYTHON=/usr/bin/python3.12
UV="$(command -v uv || echo /home/agent/.local/bin/uv)"

[ -f "$LOCK" ] || { echo "ERROR: ${LOCK} not found" >&2; exit 1; }
[ -x "$PYTHON" ] || { echo "ERROR: ${PYTHON} not found" >&2; exit 1; }

if [ ! -x "${VENV}/bin/python" ]; then
    echo "Creating ${VENV}"
    if [ -x "$UV" ]; then
        "$UV" venv --quiet --python "$PYTHON" --no-managed-python "$VENV"
    else
        "$PYTHON" -m venv "$VENV"
    fi
else
    echo "Reusing ${VENV}"
fi

echo "Syncing ${VENV} to ${LOCK}"
if [ -x "$UV" ]; then
    "$UV" pip sync --quiet --require-hashes --python "${VENV}/bin/python" "$LOCK"
else
    # pip cannot remove unlocked packages, so rebuild from scratch.
    rm -rf "$VENV"
    "$PYTHON" -m venv "$VENV"
    "${VENV}/bin/pip" install --quiet --require-hashes -r "$LOCK"
fi

"${VENV}/bin/python" -c 'import fastapi, uvicorn, starlette'
echo "Venv ready: ${VENV}"
