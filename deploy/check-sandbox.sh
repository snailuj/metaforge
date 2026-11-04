#!/usr/bin/env bash
# Checks that the API and enricher units are sandboxed as designed.
#
#   deploy/check-sandbox.sh [--static-only] [--no-real] [--live-key]
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
# Real program: the production unit's properties are also applied to the Go binary
# built from this checkout (installed root-owned under /opt/mf-sandbox-bin) serving
# the real .worktrees/next lexicon through a read-only bind, on port 8099 with no API
# key, so a seccomp or address-family rule that kills the real server is caught.
# Nothing is ever written into that live worktree. --no-real skips this.
# --live-key also checks /etc/metaforge/forest*.env are not group/world-readable.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORKTREE=/opt/mf-sandbox-wt
# shellcheck source=lib/sandbox-props.sh
. "${HERE}/lib/sandbox-props.sh"

STATIC_ONLY=0 LIVE_KEY=0 REAL=1
LIVE_NEXT=/home/agent/projects/metaforge/.worktrees/next
REPO="$(cd "${HERE}/.." && pwd)"
BIN_DIR=/opt/mf-sandbox-bin
for a in "$@"; do
    case "$a" in
        --static-only) STATIC_ONLY=1 ;;
        --live-key) LIVE_KEY=1 ;;
        --no-real) REAL=0 ;;
        *) echo "unknown argument: $a" >&2; exit 2 ;;
    esac
done

TMP="$(mktemp -d)"
sudo install -d -o agent -g agent -m 0755 "${WORKTREE}/data-pipeline/output"
: > "${WORKTREE}/data-pipeline/output/lexicon_v2.db"
cleanup() { rm -rf "$TMP"; sudo systemctl stop mf-sandbox-test-real 2>/dev/null || true
    sudo rm -rf /var/lib/mf-sandbox-test "$WORKTREE" "$BIN_DIR" 2>/dev/null || true; }
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

if [ "$STATIC_ONLY" = 0 ] && [ "$REAL" = 1 ]; then
    echo "== real program under the production unit's sandbox"
    . "${HERE}/lib/api-host.sh"
    if ! (cd "${REPO}/api" && PATH="/usr/local/go/bin:${PATH}" go build -o "${TMP}/metaforge" ./cmd/metaforge) 2>"${TMP}/build.log"; then
        fail "go build: $(tail -3 "${TMP}/build.log")"
    else
        install_root_binary "${TMP}/metaforge" "${BIN_DIR}/metaforge" >/dev/null
        render_unit "${HERE}/production/metaforge-api.service" "$LIVE_NEXT" "${TMP}/real.service"
        sandbox_props "${TMP}/real.service" | scratch_state > "${TMP}/real.props"
        sed -i 's|^StateDirectory=.*|StateDirectory=mf-sandbox-test mf-sandbox-test/production|' "${TMP}/real.props"
        args=(); while IFS= read -r l; do args+=(-p "$l"); done < "${TMP}/real.props"
        sudo systemd-run --quiet --collect -u mf-sandbox-test-real "${args[@]}" -p MemoryMax=600M \
            -p Environment=METAFORGE_FOREST_CACHE=/var/lib/mf-sandbox-test/production/forest_cache.db \
            -p Environment=METAFORGE_LLM_LOG=/var/lib/mf-sandbox-test/llm_calls.db \
            "${BIN_DIR}/metaforge" -port 8099 -db "${LIVE_NEXT}/data-pipeline/output/lexicon_v2.db" \
            -strings "${LIVE_NEXT}/strings" -cors-origin https://example.test \
            || fail "could not start the transient server"
        for _ in $(seq 1 30); do curl -sf -o /dev/null http://127.0.0.1:8099/health && break; sleep 1; done
        code() { curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8099$1"; }
        [ "$(code /health)" = 200 ] && ok "/health 200" || fail "/health did not answer 200"
        [ "$(code '/thesaurus/lookup?word=hope')" = 200 ] && ok "lookup 200" || fail "lookup did not answer 200"
        [ "$(code '/forge/forest?word=hope')" = 503 ] && ok "forest 503 without a key" || fail "forest did not answer 503"
        systemctl is-active --quiet mf-sandbox-test-real && ok "server still running (not killed by the filter)" \
            || fail "server died: $(sudo journalctl -u mf-sandbox-test-real --no-pager -n 3 | cut -c1-160 | tr '\n' '|')"
        sudo test -s /var/lib/mf-sandbox-test/production/forest_cache.db && ok "cache written under the state dir" || fail "no cache written"
        # Read-only is read from the mount table, not by trying to write to a live tree.
        out="$(run_sandboxed realview "${TMP}/real.props" "grep ' ${LIVE_NEXT} ' /proc/self/mountinfo; test -e /home/agent/.ssh && echo SSH-VISIBLE" 2>&1)"
        grep -q " ${LIVE_NEXT} ro," <<<"$out" && ok "live worktree bind is read-only" || fail "live worktree bind is not read-only: ${out}"
        grep -q SSH-VISIBLE <<<"$out" && fail "~/.ssh visible" || ok "~/.ssh not visible"
        sudo systemctl stop mf-sandbox-test-real
    fi
fi

echo ""
if [ "$FAILS" -eq 0 ]; then echo "All checks passed."; else echo "${FAILS} check(s) failed."; exit 1; fi
