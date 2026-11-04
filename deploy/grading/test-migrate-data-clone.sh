#!/usr/bin/env bash
# Tests migrate-data-clone.sh against scratch repos with sudo, systemctl, curl and
# deploy.sh faked:  deploy/grading/test-migrate-data-clone.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
FAILS=0
ok()   { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILS=$((FAILS + 1)); }

# --- scratch source repo with a grading-data branch and a worktree on it ---
SRC="${T}/src"
git init -q -b main "$SRC"
git -C "$SRC" config user.name "Autocommit Bot"; git -C "$SRC" config user.email "bot@example.invalid"
echo code > "${SRC}/code.txt"; git -C "$SRC" add code.txt; git -C "$SRC" commit -q -m code
git -C "$SRC" checkout -q -b grading-data
mkdir -p "${SRC}/data-pipeline/grading"
printf '{"a":1}\n{"a":2}\n' > "${SRC}/data-pipeline/grading/judgements_provisional.jsonl"
git -C "$SRC" add data-pipeline; git -C "$SRC" commit -q -m "wip(grading): autosave"
git -C "$SRC" checkout -q main
git -C "$SRC" worktree add -q "${SRC}/.worktrees/grading-data" grading-data
OLD="${SRC}/.worktrees/grading-data"
# A verdict the autocommit had not saved yet:
echo '{"a":3}' >> "${OLD}/data-pipeline/grading/judgements_provisional.jsonl"

# --- fakes on PATH ---
BIN="${T}/bin"; mkdir -p "$BIN"
cat > "${BIN}/sudo" <<'EOS'
#!/usr/bin/env bash
# Records the user asked for (git work on agent's repos must be done as agent), then runs as us.
if [ "${1:-}" = "-u" ]; then echo "as:$2 ${*:4}" >> "$FAKE_LOG"; shift 3; fi
exec "$@"
EOS
cat > "${BIN}/systemctl" <<'EOS'
#!/usr/bin/env bash
echo "systemctl $*" >> "$FAKE_LOG"
EOS
# The fake sidecar serves whichever data dir is live: the old worktree until the
# fake deploy runs, the clone afterwards.
cat > "${BIN}/curl" <<'EOS'
#!/usr/bin/env bash
[ -t 0 ] || cat > /dev/null   # the real curl reads the header file from stdin
case "$*" in
    *healthz*) echo '{"ok":true}' ;;
    *stats*)
        if [ -e "$FAKE_STATE/deployed" ]; then d="$MF_CLONE"; else d="$MF_OLD_WT"; fi
        echo "{\"judgement_count\": $(grep -c . "$d/data-pipeline/grading/judgements_provisional.jsonl")}" ;;
