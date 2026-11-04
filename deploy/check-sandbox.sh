#!/usr/bin/env bash
# Checks that the API and enricher units are sandboxed as designed.
#
#   deploy/check-sandbox.sh [--static-only] [--live-key]
#
# Static: renders each unit, runs systemd-analyze verify and asserts the hardening
# directives are present. Probe (needs sudo): starts transient units named
# mf-sandbox-test-* with the SAME sandbox properties and asserts what the process
# can and cannot reach. Nothing live is touched: state is re-pointed at
# /var/lib/mf-sandbox-test, which is removed at the end.
#
# The units are rendered against a stand-in worktree at /opt/mf-sandbox-wt (a dummy
# lexicon, nothing from a live tree), because a probe that tries to write to the
# worktree must never be pointed at a real one.
# --live-key also checks /etc/metaforge/forest*.env are not group/world-readable.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORKTREE=/opt/mf-sandbox-wt
# shellcheck source=lib/sandbox-props.sh
. "${HERE}/lib/sandbox-props.sh"

STATIC_ONLY=0 LIVE_KEY=0
for a in "$@"; do
    case "$a" in
        --static-only) STATIC_ONLY=1 ;;
        --live-key) LIVE_KEY=1 ;;
        *) echo "unknown argument: $a" >&2; exit 2 ;;
    esac
done

TMP="$(mktemp -d)"
sudo install -d -o agent -g agent -m 0755 "${WORKTREE}/data-pipeline/output"
: > "${WORKTREE}/data-pipeline/output/lexicon_v2.db"
cleanup() { rm -rf "$TMP"; sudo rm -rf /var/lib/mf-sandbox-test "$WORKTREE" 2>/dev/null || true; }
trap cleanup EXIT

FAILS=0
ok()   { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILS=$((FAILS + 1)); }

UNITS=(production/metaforge-api staging/metaforge-api-staging enrich/metaforge-enrich)

REQUIRED=(
    "User=metaforge" "Group=metaforge" "NoNewPrivileges=true" "ProtectSystem=strict"
    "ProtectHome=tmpfs" "BindReadOnlyPaths=__WT__" "PrivateTmp=true" "PrivateDevices=true"
    "CapabilityBoundingSet=" "AmbientCapabilities="
    "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX"
    "ProtectKernelTunables=true" "ProtectKernelModules=true" "ProtectKernelLogs=true"
    "ProtectControlGroups=true" "ProtectClock=true" "ProtectHostname=true"
    "RestrictNamespaces=true" "RestrictSUIDSGID=true" "RestrictRealtime=true"
    "LockPersonality=true" "SystemCallArchitectures=native"
    "SystemCallFilter=@system-service" "UMask=0077"
)

for u in "${UNITS[@]}"; do
    name="$(basename "$u")"
    unit="${TMP}/${name}.service"
    render_unit "${HERE}/${u}.service" "$WORKTREE" "$unit"
    echo "== ${name}"

    # Missing binaries are expected on a checkout that has not built them; other
    # units' warnings share the output, so keep only this unit's lines.
    v="$(systemd-analyze verify "$unit" 2>&1 | grep -F "${name}.service" | grep -v 'is not executable' || true)"
    if [ -z "$v" ]; then ok "systemd-analyze verify clean"; else fail "verify: $v"; fi

    props="${TMP}/${name}.props"
    sandbox_props "$unit" > "$props"
    for want in "${REQUIRED[@]}"; do
        want="${want//__WT__/$WORKTREE}"
        if grep -qxF "$want" "$props"; then ok "has ${want}"; else fail "missing ${want}"; fi
    done
    if grep -q '^User=agent' "$props"; then fail "runs as agent"; fi
    # The binary runs with the API key, so it must not sit where agent can rewrite it.
    if grep -qE '^ExecStart=/usr/local/lib/metaforge/[a-z-]+/[a-z]+( |$)' "$unit"; then
        ok "binary runs from a root-owned path"; else fail "ExecStart is not under /usr/local/lib/metaforge"; fi
done

if [ "$LIVE_KEY" = 1 ]; then
    echo "== key files"
    for f in /etc/metaforge/forest.env /etc/metaforge/forest-staging.env; do
        mode="$(sudo stat -c '%a %U:%G' "$f" 2>/dev/null || true)"
        if [ -z "$mode" ]; then echo "  SKIP: ${f} absent"
        elif [ "$mode" = "600 root:root" ]; then ok "${f} is ${mode}"
        else fail "${f} is ${mode}, want 600 root:root"; fi
    done
fi

if [ "$STATIC_ONLY" = 0 ]; then
    sudo install -d -m 1777 /var/lib/mf-sandbox-test
    PROBE='
t() { if "$@" >/dev/null 2>&1; then echo "can:$LBL"; else echo "cannot:$LBL"; fi; }
LBL=see-ssh         t test -e /home/agent/.ssh
LBL=see-claude    t test -e /home/agent/.claude
LBL=write-worktree  t touch "$WT/.mf-probe"
LBL=write-output    t touch "$WT/data-pipeline/output/.mf-probe"
LBL=read-lexicon    t test -r "$WT/data-pipeline/output/lexicon_v2.db"
LBL=write-state     t touch /var/lib/mf-sandbox-test/.mf-probe
'
    for u in "${UNITS[@]}"; do
        name="$(basename "$u")"
        echo "== probe ${name}"
        scratch_state < "${TMP}/${name}.props" > "${TMP}/${name}.scratch.props"
        out="$(run_sandboxed "${name#metaforge-}" "${TMP}/${name}.scratch.props" "WT='${WORKTREE}'; ${PROBE}" 2>&1)" \
            || { fail "transient unit did not run: ${out}"; continue; }
        for expect in cannot:see-ssh cannot:see-claude cannot:write-worktree cannot:write-output can:read-lexicon can:write-state; do
            if grep -qx "$expect" <<<"$out"; then ok "$expect"; else fail "wanted ${expect}"; fi
        done
    done
fi

echo ""
if [ "$FAILS" -eq 0 ]; then echo "All checks passed."; else echo "${FAILS} check(s) failed."; exit 1; fi
