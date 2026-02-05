#!/bin/bash
set -euo pipefail

# =============================================================================
# Sync Claude Code skills to the agent VPS
# =============================================================================
# Usage: ./scripts/sync-skills.sh [--all | --metaforge-only]
#
# Options:
#   --all             Sync all skills (default)
#   --metaforge-only  Only sync metaforge-related and general skills
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$(dirname "$SCRIPT_DIR")"

cd "$TF_DIR"

MODE="${1:---all}"

INSTANCE_IP=$(terraform output -raw instance_ip 2>/dev/null) || {
    echo "Error: Could not get instance IP. Is the instance deployed?"
    exit 1
}

LOCAL_SKILLS="$HOME/.claude/skills"

if [[ ! -d "$LOCAL_SKILLS" ]]; then
    echo "Error: No skills directory found at $LOCAL_SKILLS"
    exit 1
fi

echo "Syncing skills to agent@$INSTANCE_IP..."

# Ensure remote directory exists
ssh "agent@$INSTANCE_IP" "mkdir -p ~/.claude/skills"

if [[ "$MODE" == "--metaforge-only" ]]; then
    echo "Mode: metaforge-only (excluding unrelated project contexts)"

    # Sync everything except non-metaforge project contexts
    rsync -avz --progress \
        --exclude 'project-digital-garden-context' \
        --exclude 'project-k-st-massive-context' \
        --exclude 'project-tasks-management-context' \
        --exclude 'project-tnb-context' \
        --exclude 'project-zettelkasten-migration-context' \
        "$LOCAL_SKILLS/" \
        "agent@$INSTANCE_IP:~/.claude/skills/"
else
    echo "Mode: all skills"

    rsync -avz --progress \
        "$LOCAL_SKILLS/" \
        "agent@$INSTANCE_IP:~/.claude/skills/"
fi

echo ""
echo "Skills synced. Listing remote skills:"
ssh "agent@$INSTANCE_IP" "ls ~/.claude/skills/"
