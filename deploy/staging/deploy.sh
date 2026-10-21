#!/usr/bin/env bash
# Metaforge staging deploy
# Idempotent: pull -> restore DB -> build Go -> build frontend -> drop Caddy snippet -> reload
#
# Drops a single-site Caddy snippet into /etc/caddy/conf.d/.
# Does NOT own or restart the Caddy service -- the system caddy.service
# imports all snippets via: import /etc/caddy/conf.d/*.caddy
#
# Usage: ./deploy.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKTREE="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CADDY_SNIPPETS="/etc/caddy/conf.d"
DOMAIN="metaforge-next.julianit.me"
API_PORT=8081
SERVICE_NAME="metaforge-api-staging"

echo "=== Metaforge Staging Deploy ==="
echo "Worktree: ${WORKTREE}"
echo "Domain:   ${DOMAIN}"
echo ""

# 1. Pull latest
echo "--- git pull --ff-only ---"
cd "${WORKTREE}"
git pull --ff-only
echo ""

# 2. Restore DB from SQL dump
echo "--- Restore database ---"
"${WORKTREE}/data-pipeline/scripts/restore_db.sh"
echo ""

# 3. Build Go API
echo "--- Build Go API ---"
export PATH="/usr/local/go/bin:${PATH}"
cd "${WORKTREE}/api"
go build -o metaforge ./cmd/metaforge
echo "Built: ${WORKTREE}/api/metaforge"
echo ""

# 4. Build frontend
echo "--- Build frontend ---"
cd "${WORKTREE}/web"
npm ci --prefer-offline
npm run build
echo ""

# 5. Install API systemd service
echo "--- Install API service ---"
sed "s|__WORKTREE__|${WORKTREE}|g" "${SCRIPT_DIR}/metaforge-api-staging.service" \
    | sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null
echo "Installed: ${SERVICE_NAME}.service"

# 6. Drop Caddy snippet
# Grading secrets come from the gitignored ${SCRIPT_DIR}/.env (see .env.example).
# Without them the snippet carries raw placeholders, Caddy rejects it, and the
# broken file on disk would stop Caddy (and every site) on its next restart.
echo "--- Drop Caddy snippet ---"
ENV_FILE="${SCRIPT_DIR}/.env"
if [ ! -f "${ENV_FILE}" ]; then
    echo "ERROR: ${ENV_FILE} missing (copy .env.example and fill it in)" >&2
    exit 1
fi
set -a
# shellcheck source=/dev/null
. "${ENV_FILE}"
set +a
: "${JULIAN_BCRYPT_HASH:?not set in ${ENV_FILE}}"
: "${GRADING_SECRET:?not set in ${ENV_FILE}}"

SNIPPET="${CADDY_SNIPPETS}/metaforge-next.caddy"
sudo cp "${SNIPPET}" "${SNIPPET}.prev" 2>/dev/null || true
sed -e "s|__WORKTREE__|${WORKTREE}|g" \
    -e "s|__JULIAN_BCRYPT_HASH__|${JULIAN_BCRYPT_HASH}|g" \
    -e "s|__GRADING_SECRET__|${GRADING_SECRET}|g" \
    "${SCRIPT_DIR}/metaforge-staging.caddy" \
    | sudo tee "${SNIPPET}" > /dev/null
if sudo grep -q '__[A-Z_]*__' "${SNIPPET}" \
    || ! sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile > /dev/null 2>&1; then
    echo "ERROR: rendered snippet is invalid; restoring previous" >&2
    sudo mv "${SNIPPET}.prev" "${SNIPPET}"
    exit 1
fi
sudo rm -f "${SNIPPET}.prev"
echo "Installed: ${SNIPPET}"
echo ""

# 7. Reload services
echo "--- Reload services ---"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"
sleep 2
sudo caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
echo ""

# 8. Health checks
echo "--- Health checks ---"
PASS=0
FAIL=0

check() {
    local label="$1"
    local url="$2"
    local expect="$3"
    if curl -sf --max-time 5 "$url" | grep -q "$expect"; then
        echo "  PASS: ${label}"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: ${label}"
        FAIL=$((FAIL + 1))
    fi
}

check "API direct"    "http://127.0.0.1:${API_PORT}/health" '"status"'
check "API via Caddy" "https://${DOMAIN}/health"             '"status"'
check "Frontend"      "https://${DOMAIN}/"                   '<!doctype html>'
check "Thesaurus"     "https://${DOMAIN}/thesaurus/lookup?word=happy" '"senses"'

echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed ==="

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "Service status:"
    sudo systemctl status "${SERVICE_NAME}" --no-pager -l || true
    exit 1
fi

echo ""
echo "Staging is live at https://${DOMAIN}/"
