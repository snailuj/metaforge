#!/usr/bin/env bash
# Tests deploy/grading/build-venv.sh in a scratch dir:  deploy/grading/test-build-venv.sh
# Needs network (or a warm uv cache) to fetch the locked wheels.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LOCK_SRC="${HERE}/../../data-pipeline/grading_sidecar/requirements.lock"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
cp "$LOCK_SRC" "${T}/requirements.lock"

FAILS=0
ok()   { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILS=$((FAILS + 1)); }

echo "== builds a venv from the lock"
"${HERE}/build-venv.sh" "$T" >/dev/null 2>&1 && ok "exit 0" || fail "build failed"
"${T}/.venv/bin/python" -c 'import fastapi, uvicorn, starlette' 2>/dev/null && ok "runtime deps import" || fail "runtime deps missing"
grep -q '^home = /usr/bin' "${T}/.venv/pyvenv.cfg" && ok "base python is the system one" \
    || fail "base python is not /usr/bin (a home-dir python is invisible to the sandboxed unit)"

echo "== idempotent, and removes anything not in the lock"
uv pip install --quiet --python "${T}/.venv/bin/python" six >/dev/null 2>&1
"${HERE}/build-venv.sh" "$T" >/dev/null 2>&1 && ok "second run exit 0" || fail "second run failed"
"${T}/.venv/bin/python" -c 'import six' 2>/dev/null && fail "extra package survived" || ok "extra package removed"

echo "== refuses a wheel whose hash is not in the lock"
sed -i -E 's/--hash=sha256:[0-9a-f]{64}/--hash=sha256:'"$(printf '0%.0s' {1..64})"'/' "${T}/requirements.lock"
rm -rf "${T}/.venv"
"${HERE}/build-venv.sh" "$T" >/dev/null 2>&1 && fail "installed despite a bad hash" || ok "bad hash refused"

echo ""
if [ "$FAILS" -eq 0 ]; then echo "All tests passed."; else echo "${FAILS} test(s) failed."; exit 1; fi
