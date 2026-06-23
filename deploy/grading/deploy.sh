#!/usr/bin/env bash
# Deploy ONLY the Metaforge grading sidecar (systemd unit + secret + smoke).
# Idempotent. Fails closed on missing secret file.
# Caddy snippet drop is handled by deploy/staging/deploy.sh — run THAT after this
# if the staging Caddy snippet has changed (T11 added /api/grading/* routing).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# The sidecar runs as `agent` (the repo owner — see metaforge-grading.service
# for why a dedicated user breaks code-read + git-autocommit). The secret file
# is therefore owned by agent.
SIDECAR_USER="${SIDECAR_USER:-agent}"

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

# 3b. The unit pins the deploy worktree via Environment=PYTHONPATH=. Observed
# gotcha: a PYTHONPATH in THIS EnvironmentFile OVERRIDES the unit's inline value at
# runtime (systemd applies EnvironmentFile after Environment= for duplicate keys),
# silently sending the sidecar's code + grading-data resolution back to whatever
# path the file names. Strip it so the unit is the sole authority. Idempotent.
if [ -f /etc/default/metaforge-grading ] && grep -q '^PYTHONPATH=' /etc/default/metaforge-grading; then
    sudo sed -i '/^PYTHONPATH=/d' /etc/default/metaforge-grading
    echo "Stripped PYTHONPATH from /etc/default/metaforge-grading (unit Environment= is authoritative)."
fi

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

# 7. Verify the cutover actually pinned the deploy worktree. paths.py + the git
# autocommit derive code AND grading-data location from PYTHONPATH, so if the live
# process resolves it to anything other than .worktrees/next, the sidecar is
# silently running off the main checkout (the EnvironmentFile gotcha above). Fail
# loudly rather than appear-deployed-but-wrong.
PID="$(pgrep -f 'grading_sidecar.main' | head -1)"
if [ -n "$PID" ] && grep -qz '^PYTHONPATH=.*\.worktrees/next' "/proc/$PID/environ" 2>/dev/null; then
    echo "Verified: live sidecar (PID $PID) PYTHONPATH is pinned to .worktrees/next."
else
    echo "ERROR: sidecar PYTHONPATH is NOT pinned to .worktrees/next — code + grading data" >&2
    echo "       are resolving from the main checkout, not the deploy worktree." >&2
    echo "       Inspect: tr '\\0' '\\n' < /proc/${PID}/environ | grep PYTHONPATH" >&2
    exit 1
fi

echo "Sidecar deploy complete."
echo ""
echo "If the staging Caddy snippet changed (T11 added /api/grading/* handles),"
echo "now run: deploy/staging/deploy.sh"
echo "Then check: curl -fsS https://metaforge-next.julianit.me/api/grading/healthz"
