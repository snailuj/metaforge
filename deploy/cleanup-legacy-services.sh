#!/usr/bin/env bash
# One-time cleanup: disable legacy Caddy services that compete with system caddy.service
#
# After running this, only caddy.service (the system package unit) manages Caddy.
# Metaforge deploy scripts drop snippets into /etc/caddy/conf.d/ and reload.
#
# Safe to run multiple times (idempotent).

set -euo pipefail

echo "=== Legacy Service Cleanup ==="

for svc in julianit-caddy metaforge-caddy; do
    if systemctl list-unit-files "${svc}.service" &>/dev/null; then
        echo "Disabling ${svc}.service..."
        sudo systemctl stop "${svc}" 2>/dev/null || true
        sudo systemctl disable "${svc}" 2>/dev/null || true
        echo "  Stopped and disabled."
    else
        echo "  ${svc}.service not found, skipping."
    fi
done

echo ""
echo "Verifying caddy.service is the sole Caddy process..."
if systemctl is-active --quiet caddy; then
    echo "  caddy.service: active"
else
    echo "  WARNING: caddy.service is not running. Start it with: sudo systemctl start caddy"
fi

echo ""
echo "Done. Only caddy.service should manage Caddy from now on."
