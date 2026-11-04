#!/usr/bin/env bash
# Tests sync-data-to-repo.sh against scratch repos:  deploy/grading/test-sync-data-to-repo.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
FAILS=0
ok()   { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILS=$((FAILS + 1)); }

SRC="${T}/src"; CLONE="${T}/clone"
git init -q -b main "$SRC"
git -C "$SRC" config user.name Bot; git -C "$SRC" config user.email bot@example.invalid
echo code > "${SRC}/code.txt"; git -C "$SRC" add code.txt; git -C "$SRC" commit -q -m code
git -C "$SRC" checkout -q -b grading-data
mkdir -p "${SRC}/data-pipeline/grading"; echo '{"a":1}' > "${SRC}/data-pipeline/grading/j.jsonl"
git -C "$SRC" add data-pipeline; git -C "$SRC" commit -q -m first
git -C "$SRC" checkout -q main
git clone -q --no-hardlinks --branch grading-data --single-branch "$SRC" "$CLONE"
git -C "$CLONE" config user.name Bot; git -C "$CLONE" config user.email bot@example.invalid

BIN="${T}/bin"; mkdir -p "$BIN"
cat > "${BIN}/sudo" <<'EOS'
#!/usr/bin/env bash
if [ "${1:-}" = "-u" ]; then shift 3; fi
exec "$@"
EOS
chmod +x "${BIN}/sudo"
export PATH="${BIN}:${PATH}" MF_SRC_REPO="$SRC" MF_CLONE="$CLONE"
RUN() { "${HERE}/sync-data-to-repo.sh"; }
tip() { git -C "$SRC" rev-parse refs/heads/grading-data; }

echo "== fast-forwards the branch to the clone's commits"
echo '{"a":2}' >> "${CLONE}/data-pipeline/grading/j.jsonl"
git -C "$CLONE" commit -qam "wip(grading): autosave"
RUN >/dev/null 2>&1 && ok "exit 0" || fail "sync failed"
[ "$(tip)" = "$(git -C "$CLONE" rev-parse HEAD)" ] && ok "branch at the clone's tip" || fail "branch not advanced"
[ "$(git -C "$SRC" branch --show-current)" = main ] && ok "main checkout untouched" || fail "main checkout moved"

echo "== idempotent"
BEFORE="$(tip)"; RUN >/dev/null 2>&1 && [ "$(tip)" = "$BEFORE" ] && ok "second run is a no-op" || fail "second run changed or failed"

echo "== refuses when the branch is checked out in a worktree"
echo '{"a":3}' >> "${CLONE}/data-pipeline/grading/j.jsonl"; git -C "$CLONE" commit -qam "wip(grading): autosave 2"
git -C "$SRC" worktree add -q "${T}/wt" grading-data
OUT="$(RUN 2>&1)" && fail "synced into a checked-out branch" || ok "refused"
grep -q "checkout --detach" <<<"$OUT" && ok "says how to fix it" || fail "no hint"
git -C "${T}/wt" checkout -q --detach
RUN >/dev/null 2>&1 && ok "works once detached" || fail "still failing after detach"

echo "== the detached old worktree follows the new tip, read-only mirror style"
export MF_OLD_WT="${T}/wt"
echo '{"a":5}' >> "${CLONE}/data-pipeline/grading/j.jsonl"; git -C "$CLONE" commit -qam "wip(grading): autosave 5"
RUN >/dev/null 2>&1 && ok "exit 0" || fail "sync failed"
[ "$(git -C "$MF_OLD_WT" rev-parse HEAD)" = "$(tip)" ] && ok "worktree moved to the tip" || fail "worktree stale"
[ "$(git -C "$MF_OLD_WT" rev-parse --abbrev-ref HEAD)" = HEAD ] && ok "still detached" || fail "worktree re-attached"
grep -q '"a":5' "${MF_OLD_WT}/data-pipeline/grading/j.jsonl" && ok "files show the new verdicts" || fail "files stale"

echo "== a dirty old worktree is left alone"
echo '{"a":6}' >> "${CLONE}/data-pipeline/grading/j.jsonl"; git -C "$CLONE" commit -qam "wip(grading): autosave 6"
echo scribble >> "${MF_OLD_WT}/data-pipeline/grading/j.jsonl"
STALE="$(git -C "$MF_OLD_WT" rev-parse HEAD)"
OUT="$(RUN 2>&1)" && ok "branch still synced" || fail "sync failed"
[ "$(git -C "$MF_OLD_WT" rev-parse HEAD)" = "$STALE" ] && ok "dirty worktree not moved" || fail "dirty worktree moved"
grep -q scribble "${MF_OLD_WT}/data-pipeline/grading/j.jsonl" && ok "its edit is intact" || fail "edit lost"
grep -qi "dirty\|not clean" <<<"$OUT" && ok "warns" || fail "silent"
git -C "$MF_OLD_WT" checkout -q -- .

echo "== refuses a diverged clone"
git -C "$SRC" update-ref refs/heads/grading-data "$(git -C "$SRC" commit-tree -p "$(git -C "$SRC" rev-parse main)" -m other "$(git -C "$SRC" rev-parse 'main^{tree}')")"
echo '{"a":4}' >> "${CLONE}/data-pipeline/grading/j.jsonl"; git -C "$CLONE" commit -qam "wip(grading): autosave 3"
RUN >/dev/null 2>&1 && fail "overwrote a diverged branch" || ok "diverged branch refused"

echo ""
if [ "$FAILS" -eq 0 ]; then echo "All tests passed."; else echo "${FAILS} test(s) failed."; exit 1; fi
