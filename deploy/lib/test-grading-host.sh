#!/usr/bin/env bash
# Tests for deploy/lib/grading-host.sh against scratch files; useradd and usermod
# are faked and logged, chown and chmod are real (needs sudo and the
# metaforge-grading user, which deploy/grading/check-sandbox.sh creates):
#   deploy/lib/test-grading-host.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
T="$(mktemp -d)"
LOG="${T}/calls.log"; : > "$LOG"
trap 'command sudo rm -rf "$T"' EXIT
sudo() {
    case "$1" in
        useradd|usermod) echo "sudo $*" >> "$LOG" ;;
        *)               command sudo "$@" ;;
    esac
}
# shellcheck source=grading-host.sh
. "${HERE}/grading-host.sh"

FAILS=0
ok()   { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILS=$((FAILS + 1)); }

echo "== ensure_grading_user"
(GRADING_USER=mf-test-absent; ensure_grading_user >/dev/null)
grep -qF "useradd --system --no-create-home --shell /usr/sbin/nologin --user-group mf-test-absent" "$LOG" \
    && ok "creates a missing user" || fail "did not create the user"
: > "$LOG"; GRADING_USER=root ensure_grading_user >/dev/null
[ ! -s "$LOG" ] && ok "leaves an existing user alone" || fail "touched an existing user"

echo "== ensure_group_member"
: > "$LOG"; GRADING_USER=root ensure_group_member nobody >/dev/null
grep -qF "usermod -aG root nobody" "$LOG" && ok "adds a non-member" || fail "did not add the member"
: > "$LOG"; GRADING_USER=root ensure_group_member root >/dev/null
[ ! -s "$LOG" ] && ok "skips an existing member" || fail "re-added a member"

echo "== own_data_clone"
mkdir -p "${T}/clone/data-pipeline/grading" "${T}/clone/.git"
echo '{}' > "${T}/clone/data-pipeline/grading/a.jsonl"; chmod 666 "${T}/clone/data-pipeline/grading/a.jsonl"
own_data_clone "${T}/clone" >/dev/null
[ "$(command sudo stat -c '%U:%G' "${T}/clone/data-pipeline/grading/a.jsonl")" = "metaforge-grading:metaforge-grading" ] \
    && ok "files owned by the grading user" || fail "ownership wrong"
[ "$(command sudo stat -c '%a' "${T}/clone/data-pipeline/grading/a.jsonl")" = 640 ] && ok "file mode 640" || fail "file mode wrong"
[ "$(command sudo stat -c '%a' "${T}/clone/data-pipeline/grading")" = 750 ] && ok "dir mode 750" || fail "dir mode wrong"

echo "== strip_env_keys"
printf 'GRADING_SECRET_FILE=/etc/x\nKEEP=1\nPYTHONPATH=/p\nGRADING_SECRET_FILE_OTHER=2\n' > "${T}/env"
strip_env_keys "${T}/env" GRADING_SECRET_FILE PYTHONPATH >/dev/null
[ "$(cat "${T}/env")" = $'KEEP=1\nGRADING_SECRET_FILE_OTHER=2' ] && ok "only the exact keys removed" || fail "env file wrong: $(cat "${T}/env")"
strip_env_keys "${T}/env" GRADING_SECRET_FILE >/dev/null && ok "idempotent" || fail "second run failed"
strip_env_keys "${T}/missing" GRADING_SECRET_FILE >/dev/null && ok "absent file is fine" || fail "absent file failed"

echo "== refuse_unmigrated"
printf 'GRADING_DATA_DIR=/x/.worktrees/grading-data/data-pipeline/grading\n' > "${T}/old.service"
printf 'GRADING_DATA_DIR=/x/metaforge-grading-data/data-pipeline/grading\n' > "${T}/new.service"
refuse_unmigrated "${T}/old.service" 2>/dev/null && fail "switched an unmigrated install" || ok "unit still on the old worktree is refused"
MF_MIGRATING=1 refuse_unmigrated "${T}/old.service" && ok "allowed from the migration" || fail "migration blocked"
refuse_unmigrated "${T}/new.service" && ok "migrated unit passes" || fail "migrated unit refused"
refuse_unmigrated "${T}/absent.service" && ok "no unit yet passes" || fail "fresh install refused"
HINT="$(refuse_unmigrated "${T}/old.service" 2>&1)"; grep -q migrate-data-clone.sh <<<"$HINT" && ok "names the script to run" || fail "no hint"

echo ""
if [ "$FAILS" -eq 0 ]; then echo "All tests passed."; else echo "${FAILS} test(s) failed."; exit 1; fi
