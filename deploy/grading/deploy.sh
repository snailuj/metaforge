#!/usr/bin/env bash
# Deploy ONLY the Metaforge grading sidecar (systemd unit + secret + smoke).
# Idempotent. Fails closed on missing secret file.
# Caddy snippet drop is handled by deploy/staging/deploy.sh — run THAT after this
# if the staging Caddy snippet has changed (T11 added /api/grading/* routing).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../lib/grading-host.sh
. "${REPO_ROOT}/deploy/lib/grading-host.sh"

# The sidecar runs as metaforge-grading (see the unit). agent owns the code, the venv
# and the secret file: systemd reads the secret as root (LoadCredential) and hands it
# to the unit, so agent's tools can still read it too.
SIDECAR_USER="${SIDECAR_USER:-agent}"

# The unit pins its code and venv to .worktrees/next, so only that checkout can
# build the right venv. (ALLOW_ANY_CHECKOUT=1 skips this, for a trial install.)
LIVE_CODE=/home/agent/projects/metaforge/.worktrees/next
if [ "${ALLOW_ANY_CHECKOUT:-0}" != 1 ] && [ "$REPO_ROOT" != "$LIVE_CODE" ]; then
    echo "ERROR: run this from ${LIVE_CODE} (merged and pulled), not ${REPO_ROOT}." >&2
    exit 1
fi

# The data lives in a standalone clone outside the repo (see the unit). Without it
# the unit's BindPaths= fails the start, so fail here with the fix instead.
DATA_CLONE=/home/agent/projects/metaforge-grading-data
if [ ! -d "${DATA_CLONE}/.git" ]; then
    echo "ERROR: ${DATA_CLONE} is not a git clone yet. Run deploy/grading/migrate-data-clone.sh first." >&2
    exit 1
fi

# The sidecar's own user owns the clone; agent gets read access through the group.
ensure_grading_user
ensure_group_member "$SIDECAR_USER"
own_data_clone "$DATA_CLONE"

# Own hashed venv (idempotent); built before the unit that points at it restarts.
# Run as the sidecar user even under `sudo deploy.sh`, so the venv and uv's cache
# are not left root-owned in agent's tree.
if [ "$(id -u)" -eq 0 ]; then
    sudo -u "$SIDECAR_USER" -H "$REPO_ROOT/deploy/grading/build-venv.sh"
else
    "$REPO_ROOT/deploy/grading/build-venv.sh"
fi

# 1. Ensure secret-file path exists. Dir is 0711 (NOT 0700): agent must traverse
# this root-owned dir to read its own 0600 secret by exact path; 0700 blocks the
# traversal → PermissionError. 0711 allows traversal without enumeration.
sudo install -d -m 0711 -o root -g root /etc/metaforge
if [ ! -f /etc/metaforge/grading_secret ]; then
    echo "ERROR: /etc/metaforge/grading_secret does not exist." >&2
    echo "Create it manually (and match the GRADING_SECRET in the rendered Caddy snippet):" >&2
    echo "  openssl rand -hex 32 | sudo tee /etc/metaforge/grading_secret >/dev/null" >&2
    echo "  sudo chmod 600 /etc/metaforge/grading_secret" >&2
    echo "  sudo chown ${SIDECAR_USER}:${SIDECAR_USER} /etc/metaforge/grading_secret" >&2
    exit 1
fi
sudo chmod 0600 /etc/metaforge/grading_secret
sudo chown "${SIDECAR_USER}:${SIDECAR_USER}" /etc/metaforge/grading_secret

# 3. Ensure /etc/default/metaforge-grading exists (operator populates).
if [ ! -f /etc/default/metaforge-grading ]; then
    sudo install -m 0640 "$REPO_ROOT/deploy/grading/metaforge-grading.env.example" \
        /etc/default/metaforge-grading
    echo "Wrote /etc/default/metaforge-grading from template. Review and adjust if needed."
fi

# 3b. EnvironmentFile= OVERRIDES the unit's inline Environment= for the same key
# (observed with PYTHONPATH: it silently sent the sidecar's code and data resolution
# back to whatever path the file named). The unit is the sole authority for these
# keys, including the secret path, which must stay the systemd credential.
strip_env_keys /etc/default/metaforge-grading PYTHONPATH GRADING_SECRET_FILE GRADING_DATA_DIR GRADING_DATA_GIT_ROOT

# 4. Install systemd unit (idempotent — overwrites).
sudo install -m 0644 "$REPO_ROOT/deploy/grading/metaforge-grading.service" \
    /etc/systemd/system/metaforge-grading.service
sudo systemctl daemon-reload

# 5. Apply.
sudo systemctl enable --now metaforge-grading
sudo systemctl restart metaforge-grading

# 6. Local smoke (sidecar reachable on loopback).
sleep 2
curl -fsS http://127.0.0.1:53775/api/grading/healthz
echo ""

# 7. Verify the process actually runs with the intended environment. The sidecar's
# user differs from ours, so its environ is read through sudo. paths.py and the git
# autocommit derive code and data locations from these variables, so a wrong value
# means it is silently running off another checkout.
PID="$(systemctl show -p MainPID --value metaforge-grading)"
if [ -z "$PID" ] || [ "$PID" = 0 ]; then
    echo "ERROR: metaforge-grading has no running main process after the restart." >&2
    echo "       Inspect: journalctl -u metaforge-grading -n 50 --no-pager" >&2
    exit 1
fi
ENVIRON="$(sudo cat "/proc/${PID}/environ" | tr '\0' '\n')"
check_env() { # <regex> <what>
    if grep -q "$1" <<<"$ENVIRON"; then
        echo "Verified: sidecar (PID ${PID}) $2"
    else
        echo "ERROR: sidecar (PID ${PID}) environment is wrong: $2 failed." >&2
        exit 1
    fi
}
check_env '^PYTHONPATH=.*\.worktrees/next' "PYTHONPATH is pinned to .worktrees/next"
check_env "^GRADING_DATA_GIT_ROOT=${DATA_CLONE}\$" "writes grading data to ${DATA_CLONE}"
check_env '^GRADING_SECRET_FILE=/run/credentials/metaforge-grading.service/' "reads its secret from the systemd credential"
if [ "$(sudo stat -c %U "/proc/${PID}")" = "metaforge-grading" ]; then
    echo "Verified: sidecar runs as metaforge-grading."
else
    echo "ERROR: sidecar is not running as metaforge-grading." >&2
    exit 1
fi

echo "Sidecar deploy complete."
echo ""
echo "If the staging Caddy snippet changed (T11 added /api/grading/* handles),"
echo "now run: deploy/staging/deploy.sh"
echo "Then check: curl -fsS https://metaforge-next.julianit.me/api/grading/healthz"
