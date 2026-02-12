#!/usr/bin/env bash
# Metaforge staging deploy script
# Idempotent: pull → restore DB → build Go → build frontend → install services → verify
#
# Usage: ./deploy.sh
#   Run from any worktree — auto-detects paths from script location.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKTREE="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "=== Metaforge Staging Deploy ==="
echo "Worktree: ${WORKTREE}"
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

# 5. Generate config files from templates (substitute __WORKTREE__)
echo "--- Generate config files ---"
sed "s|__WORKTREE__|${WORKTREE}|g" "${SCRIPT_DIR}/Caddyfile" > "${SCRIPT_DIR}/Caddyfile.active"
echo "Generated: ${SCRIPT_DIR}/Caddyfile.active"

sed "s|__WORKTREE__|${WORKTREE}|g" "${SCRIPT_DIR}/metaforge-api.service" \
    | sudo tee /etc/systemd/system/metaforge-api.service > /dev/null
echo "Installed: metaforge-api.service"

sed "s|__WORKTREE__|${WORKTREE}|g" "${SCRIPT_DIR}/metaforge-caddy.service" \
    | sudo tee /etc/systemd/system/metaforge-caddy.service > /dev/null
echo "Installed: metaforge-caddy.service"
echo ""

# 6. Reload systemd and start services
echo "--- Start services ---"
sudo systemctl daemon-reload
sudo systemctl enable metaforge-api metaforge-caddy
sudo systemctl restart metaforge-api
sleep 2
sudo systemctl restart metaforge-caddy
sleep 1
echo ""

# 7. Health checks
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

check "API direct"      "http://127.0.0.1:8080/health"       '"status"'
check "API via Caddy"   "http://127.0.0.1:3000/health"       '"status"'
check "Frontend"        "http://127.0.0.1:3000/"             '<!doctype html>'
check "Thesaurus"       "http://127.0.0.1:3000/thesaurus/lookup?word=happy" '"senses"'

echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed ==="

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "Service status:"
    sudo systemctl status metaforge-api --no-pager -l || true
    echo "---"
    sudo systemctl status metaforge-caddy --no-pager -l || true
    exit 1
fi

echo ""
echo "Staging is live at http://45.32.60.40:3000/"