esac
EOS
cat > "${T}/deploy.sh" <<'EOS'
#!/usr/bin/env bash
[ "${FAKE_DEPLOY_FAILS:-0}" = 1 ] && exit 1
touch "$FAKE_STATE/deployed"
EOS
chmod +x "${BIN}"/* "${T}/deploy.sh"
echo secret > "${T}/secret"; echo "[Service]" > "${T}/unit.service"

export PATH="${BIN}:${PATH}" FAKE_LOG="${T}/log" FAKE_STATE="${T}/state"
export MF_SRC_REPO="$SRC" MF_OLD_WT="$OLD" MF_CLONE="${T}/clone" MF_UNIT_FILE="${T}/unit.service" \
       MF_DEPLOY="${T}/deploy.sh" MF_SECRET_FILE="${T}/secret" MF_SKIP_CHECKOUT_CHECK=1
mkdir -p "$FAKE_STATE"; : > "$FAKE_LOG"
RUN() { "${HERE}/migrate-data-clone.sh"; }
# Back to the state before a cutover: old worktree on its branch, the old unit
# installed, no backup, nothing deployed.
PRE() {
    git -C "$OLD" checkout -q grading-data
    [ ! -d "${MF_CLONE}/.git" ] || git -C "$MF_CLONE" reset -q --hard "$(git -C "$OLD" rev-parse grading-data)"
    echo "OLD UNIT" > "${T}/unit.service"; rm -f "${MF_CLONE}.service.pre-migration" "${FAKE_STATE}/deployed"
    cat > "${T}/deploy.sh" <<'EOS'
#!/usr/bin/env bash
[ "${FAKE_DEPLOY_FAILS:-0}" = 1 ] && exit 1
echo "[Service]
User=metaforge-grading" > "$MF_UNIT_FILE"
touch "$FAKE_STATE/deployed"
EOS
}
PRE

echo "== first run"
OUT="$(RUN 2>&1)" && ok "exit 0" || { fail "exit non-zero"; echo "$OUT" | tail -8; }
[ -d "${MF_CLONE}/.git" ] && ok "clone has its own .git dir" || fail "no clone"
[ "$(wc -l < "${MF_CLONE}/data-pipeline/grading/judgements_provisional.jsonl")" = 3 ] \
    && ok "unsaved verdict reached the clone" || fail "unsaved verdict lost"
[ -z "$(git -C "$OLD" status --porcelain data-pipeline)" ] && ok "old worktree committed" || fail "old worktree dirty"
[ -d "$OLD" ] && ok "old worktree kept" || fail "old worktree deleted"
[ "$(git -C "$MF_CLONE" config user.name)" = "Autocommit Bot" ] && ok "identity copied" || fail "identity not set"
[ ! -e "${MF_CLONE}/.git/objects/info/alternates" ] && ok "no shared objects" || fail "clone shares objects"
grep -q "systemctl stop metaforge-grading" "$FAKE_LOG" && ok "sidecar stopped" || fail "sidecar not stopped"
[ -e "${MF_CLONE}.service.pre-migration" ] && ok "unit backed up" || fail "unit not backed up"

echo "== a second run after the cutover is a no-op that never stops the sidecar"
echo '{"a":4}' >> "${MF_CLONE}/data-pipeline/grading/judgements_provisional.jsonl"   # the clone is live now
git -C "$MF_CLONE" commit -qam "wip(grading): autosave after cutover"
UNIT_BEFORE="$(cat "${T}/unit.service")"; : > "$FAKE_LOG"
OUT="$(RUN 2>&1)" && ok "exit 0" || { fail "second run failed"; echo "$OUT" | tail -12; }
grep -qi "already migrated" <<<"$OUT" && ok "says so" || fail "does not say it is already migrated"
grep -q "systemctl stop" "$FAKE_LOG" && fail "stopped the sidecar" || ok "sidecar never stopped"
[ "$(cat "${T}/unit.service")" = "$UNIT_BEFORE" ] && ok "installed unit untouched" || fail "unit rewritten"
[ "$(git -C "$OLD" rev-parse --abbrev-ref HEAD)" = HEAD ] && ok "old worktree still detached" || fail "old worktree re-attached"
[ "$(grep -c . "${MF_CLONE}/data-pipeline/grading/judgements_provisional.jsonl")" = 4 ] && ok "clone verdicts kept" || fail "clone verdicts lost"

echo "== each sign of a finished cutover is enough on its own"
for sign in unit owner detached; do
    PRE; : > "$FAKE_LOG"
    case "$sign" in
        unit)     printf '[Service]\nUser=metaforge-grading\n' > "${T}/unit.service"; E=() ;;
        owner)    E=(MF_SIDECAR_USER="$(id -un)") ;;
        detached) git -C "$OLD" checkout -q --detach; E=() ;;
    esac
    env "${E[@]}" "${HERE}/migrate-data-clone.sh" >/dev/null 2>&1 && ! grep -q "systemctl stop" "$FAKE_LOG" \
        && ok "${sign}: skipped" || fail "${sign}: ran the migration"
done
PRE

echo "== a re-run after a half-finished first run completes it"
OUT="$(RUN 2>&1)" && ok "exit 0" || { fail "re-run failed"; echo "$OUT" | tail -8; }
grep -q "systemctl stop" "$FAKE_LOG" && ok "did the migration" || fail "skipped an unfinished migration"

echo "== refuses a worktree standing in for the clone"
PRE
rm -rf "${T}/clone2"; git -C "$SRC" worktree add -q "${T}/clone2" -b other
MF_CLONE="${T}/clone2" RUN >/dev/null 2>&1 && fail "accepted a worktree" || ok "worktree refused"

echo "== failed deploy prints rollback steps"
PRE
OUT="$(FAKE_DEPLOY_FAILS=1 RUN 2>&1)" && fail "ignored a failed deploy" || ok "failed deploy fails the run"
grep -q "MIGRATION FAILED" <<<"$OUT" && ok "rollback steps printed" || fail "no rollback steps"

echo "== count mismatch is caught"
PRE
cat > "${T}/deploy.sh" <<'EOS'
#!/usr/bin/env bash
touch "$FAKE_STATE/deployed"; echo '{"a":9}' >> "$MF_CLONE/data-pipeline/grading/judgements_provisional.jsonl"
EOS
RUN >/dev/null 2>&1 && fail "accepted a changed count" || ok "changed count refused"

git -C "$MF_CLONE" checkout -q -- . ; git -C "$MF_CLONE" clean -fdq   # undo the previous case
echo "== git on agent-owned repos runs as agent, not as root"
grep -q "^as:$(id -un) git" "$FAKE_LOG" && ok "git ran via sudo -u owner" || fail "git ran as the invoking user"

echo "== failed deploy puts the old unit back and restarts it"
PRE
cat > "${T}/deploy.sh" <<'EOS'
#!/usr/bin/env bash
echo "NEW UNIT" > "$MF_UNIT_FILE"; exit 1
EOS
: > "$FAKE_LOG"
OUT="$(RUN 2>&1)" && fail "ignored a failed deploy" || ok "run fails"
[ "$(cat "${T}/unit.service")" = "OLD UNIT" ] && ok "previous unit restored" || fail "unit not restored: $(cat "${T}/unit.service")"
grep -q "systemctl start metaforge-grading" "$FAKE_LOG" && ok "sidecar started again" || fail "sidecar left stopped"
grep -q "restored the previous unit" <<<"$OUT" && ok "says what it did" || fail "silent about the restore"

echo "== a stale backup from an earlier run is never restored"
PRE; echo "STALE UNIT (User=agent, whole repo writable)" > "${MF_CLONE}.service.pre-migration"
cat > "${T}/deploy.sh" <<'EOS'
#!/usr/bin/env bash
echo "NEW UNIT" > "$MF_UNIT_FILE"; exit 1
EOS
RUN >/dev/null 2>&1 && fail "ignored a failed deploy" || ok "run fails"
[ "$(cat "${T}/unit.service")" = "OLD UNIT" ] && ok "restored the unit captured in this run" || fail "restored: $(cat "${T}/unit.service")"
grep -q '^as:.* sh -c' "$FAKE_LOG" && ok "the data inventory is read as the dir owner" || fail "inventory ran as the invoking user"

echo "== an explicit exit after the stop also restarts the sidecar"
PRE; : > "$FAKE_LOG"
chmod 000 "${MF_CLONE}/data-pipeline/grading/judgements_provisional.jsonl"  # step 6 cannot read it
RUN >/dev/null 2>&1 && fail "run succeeded" || ok "run fails"
chmod 644 "${MF_CLONE}/data-pipeline/grading/judgements_provisional.jsonl"
grep -q "systemctl start metaforge-grading" "$FAKE_LOG" && ok "sidecar started again" || fail "sidecar left stopped"

echo "== every appended file is compared, not just the judgements"
PRE
echo "note" >> "${OLD}/data-pipeline/grading/design_notes_provisional.md"
git -C "$OLD" add -A data-pipeline >/dev/null; git -C "$OLD" commit -q -m notes
echo "extra" >> "${MF_CLONE}/data-pipeline/grading/design_notes_provisional.md"   # clone diverges on a non-judgement file
cat > "${T}/deploy.sh" <<'EOS'
#!/usr/bin/env bash
touch "$FAKE_STATE/deployed"
EOS
RUN >/dev/null 2>&1 && fail "accepted a clone with different notes" || ok "different line counts refused"
git -C "$MF_CLONE" checkout -q -- . ; git -C "$MF_CLONE" clean -fdq

echo "== the write check fails when the sidecar user cannot write the clone"
PRE
git -C "$MF_CLONE" pull -q --ff-only "$SRC" grading-data
chmod a-w "${MF_CLONE}/data-pipeline/grading"
RUN >/dev/null 2>&1 && fail "accepted an unwritable data dir" || ok "unwritable data dir refused"
chmod u+w "${MF_CLONE}/data-pipeline/grading"

echo "== a good run detaches the old worktree so the branch can be fast-forwarded"
PRE
RUN >/dev/null 2>&1 && ok "run succeeds" || fail "good run failed"
[ "$(git -C "$OLD" rev-parse --abbrev-ref HEAD)" = HEAD ] && ok "old worktree detached" || fail "old worktree still on the branch"

echo ""
if [ "$FAILS" -eq 0 ]; then echo "All tests passed."; else echo "${FAILS} test(s) failed."; exit 1; fi
