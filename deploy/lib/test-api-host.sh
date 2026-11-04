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

echo "== install_root_binary"
BIN_DIR="${T}/libdir"
cp /bin/sleep "${T}/sleep.v1"; cp /bin/sleep "${T}/sleep.v2"; echo x >> "${T}/sleep.v2"
install_root_binary "${T}/sleep.v1" "${BIN_DIR}/site/prog" >/dev/null
"${BIN_DIR}/site/prog" 30 & PID=$!
install_root_binary "${T}/sleep.v2" "${BIN_DIR}/site/prog" >/dev/null && ok "replaced while running" || fail "could not replace a running binary"
kill "$PID" 2>/dev/null
[ "$(command sudo stat -c '%U:%G %a' "${BIN_DIR}/site/prog")" = "root:root 755" ] && ok "binary is root:root 755" || fail "binary mode wrong"
[ "$(command sudo stat -c '%U:%G %a' "${BIN_DIR}/site")" = "root:root 755" ] && ok "dir is root:root 755" || fail "dir mode wrong"
cmp -s "${T}/sleep.v2" "${BIN_DIR}/site/prog" && ok "new content installed" || fail "old content left"
command sudo rm -rf "$BIN_DIR"

echo "== build_go_checked"
export PATH="/usr/local/go/bin:${PATH}"
GW="${T}/gowt"; mkdir -p "${GW}/api/cmd/prog"
git init -q "$GW"; git -C "$GW" config user.name t; git -C "$GW" config user.email t@invalid
printf 'module example.invalid/prog\n\ngo 1.21\n' > "${GW}/api/go.mod"
printf 'package main\n\nfunc main() {}\n' > "${GW}/api/cmd/prog/main.go"
printf 'api/prog\n' > "${GW}/.gitignore"
git -C "$GW" add -A; git -C "$GW" commit -q -m init
build_go_checked "$GW" prog ./cmd/prog >/dev/null 2>&1 && [ -x "${GW}/api/prog" ] && ok "clean tree builds" || fail "clean tree did not build"
# A poisoned environment must not reach the compiler: the build pins its own flags.
printf 'GOFLAGS=-toolexec=/bin/false\n' > "${T}/goenv"
GOENV="${T}/goenv" GOFLAGS=-toolexec=/bin/false build_go_checked "$GW" prog ./cmd/prog >/dev/null 2>&1 \
    && ok "poisoned GOFLAGS and go env file ignored" || fail "build honoured a poisoned environment"
echo '// edited by an install script' >> "${GW}/api/cmd/prog/main.go"
build_go_checked "$GW" prog ./cmd/prog >/dev/null 2>&1 && fail "built an edited source" || ok "edited tracked file refused"
git -C "$GW" checkout -q -- api
echo 'package main' > "${GW}/api/cmd/prog/extra.go"
build_go_checked "$GW" prog ./cmd/prog >/dev/null 2>&1 && fail "built with an extra file" || ok "untracked source refused"
rm "${GW}/api/cmd/prog/extra.go"
echo '// staged' >> "${GW}/api/go.mod"; git -C "$GW" add api/go.mod
build_go_checked "$GW" prog ./cmd/prog >/dev/null 2>&1 && fail "built a staged go.mod change" || ok "staged change refused"
git -C "$GW" reset -q --hard

MF_STOPPED_SERVICE=   # the migrations above armed the exit restart; nothing is real here
echo ""
if [ "$FAILS" -eq 0 ]; then echo "All tests passed."; else echo "${FAILS} test(s) failed."; exit 1; fi
