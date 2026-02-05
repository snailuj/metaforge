#!/bin/bash
set -euo pipefail

# =============================================================================
# Metaforge Agent VPS Setup
# =============================================================================
# This script runs on first boot via Vultr startup scripts.
# It provisions a development environment for Claude Code agents.
# =============================================================================

LOG_FILE="/var/log/metaforge-setup.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Metaforge Agent Setup Started: $(date) ==="

# -----------------------------------------------------------------------------
# System Updates
# -----------------------------------------------------------------------------

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get upgrade -y

# Enable automatic security updates
apt-get install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades

# -----------------------------------------------------------------------------
# Essential Packages
# -----------------------------------------------------------------------------

apt-get install -y \
    build-essential \
    curl \
    wget \
    git \
    tmux \
    htop \
    jq \
    sqlite3 \
    ripgrep \
    fd-find \
    tree \
    unzip \
    ca-certificates \
    gnupg \
    fail2ban \
    ufw

# -----------------------------------------------------------------------------
# Firewall
# -----------------------------------------------------------------------------

ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw --force enable

# -----------------------------------------------------------------------------
# Fail2ban
# -----------------------------------------------------------------------------

systemctl enable fail2ban
systemctl start fail2ban

# -----------------------------------------------------------------------------
# Create Agent User
# -----------------------------------------------------------------------------

useradd -m -s /bin/bash -G sudo agent

# Copy SSH keys from root to agent user
mkdir -p /home/agent/.ssh
cp /root/.ssh/authorized_keys /home/agent/.ssh/
chown -R agent:agent /home/agent/.ssh
chmod 700 /home/agent/.ssh
chmod 600 /home/agent/.ssh/authorized_keys

# Passwordless sudo for agent
echo "agent ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/agent

# -----------------------------------------------------------------------------
# Python 3.12
# -----------------------------------------------------------------------------

add-apt-repository -y ppa:deadsnakes/ppa
apt-get update
apt-get install -y python3.12 python3.12-venv python3.12-dev python3-pip

update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
update-alternatives --set python3 /usr/bin/python3.12

# -----------------------------------------------------------------------------
# Go 1.22
# -----------------------------------------------------------------------------

GO_VERSION="1.22.5"
wget -q "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" -O /tmp/go.tar.gz
tar -C /usr/local -xzf /tmp/go.tar.gz
rm /tmp/go.tar.gz

# Add Go to PATH for all users
cat >> /etc/profile.d/go.sh << 'EOF'
export PATH=$PATH:/usr/local/go/bin
export GOPATH=$HOME/go
export PATH=$PATH:$GOPATH/bin
EOF

# -----------------------------------------------------------------------------
# Node.js 20 LTS
# -----------------------------------------------------------------------------

curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# -----------------------------------------------------------------------------
# Claude Code CLI
# -----------------------------------------------------------------------------

npm install -g @anthropic-ai/claude-code

# -----------------------------------------------------------------------------
# Agent User Environment
# -----------------------------------------------------------------------------

su - agent << 'AGENT_SETUP'
set -euo pipefail

# Source Go paths
source /etc/profile.d/go.sh

# Create project directory
mkdir -p ~/projects

# Git config
git config --global init.defaultBranch main
git config --global pull.rebase true

# Claude Code directory
mkdir -p ~/.claude

# Bash aliases
cat >> ~/.bashrc << 'BASHRC'

# Metaforge Agent Aliases
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'
alias gs='git status'
alias gd='git diff'
alias gl='git log --oneline -20'

# Python
alias python=python3
alias pip='python3 -m pip'

# tmux
alias ta='tmux attach -t'
alias tn='tmux new -s'
alias tl='tmux ls'

# Claude Code
alias cc='claude'

export EDITOR=vim
BASHRC

# tmux config for persistent sessions
cat >> ~/.tmux.conf << 'TMUX'
set -g mouse on
set -g history-limit 50000
set -g default-terminal "screen-256color"
set -g status-bg colour235
set -g status-fg white
set -g status-left '[#S] '
set -g status-right '%H:%M %d-%b'
TMUX

echo "Agent user setup complete"
AGENT_SETUP

# -----------------------------------------------------------------------------
# Disable root SSH login (security hardening)
# -----------------------------------------------------------------------------

sed -i 's/^PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart sshd

# -----------------------------------------------------------------------------
# Cleanup
# -----------------------------------------------------------------------------

apt-get autoremove -y
apt-get clean

echo "=== Metaforge Agent Setup Complete: $(date) ==="
echo "SSH as: ssh agent@<instance-ip>"
