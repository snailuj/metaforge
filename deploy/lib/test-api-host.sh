#!/usr/bin/env bash
# Tests for deploy/lib/api-host.sh, run against a scratch tree with sudo,
# systemctl and chown faked, so nothing real is touched:  deploy/lib/test-api-host.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
LOG="${T}/calls.log"
: > "$LOG"

# Faked privileged commands: log them, and only run what is safe unprivileged.
sudo() {
    case "$1" in
        chown|chmod|useradd) echo "sudo $*" >> "$LOG" ;;
        systemctl)           echo "sudo $*" >> "$LOG" ;;
        stat)                shift; stat "$@" ;;
        install)             shift; a=(); while [ $# -gt 0 ]; do case "$1" in -o|-g) shift 2 ;; *) a+=("$1"); shift ;; esac; done
                             install "${a[@]}" ;;
        *)                   "$@" ;;
    esac
}

export MF_STATE_DIR="${T}/state" MF_KEY_DIR="${T}/etc" MF_USER=mf-test-absent-user
mkdir -p "$MF_STATE_DIR" "$MF_KEY_DIR"
# shellcheck source=api-host.sh
. "${HERE}/api-host.sh"

FAILS=0
ok()   { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILS=$((FAILS + 1)); }
expect_log()  { if grep -qF -- "$1" "$LOG"; then ok "logged: $1"; else fail "not logged: $1"; fi; }
expect_nolog(){ if grep -qF -- "$1" "$LOG"; then fail "unexpectedly logged: $1"; else ok "not logged: $1"; fi; }

echo "== ensure_service_user"
ensure_service_user >/dev/null
expect_log "useradd --system --no-create-home --shell /usr/sbin/nologin --user-group mf-test-absent-user"
: > "$LOG"; MF_USER=root ensure_service_user >/dev/null
expect_nolog "useradd"

echo "== ensure_state_dir"
: > "$LOG"
ensure_state_dir production >/dev/null
[ -d "${MF_STATE_DIR}/production" ] && ok "site dir created" || fail "site dir missing"
expect_log "chown -R mf-test-absent-user:mf-test-absent-user ${MF_STATE_DIR}"

echo "== secure_key_files"
: > "$LOG"; touch "${MF_KEY_DIR}/forest.env"
secure_key_files forest.env forest-staging.env >/dev/null
expect_log "chown root:root ${MF_KEY_DIR}/forest.env"
expect_log "chmod 0600 ${MF_KEY_DIR}/forest.env"
expect_nolog "forest-staging.env"

echo "== migrate_forest_cache"
WT="${T}/wt"; mkdir -p "${WT}/data-pipeline/output"
OLD="${WT}/data-pipeline/output/forest_cache.db"
NEW="${MF_STATE_DIR}/production/forest_cache.db"

: > "$LOG"; migrate_forest_cache production svc "$WT" >/dev/null
[ ! -e "$NEW" ] && expect_nolog "systemctl stop" || fail "created a cache from nothing"

sqlite3 "$OLD" "PRAGMA journal_mode=WAL; CREATE TABLE f(x); INSERT INTO f VALUES (1),(2);" >/dev/null
: > "$LOG"; migrate_forest_cache production svc "$WT" >/dev/null
[ "$(sqlite3 "$NEW" 'SELECT count(*) FROM f')" = 2 ] && ok "rows copied" || fail "rows not copied"
expect_log "systemctl stop svc"
expect_log "chown mf-test-absent-user:mf-test-absent-user ${NEW}"
[ -e "$OLD" ] && ok "old cache kept" || fail "old cache deleted"
ls "${MF_STATE_DIR}/production" | grep -q partial && fail "partial file left" || ok "no partial file left"

echo "== migrate_forest_cache is idempotent"
sqlite3 "$NEW" "INSERT INTO f VALUES (3)"
: > "$LOG"; migrate_forest_cache production svc "$WT" >/dev/null
[ "$(sqlite3 "$NEW" 'SELECT count(*) FROM f')" = 3 ] && ok "existing cache not overwritten" || fail "existing cache overwritten"
expect_nolog "systemctl stop"

echo "== migrate_forest_cache recovers from a half-finished copy"
rm -f "$NEW"; echo junk > "${NEW}.partial"
migrate_forest_cache production svc "$WT" >/dev/null
[ "$(sqlite3 "$NEW" 'SELECT count(*) FROM f')" = 2 ] && ok "stale partial replaced" || fail "stale partial used"

echo "== migrate_forest_cache without sqlite3 copies the db and its wal"
rm -f "$NEW"
have_sqlite3() { return 1; }
echo wal-bytes > "${OLD}-wal"
migrate_forest_cache production svc "$WT" >/dev/null
[ -s "$NEW" ] && ok "db copied" || fail "db not copied"
[ "$(cat "${NEW}-wal" 2>/dev/null)" = wal-bytes ] && ok "wal copied" || fail "wal not copied"

echo ""
if [ "$FAILS" -eq 0 ]; then echo "All tests passed."; else echo "${FAILS} test(s) failed."; exit 1; fi
