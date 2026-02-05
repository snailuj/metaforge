#!/bin/bash
set -euo pipefail

# =============================================================================
# Connect to the agent VPS via SSH
# =============================================================================
# Usage: ./scripts/connect.sh [tmux-session-name]
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$(dirname "$SCRIPT_DIR")"

cd "$TF_DIR"

INSTANCE_IP=$(terraform output -raw instance_ip 2>/dev/null) || {
    echo "Error: Could not get instance IP. Is the instance deployed?"
    exit 1
}

SESSION_NAME="${1:-main}"

echo "Connecting to agent@$INSTANCE_IP..."

# Connect and attach/create tmux session
ssh -t "agent@$INSTANCE_IP" "tmux attach -t $SESSION_NAME 2>/dev/null || tmux new -s $SESSION_NAME"
