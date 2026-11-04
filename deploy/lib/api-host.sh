#!/usr/bin/env bash
# Host setup shared by the API and enricher deploy scripts. Source, do not execute.
# Every function is safe to re-run after a partial failure. MF_STATE_DIR, MF_KEY_DIR
# and MF_USER exist so deploy/lib/test-api-host.sh can run against a scratch tree.

MF_USER="${MF_USER:-metaforge}"
MF_STATE_DIR="${MF_STATE_DIR:-/var/lib/metaforge}"
MF_KEY_DIR="${MF_KEY_DIR:-/etc/metaforge}"

have_sqlite3() { command -v sqlite3 >/dev/null 2>&1; }

# The units run as a dedicated user so agent's own processes cannot read the
# API key or the ledger. No home, no login shell.
ensure_service_user() {
    if id -u "$MF_USER" >/dev/null 2>&1; then
        echo "User ${MF_USER} exists"
    else
        sudo useradd --system --no-create-home --shell /usr/sbin/nologin --user-group "$MF_USER"
        echo "Created user ${MF_USER}"
    fi
}

# Shared state: ledger, forest caches, enricher state. Earlier deploys created it
# owned by agent, so ownership is corrected recursively.
ensure_state_dir() { # [site]
    sudo install -d -o "$MF_USER" -g "$MF_USER" -m 0750 "$MF_STATE_DIR"
    [ -n "${1:-}" ] && sudo install -d -o "$MF_USER" -g "$MF_USER" -m 0750 "${MF_STATE_DIR}/$1"
    sudo chown -R "${MF_USER}:${MF_USER}" "$MF_STATE_DIR"
    echo "State dir ${MF_STATE_DIR} owned by ${MF_USER}"
}

# systemd reads EnvironmentFile as root before dropping privileges, so the key
# files need no other reader. Absent files are skipped (both are optional).
secure_key_files() { # <file>...
    local f
    for f in "$@"; do
        if sudo test -e "${MF_KEY_DIR}/${f}"; then
            sudo chown root:root "${MF_KEY_DIR}/${f}"
            sudo chmod 0600 "${MF_KEY_DIR}/${f}"
            echo "Key file ${MF_KEY_DIR}/${f} is root:root 0600"
        fi
    done
}

# Restarts a service that a migration stopped. Runs on any exit, so a deploy that
# dies between the stop and its own restart does not leave the site down.
_mf_restart_stopped() {
    if [ -n "${MF_STOPPED_SERVICE:-}" ]; then
        echo "Restarting ${MF_STOPPED_SERVICE} that this run stopped" >&2
        sudo systemctl start "$MF_STOPPED_SERVICE" || true
    fi
}

# Adds _mf_restart_stopped to the EXIT trap once, keeping any trap already set.
_mf_arm_restart() {
    [ -z "${MF_EXIT_ARMED:-}" ] || return 0
    local prev
    prev="$(trap -p EXIT | sed "s/^trap -- '\(.*\)' EXIT\$/\1/")"
    # shellcheck disable=SC2064
    trap "${prev:+${prev}; }_mf_restart_stopped" EXIT
    MF_EXIT_ARMED=1
}

# The state dir is 0750 metaforge, so everything inside it goes through sudo; the old
# db is read as the invoking user, staged in a temp dir, then installed owned by
# MF_USER under a .partial name. Returns non-zero on any failure.
_mf_copy_cache() { # <old> <new>
    local old="$1" new="$2" tmp rc=0
    tmp="$(mktemp -d)" || return 1
    {
        sudo rm -f "${new}.partial" "${new}.partial-wal" "${new}-wal" "${new}-shm" &&
        if have_sqlite3; then
            sqlite3 "$old" ".backup '${tmp}/db'"
        else
            cp "$old" "${tmp}/db" && { [ ! -e "${old}-wal" ] || cp "${old}-wal" "${tmp}/db-wal"; }
        fi &&
        sudo install -o "$MF_USER" -g "$MF_USER" -m 0600 "${tmp}/db" "${new}.partial" &&
        { [ ! -e "${tmp}/db-wal" ] || sudo install -o "$MF_USER" -g "$MF_USER" -m 0600 "${tmp}/db-wal" "${new}.partial-wal"; } &&
        # wal first: an orphan wal is cleared above on the next run, but a db
        # without its wal would look finished and lose rows.
        { ! sudo test -e "${new}.partial-wal" || sudo mv "${new}.partial-wal" "${new}-wal"; } &&
        sudo mv "${new}.partial" "$new"
    } || rc=1
    rm -rf "$tmp"
    return "$rc"
}

# Forest caches used to live in the worktree. Copy the old one to the state dir once:
# stop the service so nothing writes mid-copy, copy under a .partial name and rename,
# so a failed run leaves no file that looks finished. The old file is never deleted.
# If anything fails after the stop the service is started again.
migrate_forest_cache() { # <site> <service> <worktree>
    local site="$1" service="$2" old="$3/data-pipeline/output/forest_cache.db"
    local new="${MF_STATE_DIR}/${site}/forest_cache.db"
    if sudo test -e "$new"; then echo "Forest cache already at ${new}"; return 0; fi
    if [ ! -e "$old" ]; then echo "No old forest cache to migrate"; return 0; fi

    echo "Migrating ${old} -> ${new}"
    MF_STOPPED_SERVICE="$service"
    _mf_arm_restart
    sudo systemctl stop "$service" || return 1
    if ! _mf_copy_cache "$old" "$new"; then
        echo "ERROR: could not copy the forest cache; starting ${service} again" >&2
        sudo systemctl start "$service" || true
        return 1
    fi
    echo "Forest cache migrated"
}

# Binaries that run with the API key live under /usr/local/lib/metaforge, owned by
# root, so a process running as agent (npm scripts, a compromised tool) cannot swap
# them. Written beside the target and renamed: install over a running binary fails
# with "Text file busy".
install_root_binary() { # <src> <dest>
    local src="$1" dest="$2"
    sudo install -d -o root -g root -m 0755 "$(dirname "$dest")"
    sudo install -o root -g root -m 0755 "$src" "${dest}.new"
    sudo mv -f "${dest}.new" "$dest"
    echo "Installed ${dest} (root:root 0755)"
}
