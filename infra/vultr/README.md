# Metaforge Agent VPS Infrastructure

Terraform configuration for a Vultr VPS optimised for running Claude Code agents in isolation.

## Spec

- **Instance:** 2 vCPU / 4GB RAM / 80GB SSD (~$24/mo)
- **OS:** Ubuntu 24.04 LTS
- **Region:** London (configurable)
- **Purpose:** Isolated environment for batch jobs and autonomous agent work

## Prerequisites

1. [Vultr account](https://www.vultr.com/)
2. API key from Vultr dashboard → Account → API
3. Terraform 1.5+
4. SSH key pair

## Quick Start

```bash
cd infra/vultr

# Set your API key
export VULTR_API_KEY="your-api-key-here"

# Initialise Terraform
terraform init

# Deploy (wait 2-3 min for cloud-init to complete)
terraform apply -var="ssh_public_key=$(cat ~/.ssh/id_ed25519.pub)"

# Connect and authenticate Claude Code
./scripts/connect.sh
claude  # Follow device auth flow - open URL in browser, paste code back

# Sync your project, skills, and plugins
./scripts/sync-all.sh
```

## Authentication: Max Plan vs API Key

### Using Max Plan (Recommended)

Claude Code supports device auth flow for headless servers. On the VPS:

```bash
claude
# It will display a URL - open it in your local browser
# Complete OAuth login
# Paste the code back into the VPS terminal
```

This authenticates directly with your Max plan quota.

### Using API Key (Alternative)

If you prefer separate billing:

```bash
# On the VPS
export ANTHROPIC_API_KEY="sk-ant-..."
```

This charges against API credits, not your Max quota.

## Sync Scripts

```bash
# Sync project files (excludes .venv, node_modules, large embeddings)
./scripts/sync-project.sh

# Sync Claude skills
./scripts/sync-skills.sh              # All skills
./scripts/sync-skills.sh --metaforge-only  # Exclude unrelated project contexts

# Sync Claude plugins (superpowers, context7, etc.)
./scripts/sync-plugins.sh

# Sync everything
./scripts/sync-all.sh
```

## What Gets Installed

The cloud-init script provisions:

- **Python 3.12** with pip, venv
- **Go 1.22**
- **Node.js 20 LTS** (for Claude Code)
- **Claude Code CLI** (via npm)
- **SQLite 3**
- **Git** configured for worktrees
- **tmux** for persistent sessions
- **Dedicated `agent` user** with sudo access

## Security Model

- SSH key-only authentication (no passwords)
- UFW firewall: only ports 22 (SSH) open
- Fail2ban for brute-force protection
- Automatic security updates enabled
- No access to your personal laptop

## Destroying

```bash
terraform destroy -var="ssh_public_key=$(cat ~/.ssh/id_ed25519.pub)"
```

## Snapshots

Before experiments, snapshot the instance:

```bash
# Via Vultr CLI or dashboard
vultr-cli snapshot create --instance-id=$(terraform output -raw instance_id)
```

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `connect.sh` | SSH into VPS with tmux session |
| `setup-claude-auth.sh` | Transfer local OAuth credentials (fallback) |
| `sync-project.sh` | Rsync metaforge project to VPS |
| `sync-skills.sh` | Rsync Claude skills to VPS |
| `sync-plugins.sh` | Rsync Claude plugins to VPS |
| `sync-all.sh` | Run all sync scripts |
