#!/bin/bash
set -euo pipefail

# =============================================================================
# Transfer Claude Code OAuth credentials to VPS
# =============================================================================
# This copies your local OAuth credentials to the VPS so it uses your Max plan.
#
# Usage: ./scripts/setup-claude-auth.sh
#
# Prerequisites:
# - You must be logged into Claude Code locally (run `claude` and complete OAuth)
# - VPS must be deployed
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$(dirname "$SCRIPT_DIR")"

cd "$TF_DIR"

INSTANCE_IP=$(terraform output -raw instance_ip 2>/dev/null) || {
    echo "Error: Could not get instance IP. Is the instance deployed?"
    exit 1
}

LOCAL_CREDS="$HOME/.claude/.credentials.json"

if [[ ! -f "$LOCAL_CREDS" ]]; then
    echo "Error: No local credentials found at $LOCAL_CREDS"
    echo "Run 'claude' locally and complete the OAuth login first."
    exit 1
fi

echo "Transferring Claude Code credentials to VPS..."

# Create .claude directory on VPS
ssh "agent@$INSTANCE_IP" "mkdir -p ~/.claude && chmod 700 ~/.claude"

# Copy credentials (secure permissions)
scp "$LOCAL_CREDS" "agent@$INSTANCE_IP:~/.claude/.credentials.json"
ssh "agent@$INSTANCE_IP" "chmod 600 ~/.claude/.credentials.json"

# Copy settings if they exist
if [[ -f "$HOME/.claude/settings.json" ]]; then
    scp "$HOME/.claude/settings.json" "agent@$INSTANCE_IP:~/.claude/settings.json"
fi

echo ""
echo "Credentials transferred. Testing..."

# Verify Claude Code works
ssh "agent@$INSTANCE_IP" "claude --version" && {
    echo ""
    echo "Claude Code authenticated on VPS using your Max plan."
    echo "Connect with: ./scripts/connect.sh"
}
