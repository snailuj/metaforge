#!/usr/bin/env bash
# Metaforge enrichment deploy: builds the enricher and installs its unit.
# Idempotent. Run after deploy/production/deploy.sh, which builds the API
# with the ledger and weekly cap the enricher paces itself against.
#
# Usage: ./deploy.sh             install and (re)start
#        ./deploy.sh --no-start  install, and stop it if it was running
#
# Starting it spends real money, up to (weekly cap - reserve) a week.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../lib/api-host.sh
. "${SCRIPT_DIR}/../lib/api-host.sh"
WORKTREE="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SERVICE_NAME="metaforge-enrich"

echo "=== Metaforge Enrichment Deploy ==="
echo "Worktree: ${WORKTREE}"

RESERVE_USD=5 # keep in step with -reserve in the unit

echo "--- Check the API reports a weekly cap above the reserve ---"
if ! BUDGET="$(curl -sf --max-time 5 http://127.0.0.1:8080/forge/budget)"; then
    echo "FAIL: http://127.0.0.1:8080/forge/budget did not answer; deploy production first." >&2
    exit 1
fi
echo "${BUDGET}"
# The enricher refuses an uncapped API, or a cap the reserve swallows, and
# would only restart in a loop.
if ! python3 -c 'import json,sys; sys.exit(0 if json.loads(sys.argv[1]).get("cap_usd", 0) > float(sys.argv[2]) else 1)' \
        "${BUDGET}" "${RESERVE_USD}"; then
    echo "FAIL: the weekly cap must be above the USD ${RESERVE_USD} reserve (METAFORGE_WEEKLY_BUDGET_USD on the API)." >&2
    exit 1
fi

echo "--- Build enricher ---"
export PATH="/usr/local/go/bin:${PATH}"
cd "${WORKTREE}/api"
go build -o enrich ./cmd/enrich
echo "Built: ${WORKTREE}/api/enrich"
install_root_binary "${WORKTREE}/api/enrich" /usr/local/lib/metaforge/enrich/enrich

echo "--- Install service ---"
ensure_service_user
ensure_state_dir
sed "s|__WORKTREE__|${WORKTREE}|g" "${SCRIPT_DIR}/${SERVICE_NAME}.service" \
    | sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"

if [ "${1:-}" = "--no-start" ]; then
    # Also stops a copy already running, so --no-start never leaves one spending.
    sudo systemctl stop "${SERVICE_NAME}"
    echo "Installed, not running. Start with: sudo systemctl start ${SERVICE_NAME}"
    exit 0
fi
sudo systemctl restart "${SERVICE_NAME}"
sleep 2
sudo systemctl status "${SERVICE_NAME}" --no-pager -l | head -20
echo "Follow it with: journalctl -u ${SERVICE_NAME} -f"
