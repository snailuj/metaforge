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
case "$*" in
    *healthz*) echo '{"ok":true}' ;;
    *stats*)
        if [ -e "$FAKE_STATE/deployed" ]; then d="$MF_CLONE"; else d="$MF_OLD_WT"; fi
        echo "{\"judgement_count\": $(wc -l < "$d/data-pipeline/grading/judgements_provisional.jsonl")}" ;;
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

echo "== re-run is safe"
rm -f "${FAKE_STATE}/deployed"
OUT="$(RUN 2>&1)" && ok "exit 0" || { fail "re-run failed"; echo "$OUT" | tail -8; }

echo "== refuses a worktree standing in for the clone"
rm -rf "${T}/clone2"; git -C "$SRC" worktree add -q "${T}/clone2" -b other
MF_CLONE="${T}/clone2" RUN >/dev/null 2>&1 && fail "accepted a worktree" || ok "worktree refused"

echo "== failed deploy prints rollback steps"
rm -f "${FAKE_STATE}/deployed"
OUT="$(FAKE_DEPLOY_FAILS=1 RUN 2>&1)" && fail "ignored a failed deploy" || ok "failed deploy fails the run"
grep -q "MIGRATION FAILED" <<<"$OUT" && ok "rollback steps printed" || fail "no rollback steps"

echo "== count mismatch is caught"
rm -f "${FAKE_STATE}/deployed"
cat > "${T}/deploy.sh" <<'EOS'
#!/usr/bin/env bash
touch "$FAKE_STATE/deployed"; echo '{"a":9}' >> "$MF_CLONE/data-pipeline/grading/judgements_provisional.jsonl"
EOS
RUN >/dev/null 2>&1 && fail "accepted a changed count" || ok "changed count refused"

echo ""
if [ "$FAILS" -eq 0 ]; then echo "All tests passed."; else echo "${FAILS} test(s) failed."; exit 1; fi
