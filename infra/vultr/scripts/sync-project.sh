#!/bin/bash
set -euo pipefail

# =============================================================================
# Sync Metaforge project to the agent VPS
# =============================================================================
# Usage: ./scripts/sync-project.sh
# Requires: terraform output available (instance must be deployed)
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(cd "$TF_DIR/../.." && pwd)"

cd "$TF_DIR"

# Get instance IP from Terraform
INSTANCE_IP=$(terraform output -raw instance_ip 2>/dev/null) || {
    echo "Error: Could not get instance IP. Is the instance deployed?"
    echo "Run: terraform apply"
    exit 1
}

echo "Syncing to agent@$INSTANCE_IP..."

# Sync project (excluding large/sensitive files)
rsync -avz --progress \
    --exclude '.git' \
    --exclude '.venv' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude 'node_modules' \
    --exclude '.terraform' \
    --exclude '*.tfstate*' \
    --exclude 'data-pipeline/output/*.vec' \
    --exclude 'data-pipeline/output/*.bin' \
    --exclude 'data-pipeline/output/*.idx' \
    --exclude 'data-pipeline/output/*.zip' \
    "$PROJECT_ROOT/" \
    "agent@$INSTANCE_IP:~/projects/metaforge/"

echo "Sync complete. Connect with:"
echo "  ssh agent@$INSTANCE_IP"
echo "  cd ~/projects/metaforge"
