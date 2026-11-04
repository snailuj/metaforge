#!/usr/bin/env bash
# Metaforge enrichment deploy: builds the enricher and installs its unit.
# Idempotent. Run after deploy/production/deploy.sh, which builds the API
# with the ledger and weekly cap the enricher paces itself against.
#
# Usage: ./deploy.sh          install and (re)start
#        ./deploy.sh --no-start  install only
#
# Starting it spends real money, up to (weekly cap - reserve) a week.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKTREE="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SERVICE_NAME="metaforge-enrich"

echo "=== Metaforge Enrichment Deploy ==="
echo "Worktree: ${WORKTREE}"

echo "--- Check the API reports a weekly cap ---"
if ! curl -sf --max-time 5 http://127.0.0.1:8080/forge/budget | grep -q '"cap_usd"'; then
    echo "FAIL: http://127.0.0.1:8080/forge/budget did not answer; deploy production first." >&2
    exit 1
fi
curl -s http://127.0.0.1:8080/forge/budget; echo

echo "--- Build enricher ---"
export PATH="/usr/local/go/bin:${PATH}"
cd "${WORKTREE}/api"
go build -o enrich ./cmd/enrich
echo "Built: ${WORKTREE}/api/enrich"

echo "--- Install service ---"
sudo install -d -o agent -g agent -m 0750 /var/lib/metaforge
sed "s|__WORKTREE__|${WORKTREE}|g" "${SCRIPT_DIR}/${SERVICE_NAME}.service" \
    | sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"

if [ "${1:-}" = "--no-start" ]; then
    echo "Installed, not started. Start with: sudo systemctl start ${SERVICE_NAME}"
    exit 0
fi
sudo systemctl restart "${SERVICE_NAME}"
sleep 2
sudo systemctl status "${SERVICE_NAME}" --no-pager -l | head -20
echo "Follow it with: journalctl -u ${SERVICE_NAME} -f"
