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

# Forest caches used to live in the worktree. Copy the old one to the state dir once:
# stop the service so nothing writes mid-copy, copy to a .partial name and rename, so
# a failed run leaves no file that looks finished. The old file is never deleted.
migrate_forest_cache() { # <site> <service> <worktree>
    local site="$1" service="$2" old="$3/data-pipeline/output/forest_cache.db"
    local new="${MF_STATE_DIR}/${site}/forest_cache.db"
    if [ -e "$new" ]; then echo "Forest cache already at ${new}"; return 0; fi
    if [ ! -e "$old" ]; then echo "No old forest cache to migrate"; return 0; fi

    echo "Migrating ${old} -> ${new}"
    sudo systemctl stop "$service"
    rm -f "${new}.partial" "${new}.partial-wal" "${new}-wal" "${new}-shm"
    if have_sqlite3; then
        sqlite3 "$old" ".backup '${new}.partial'"
    else
        cp "$old" "${new}.partial"
        [ -e "${old}-wal" ] && cp "${old}-wal" "${new}.partial-wal"
    fi
    # wal first: an orphan wal is cleared above on the next run, a db without
    # its wal would look finished and lose rows.
    [ -e "${new}.partial-wal" ] && mv "${new}.partial-wal" "${new}-wal"
    mv "${new}.partial" "$new"
    local f
    for f in "$new" "${new}-wal"; do
        [ -e "$f" ] && sudo chown "${MF_USER}:${MF_USER}" "$f"
    done
    return 0
}
