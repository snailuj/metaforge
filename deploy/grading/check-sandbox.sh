#!/usr/bin/env bash
# Checks the grading sidecar unit confines the process to its code (read-only) and
# its data clone, and that it can still do its job.
#
#   deploy/grading/check-sandbox.sh [--static-only] [--unit FILE] [--main-git DIR]
#
# Static: required directives are present. Probe (needs sudo): a transient unit
# mf-sandbox-test-grading gets the unit's sandbox properties, with the code path
# re-pointed at THIS checkout (bound read-only, venv included) and the data path at
# a scratch clone of the grading-data branch in /var/lib/mf-sandbox-test. It then
# runs sandbox_probe.py: create_app(), append a data line, autocommit_once (a commit
# must appear), and assert it cannot write to the code, to the main repo's .git or
# see ~/.ssh. The live sidecar's port is never bound.
#
# --unit tests a different unit file (e.g. an old revision, to see the probes fail).
# --main-git is the directory probed as "the main repo's .git"; it defaults to the
# real one, so pass a stand-in when testing an old unit that would be able to write.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "${HERE}/../.." && pwd)"
# shellcheck source=../lib/sandbox-props.sh
. "${HERE}/../lib/sandbox-props.sh"

STATIC_ONLY=0 UNIT="${HERE}/metaforge-grading.service" MAIN_GIT=/home/agent/projects/metaforge/.git
while [ $# -gt 0 ]; do
    case "$1" in
        --static-only) STATIC_ONLY=1 ;;
        --unit) UNIT="$2"; shift ;;
        --main-git) MAIN_GIT="$2"; shift ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
    shift
done

LIVE_CODE=/home/agent/projects/metaforge/.worktrees/next
LIVE_CLONE=/home/agent/projects/metaforge-grading-data
OLD_CLONE=/home/agent/projects/metaforge/.worktrees/grading-data
SCRATCH=/var/lib/mf-sandbox-test
CLONE="${SCRATCH}/grading-data"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; sudo rm -rf "$SCRATCH" 2>/dev/null || true; }
trap cleanup EXIT

FAILS=0
ok()   { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILS=$((FAILS + 1)); }

props="${TMP}/props"
sandbox_props "$UNIT" > "$props"
unit_env "$UNIT" > "${TMP}/env"

echo "== static"
v="$(systemd-analyze verify "$UNIT" 2>&1 | grep -F "$(basename "$UNIT")" | grep -v 'is not executable' || true)"
if [ -z "$v" ]; then ok "systemd-analyze verify clean"; else fail "verify: $v"; fi
REQUIRED=(
    "User=metaforge-grading" "Group=metaforge-grading"
    "LoadCredential=grading_secret:/etc/metaforge/grading_secret"
    "NoNewPrivileges=true" "ProtectSystem=strict" "ProtectHome=tmpfs"
    "BindReadOnlyPaths=${LIVE_CODE}" "BindPaths=${LIVE_CLONE}" "ReadWritePaths=${LIVE_CLONE}"
    "PrivateTmp=true" "PrivateDevices=true" "CapabilityBoundingSet=" "AmbientCapabilities="
    "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX"
    "ProtectKernelTunables=true" "ProtectKernelModules=true" "ProtectKernelLogs=true"
    "ProtectControlGroups=true" "ProtectClock=true" "ProtectHostname=true"
    "RestrictNamespaces=true" "RestrictSUIDSGID=true" "RestrictRealtime=true"
    "LockPersonality=true" "SystemCallArchitectures=native" "SystemCallFilter=@system-service"
    "UMask=0027"
)
for want in "${REQUIRED[@]}"; do
    if grep -qxF "$want" "$props"; then ok "has ${want}"; else fail "missing ${want}"; fi
done
for want in "GRADING_SECRET_FILE=%d/grading_secret" "GRADING_DATA_DIR=${LIVE_CLONE}/data-pipeline/grading" "GRADING_DATA_GIT_ROOT=${LIVE_CLONE}"; do
    if grep -qxF "$want" "${TMP}/env"; then ok "env ${want}"; else fail "env missing ${want}"; fi
