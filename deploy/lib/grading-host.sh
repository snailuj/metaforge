#!/usr/bin/env bash
# Host setup for the grading sidecar's own user. Source, do not execute. Each function
# is idempotent. GRADING_USER is overridable for deploy/lib/test-grading-host.sh.

GRADING_USER="${GRADING_USER:-metaforge-grading}"

ensure_grading_user() {
    if id -u "$GRADING_USER" >/dev/null 2>&1; then
        echo "User ${GRADING_USER} exists"
    else
        sudo useradd --system --no-create-home --shell /usr/sbin/nologin --user-group "$GRADING_USER"
        echo "Created user ${GRADING_USER}"
    fi
}

# agent joins the group so its tools can read the data. New membership only reaches
# shells started afterwards; `sudo -u agent -H` picks it up straight away.
ensure_group_member() { # <user>
    if id -nG "$1" | tr ' ' '\n' | grep -qx "$GRADING_USER"; then
        echo "${1} is in group ${GRADING_USER}"
    else
        sudo usermod -aG "$GRADING_USER" "$1"
        echo "Added ${1} to group ${GRADING_USER}"
    fi
}

# The clone belongs to the sidecar user; the group may read, nobody else may.
own_data_clone() { # <clone>
    sudo chown -R "${GRADING_USER}:${GRADING_USER}" "$1"
    sudo chmod -R g+rX,go-w,o-rwx "$1"
    echo "Clone ${1} owned by ${GRADING_USER}, group-readable"
}

# EnvironmentFile= overrides the unit's Environment= for the same key, so keys the
# unit sets itself must not appear in /etc/default/metaforge-grading.
strip_env_keys() { # <file> <KEY>...
    local file="$1" key; shift
    [ -f "$file" ] || return 0
    for key in "$@"; do
        if sudo grep -q "^${key}=" "$file"; then
            sudo sed -i "/^${key}=/d" "$file"
            echo "Stripped ${key} from ${file} (the unit sets it)"
        fi
    done
}

# Run a command as another user with that user's home and group list, so git work on
# agent's repos is done as agent even when a script runs under `sudo` (root-owned
# objects in agent's .git would break its own git later).
as_user() { # <user> <cmd>...
    local u="$1"; shift
    sudo -u "$u" -H "$@"
}

# deploy.sh would switch the unit to the data clone, which does not exist (or holds
# stale data) until migrate-data-clone.sh has moved the verdicts. Refuse unless the
# installed unit already uses the clone, or the migration itself is calling (it sets
# MF_MIGRATING=1).
refuse_unmigrated() { # <installed unit file>
    [ "${MF_MIGRATING:-0}" = 1 ] && return 0
    if sudo grep -q 'worktrees/grading-data' "$1" 2>/dev/null; then
        echo "ERROR: the installed unit still writes grading data to .worktrees/grading-data." >&2
        echo "       Run deploy/grading/migrate-data-clone.sh, which moves the data and then calls this script." >&2
        return 1
    fi
}
