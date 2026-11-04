#!/usr/bin/env bash
# Tests for deploy/lib/api-host.sh against a scratch state dir under /var/lib, owned
# by the real metaforge user as on the host. useradd and systemctl are faked and
# logged; needs sudo and the metaforge user:  deploy/lib/test-api-host.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
T="$(mktemp -d)"
LOG="${T}/calls.log"
: > "$LOG"

# Real sudo, so ownership and modes behave as on the host (the state dir must be
# unreachable by the invoking user, which a faked sudo hid). Only the commands that
# change the host outside the scratch dirs are faked and logged.
sudo() {
    case "$1" in
        useradd|systemctl) echo "sudo $*" >> "$LOG" ;;
        *)                 command sudo "$@" ;;
    esac
}

export MF_STATE_DIR=/var/lib/mf-sandbox-test-api-host MF_KEY_DIR="${T}/etc" MF_USER=metaforge
mkdir -p "$MF_KEY_DIR"
trap 'sudo rm -rf "$MF_STATE_DIR" "$MF_KEY_DIR"; rm -rf "$T"' EXIT
command sudo rm -rf "$MF_STATE_DIR"
# shellcheck source=api-host.sh
. "${HERE}/api-host.sh"

FAILS=0
ok()   { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILS=$((FAILS + 1)); }
expect_log()  { if grep -qF -- "$1" "$LOG"; then ok "logged: $1"; else fail "not logged: $1"; fi; }
expect_nolog(){ if grep -qF -- "$1" "$LOG"; then fail "unexpectedly logged: $1"; else ok "not logged: $1"; fi; }

echo "== ensure_service_user"
(MF_USER=mf-test-absent-user; ensure_service_user >/dev/null)
expect_log "useradd --system --no-create-home --shell /usr/sbin/nologin --user-group mf-test-absent-user"
: > "$LOG"; ensure_service_user >/dev/null
expect_nolog "useradd"

echo "== ensure_state_dir"
ensure_state_dir production >/dev/null
[ "$(command sudo stat -c '%U:%G %a' "${MF_STATE_DIR}/production")" = "metaforge:metaforge 750" ] \
    && ok "site dir is metaforge 0750" || fail "site dir ownership wrong"
# Precondition for every later test: the invoking user cannot even look inside.
if [ -e "${MF_STATE_DIR}/production" ]; then fail "state dir is visible to $(id -un): the tests would prove nothing"
else ok "state dir is unsearchable by $(id -un)"; fi

echo "== secure_key_files"
touch "${MF_KEY_DIR}/forest.env"
secure_key_files forest.env forest-staging.env >/dev/null
[ "$(command sudo stat -c '%U:%G %a' "${MF_KEY_DIR}/forest.env")" = "root:root 600" ] \
    && ok "forest.env is root:root 600" || fail "forest.env mode wrong"
[ ! -e "${MF_KEY_DIR}/forest-staging.env" ] && ok "absent file skipped" || fail "absent file created"

echo "== migrate_forest_cache"
WT="${T}/wt"; mkdir -p "${WT}/data-pipeline/output"
OLD="${WT}/data-pipeline/output/forest_cache.db"
NEW="${MF_STATE_DIR}/production/forest_cache.db"
rows() { command sudo sqlite3 "$1" 'SELECT count(*) FROM f'; }
exists() { command sudo test -e "$1"; }

: > "$LOG"; migrate_forest_cache production svc "$WT" >/dev/null
if ! exists "$NEW"; then ok "nothing to migrate, nothing created"; else fail "created a cache from nothing"; fi
expect_nolog "systemctl stop"

sqlite3 "$OLD" "PRAGMA journal_mode=WAL; CREATE TABLE f(x); INSERT INTO f VALUES (1),(2);" >/dev/null
: > "$LOG"; migrate_forest_cache production svc "$WT" >/dev/null && ok "migration exits 0" || fail "migration failed"
[ "$(rows "$NEW")" = 2 ] && ok "rows copied" || fail "rows not copied"
expect_log "systemctl stop svc"
[ "$(command sudo stat -c '%U:%G' "$NEW")" = "metaforge:metaforge" ] && ok "cache owned by metaforge" || fail "cache ownership wrong"
[ -e "$OLD" ] && ok "old cache kept" || fail "old cache deleted"
[ -z "$(command sudo ls "${MF_STATE_DIR}/production" | grep partial)" ] && ok "no partial file left" || fail "partial file left"

echo "== migrate_forest_cache is idempotent"
command sudo sqlite3 "$NEW" "INSERT INTO f VALUES (3)"
: > "$LOG"; migrate_forest_cache production svc "$WT" >/dev/null
[ "$(rows "$NEW")" = 3 ] && ok "existing cache not overwritten" || fail "existing cache overwritten"
expect_nolog "systemctl stop"

echo "== migrate_forest_cache recovers from a half-finished copy"
command sudo rm -f "$NEW"; echo junk | command sudo tee "${NEW}.partial" >/dev/null
migrate_forest_cache production svc "$WT" >/dev/null
[ "$(rows "$NEW")" = 2 ] && ok "stale partial replaced" || fail "stale partial used"

echo "== migrate_forest_cache without sqlite3 copies the db and its wal"
command sudo rm -f "$NEW"
have_sqlite3() { return 1; }
echo wal-bytes > "${OLD}-wal"
migrate_forest_cache production svc "$WT" >/dev/null
exists "$NEW" && ok "db copied" || fail "db not copied"
[ "$(command sudo cat "${NEW}-wal" 2>/dev/null)" = wal-bytes ] && ok "wal copied" || fail "wal not copied"
rm -f "${OLD}-wal"; unset -f have_sqlite3
. "${HERE}/api-host.sh"

echo "== a failed copy restarts the service and fails"
command sudo rm -f "$NEW" "${NEW}-wal"
mv "$OLD" "${OLD}.good"; echo "not a database" > "$OLD"
: > "$LOG"; migrate_forest_cache production svc "$WT" >/dev/null && fail "failure not reported" || ok "failure reported"
expect_log "systemctl start svc"
exists "$NEW" && fail "half-copied cache left looking finished" || ok "no cache left behind"
mv "${OLD}.good" "$OLD"

echo "== a script that dies after the stop restarts the service"
command sudo rm -f "$NEW" "${NEW}-wal"
: > "$LOG"
# A separate process, so no trap or variable leaks in from this shell.
cat > "${T}/dies.sh" <<EOS
sudo() { case "\$1" in systemctl) echo "sudo \$*" >> "$LOG" ;; *) command sudo "\$@" ;; esac; }
. "${HERE}/api-host.sh"
migrate_forest_cache production svc "$WT" >/dev/null
exit 3
EOS
bash "${T}/dies.sh"; rc=$?
[ "$rc" = 3 ] && ok "exit status preserved" || fail "exit status was $rc"
expect_log "systemctl start svc"

MF_STOPPED_SERVICE=   # the migrations above armed the exit restart; nothing is real here
echo ""
if [ "$FAILS" -eq 0 ]; then echo "All tests passed."; else echo "${FAILS} test(s) failed."; exit 1; fi
