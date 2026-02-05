#!/bin/bash
set -euo pipefail

# =============================================================================
# Sync Claude Code plugins to the agent VPS
# =============================================================================
# Usage: ./scripts/sync-plugins.sh
#
# Syncs plugin cache and configuration so you don't have to reinstall on VPS.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$(dirname "$SCRIPT_DIR")"

cd "$TF_DIR"

INSTANCE_IP=$(terraform output -raw instance_ip 2>/dev/null) || {
    echo "Error: Could not get instance IP. Is the instance deployed?"
    exit 1
}

LOCAL_PLUGINS="$HOME/.claude/plugins"

if [[ ! -d "$LOCAL_PLUGINS" ]]; then
    echo "Error: No plugins directory found at $LOCAL_PLUGINS"
    exit 1
fi

echo "Syncing plugins to agent@$INSTANCE_IP..."

# Ensure remote directory exists
ssh "agent@$INSTANCE_IP" "mkdir -p ~/.claude/plugins"

# Sync plugin configs and cache
rsync -avz --progress \
    "$LOCAL_PLUGINS/" \
    "agent@$INSTANCE_IP:~/.claude/plugins/"

echo ""
echo "Plugins synced."

# Also sync settings.json for plugin enablement
if [[ -f "$HOME/.claude/settings.json" ]]; then
    echo "Syncing settings.json..."
    rsync -avz "$HOME/.claude/settings.json" "agent@$INSTANCE_IP:~/.claude/settings.json"
fi

echo ""
echo "Done. Installed plugins on VPS:"
ssh "agent@$INSTANCE_IP" "cat ~/.claude/plugins/installed_plugins.json | grep -o '\"[^\"]*@claude-plugins-official\"' | sort -u | tr -d '\"'" 2>/dev/null || echo "(could not list)"
