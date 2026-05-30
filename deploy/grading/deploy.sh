#!/usr/bin/env bash
# Deploy the Metaforge grading sidecar + patched metaforge-next Caddy snippet.
# Idempotent. Fails closed on missing secrets.
set -euo pipefail

: "${JULIAN_BCRYPT_HASH:?must be set in /etc/default/caddy (or in shell env)}"
: "${GRADING_SECRET:?must be set in /etc/default/caddy (or in shell env)}"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# 1. Render Caddy snippet (T11 lands the .template; if absent, error)
if [ ! -f "$REPO_ROOT/deploy/caddy/metaforge-next.caddy.template" ]; then
    echo "ERROR: deploy/caddy/metaforge-next.caddy.template not found (T11 pending?)" >&2
    exit 1
fi
envsubst < "$REPO_ROOT/deploy/caddy/metaforge-next.caddy.template" \
    | sudo tee /etc/caddy/conf.d/metaforge-next.caddy.active >/dev/null

# 2. Validate before reload
sudo caddy validate --config /etc/caddy/Caddyfile

# 3. Install systemd unit (idempotent — overwrites)
sudo install -m 0644 "$REPO_ROOT/deploy/grading/metaforge-grading.service" \
    /etc/systemd/system/metaforge-grading.service
sudo systemctl daemon-reload

# 4. Ensure secret-file path exists with 0700 dir
sudo install -d -m 0700 /etc/metaforge
if [ ! -f /etc/metaforge/grading_secret ]; then
    echo "ERROR: /etc/metaforge/grading_secret does not exist." >&2
    echo "Create it manually:" >&2
    echo "  echo -n '<secret>' | sudo tee /etc/metaforge/grading_secret" >&2
    echo "  sudo chmod 600 /etc/metaforge/grading_secret" >&2
    exit 1
fi
sudo chmod 0600 /etc/metaforge/grading_secret

# 5. Apply
sudo systemctl reload caddy
sudo systemctl enable --now metaforge-grading
sudo systemctl restart metaforge-grading

# 6. Smoke (local + via Caddy)
sleep 2
curl -fsS http://127.0.0.1:53775/api/grading/healthz
curl -fsS https://metaforge-next.julianit.me/api/grading/healthz

# 7. Auth smoke — wrong basic-auth must 401
if curl -fsS -u julian:WRONGPASS https://metaforge-next.julianit.me/api/grading/stats; then
    echo "FAIL: auth bypass (wrong-pass returned 200)" >&2
    exit 1
fi
echo "OK: auth smoke (401 on wrong creds)"

echo "Deploy complete."
