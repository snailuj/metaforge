#!/bin/bash
set -euo pipefail

# =============================================================================
# Sync everything to the agent VPS
# =============================================================================
# Usage: ./scripts/sync-all.sh
#
# Syncs: project files, skills, plugins
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Syncing Project ==="
"$SCRIPT_DIR/sync-project.sh"

echo ""
echo "=== Syncing Skills ==="
"$SCRIPT_DIR/sync-skills.sh" --metaforge-only

echo ""
echo "=== Syncing Plugins ==="
"$SCRIPT_DIR/sync-plugins.sh"

echo ""
echo "=== All synced ==="