done
if grep -qE '^ReadWritePaths=/home/agent/projects/metaforge( |$)' "$props"; then fail "whole repo is writable"; fi
if grep -q '^ExecStart=.*/grading_sidecar/.venv/bin/python -m grading_sidecar.main' "$UNIT"; then
    ok "runs from the sidecar's own venv"; else fail "ExecStart is not the sidecar's own venv"; fi

if [ "$STATIC_ONLY" = 0 ]; then
    echo "== probe"
    sudo install -d -o agent -g agent -m 0755 "$SCRATCH"
    git clone -q --no-hardlinks --branch grading-data --single-branch /home/agent/projects/metaforge "$CLONE" \
        || { fail "scratch clone"; exit 1; }
    git -C "$CLONE" config user.name "sandbox probe"
    git -C "$CLONE" config user.email "probe@invalid"
    # Same ownership the migration gives the real clone: the unit's user and group.
    owner="$(sed -n 's/^User=//p' "$props")"; group="$(sed -n 's/^Group=//p' "$props")"
    getent passwd metaforge-grading >/dev/null || sudo useradd --system --no-create-home --shell /usr/sbin/nologin --user-group metaforge-grading
    sudo chown -R "${owner}:${group:-$owner}" "$CLONE"
    sudo chmod -R g+rX,o-rwx "$CLONE"
    sleep 300 & OUTSIDE_PID=$!
    trap 'kill $OUTSIDE_PID 2>/dev/null; rm -f "${REPO}/deploy/.mf-probe-proc"; cleanup' EXIT

    # (Specifiers are not expanded in transient properties, so %d is spelled out.)
    # Re-point the unit's live paths at the scratch ones; the old unit's data
    # worktree path maps to the clone too.
    rewrite() { sed "s|${OLD_CLONE}|${CLONE}|g; s|${LIVE_CLONE}|${CLONE}|g; s|${LIVE_CODE}|${REPO}|g; s|%d|/run/credentials/mf-sandbox-test-grading.service|g"; }
    rewrite < "$props" > "${TMP}/props.scratch"
    # Later assignments win: the unit's own, then the probe's overrides.
    {
        rewrite < "${TMP}/env"
        echo "PROBE_CODE_DIR=${REPO}"
        echo "PROBE_MAIN_GIT=${MAIN_GIT}"
        echo "PROBE_OUTSIDE_PID=${OUTSIDE_PID}"
        echo "PYTHONPATH=${REPO}/data-pipeline/"
    } | tac | awk -F= '!seen[$1]++' | tac > "${TMP}/env.final"
    while IFS= read -r line; do echo "Environment=${line}"; done < "${TMP}/env.final" >> "${TMP}/props.scratch"
    echo "Environment=GRADING_DEV=" >> "${TMP}/props.scratch"
    echo "WorkingDirectory=${REPO}" >> "${TMP}/props.scratch"

    mkdir -p "${MAIN_GIT}" 2>/dev/null || true
    out="$(run_sandboxed grading "${TMP}/props.scratch" "exec ${REPO}/data-pipeline/grading_sidecar/.venv/bin/python ${HERE}/sandbox_probe.py" 2>&1)" \
        || fail "probe did not run cleanly: ${out}"
    echo "$out" | grep -E '^(can|cannot):' | sed 's/^/    /'
    for expect in can:create-app cannot:write-code cannot:write-main-git cannot:see-ssh cannot:write-via-proc-root can:read-secret can:write-data can:autocommit; do
        if grep -qx "$expect" <<<"$out"; then ok "$expect"; else fail "wanted ${expect}"; fi
    done
    rm -f "${REPO}/deploy/.mf-probe"
fi

echo ""
if [ "$FAILS" -eq 0 ]; then echo "All checks passed."; else echo "${FAILS} check(s) failed."; exit 1; fi
