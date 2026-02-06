# VPS Environment Bootstrap Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make custom Claude skills Git-tracked and automatically deployable to any fresh VPS, alongside dotfiles and zsh setup.

**Architecture:** Move the `claude-config` repo from `~/.claude/` to `~/projects/claude-config/` with symlinks back into `~/.claude/skills/`. Add a `bootstrap-env.sh` script to the vultr-agent infra that clones both `dotfiles` and `claude-config` via deploy keys, runs their install scripts, and sets up zsh. Update cloud-init to install zsh and set it as the agent user's shell.

**Tech Stack:** Bash, Git, Terraform/cloud-init, GitHub deploy keys

**Repos touched:**
- `~/projects/claude-config/` (new location — `snailuj/claude-config` on GitHub)
- `~/projects/infra/vultr-agent/` (`snailuj/vultr-agent` on GitHub)
- `~/projects/dotfiles/` (read-only reference — `snailuj/dotfiles` on GitHub)

---

## Task 1: Restructure claude-config repo

Move the repo out of `~/.claude/` into `~/projects/claude-config/` and replace the originals with symlinks.

**Files:**
- Move: `~/.claude/.git/`, `~/.claude/.gitignore` → `~/projects/claude-config/`
- Move: `~/.claude/skills/project-*/`, `~/.claude/skills/user-*/`, `~/.claude/skills/save-narrative-timeline/` → `~/projects/claude-config/skills/`
- Create: symlinks from `~/.claude/skills/<name>` → `~/projects/claude-config/skills/<name>`
- Create: `~/projects/claude-config/install.sh`

**Step 1: Create target directory and move repo + gitignore**

```bash
mkdir -p ~/projects/claude-config
mv ~/.claude/.git ~/projects/claude-config/
mv ~/.claude/.gitignore ~/projects/claude-config/
```

**Step 2: Move custom skill directories into repo**

```bash
mkdir -p ~/projects/claude-config/skills

# Project contexts
for dir in ~/.claude/skills/project-*/; do
    name=$(basename "$dir")
    mv "$dir" ~/projects/claude-config/skills/"$name"
done

# User profile skills
for dir in ~/.claude/skills/user-*/; do
    name=$(basename "$dir")
    mv "$dir" ~/projects/claude-config/skills/"$name"
done

# Other custom
mv ~/.claude/skills/save-narrative-timeline ~/projects/claude-config/skills/
```

**Step 3: Create symlinks back into ~/.claude/skills/**

```bash
for dir in ~/projects/claude-config/skills/*/; do
    name=$(basename "$dir")
    ln -s "$dir" ~/.claude/skills/"$name"
done
```

**Step 4: Verify symlinks resolve and Git is clean**

```bash
ls -la ~/.claude/skills/ | grep '^l'  # Should show ~12 symlinks
cd ~/projects/claude-config && git status  # Should show clean working tree
```

**Step 5: Update .gitignore — simplify now that repo is standalone**

Replace `~/projects/claude-config/.gitignore` with:

```
# Only skills in this repo — no ignoring needed
```

Since the repo is no longer inside `~/.claude/`, the elaborate ignore-everything approach is unnecessary. The repo contains only what we want tracked.

**Step 6: Write install.sh**

Create `~/projects/claude-config/install.sh`:

```bash
#!/bin/bash
set -euo pipefail

# =============================================================================
# Claude Config Installer
# =============================================================================
# Creates symlinks from ~/.claude/skills/ to this repo's skills.
# Safe to re-run — skips existing correct symlinks, warns on conflicts.
#
# Usage: ./install.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SOURCE="$SCRIPT_DIR/skills"
SKILLS_TARGET="$HOME/.claude/skills"

if [[ ! -d "$SKILLS_SOURCE" ]]; then
    echo "Error: No skills directory at $SKILLS_SOURCE"
    exit 1
fi

mkdir -p "$SKILLS_TARGET"

linked=0
skipped=0
warned=0

for dir in "$SKILLS_SOURCE"/*/; do
    name=$(basename "$dir")
    target="$SKILLS_TARGET/$name"

    if [[ -L "$target" ]]; then
        existing=$(readlink -f "$target")
        expected=$(readlink -f "$dir")
        if [[ "$existing" == "$expected" ]]; then
            ((skipped++))
            continue
        else
            echo "WARNING: $target -> $existing (expected $expected)"
            ((warned++))
            continue
        fi
    elif [[ -e "$target" ]]; then
        echo "WARNING: $target exists and is not a symlink — skipping"
        ((warned++))
        continue
    fi

    ln -s "$dir" "$target"
    echo "  Linked: $name"
    ((linked++))
done

echo ""
echo "Done: $linked linked, $skipped already correct, $warned warnings"
```

```bash
chmod +x ~/projects/claude-config/install.sh
```

**Step 7: Commit and push**

```bash
cd ~/projects/claude-config
git add -A
git commit -m "Restructure: standalone repo with install script

Moved out of ~/.claude/ into ~/projects/claude-config/.
Skills are symlinked back into ~/.claude/skills/.
install.sh creates symlinks on any machine."
git push
```

---

## Task 2: Update cloud-init to install zsh

Add `zsh` to the packages list and set the agent user's shell to zsh.

**Files:**
- Modify: `~/projects/infra/vultr-agent/cloud-init.sh`

**Step 1: Add zsh to Essential Packages**

In `cloud-init.sh`, find the `apt-get install -y` block (line 33) and add `zsh` to the list:

```bash
apt-get install -y \
    build-essential \
    curl \
    wget \
    git \
    tmux \
    zsh \
    htop \
    ...
```

**Step 2: Change agent user creation to use zsh**

Change line 71 from:

```bash
useradd -m -s /bin/bash -G sudo agent
```

to:

```bash
useradd -m -s /bin/zsh -G sudo agent
```

**Step 3: Remove the bash aliases block from the agent setup**

Delete the entire `cat >> ~/.bashrc << 'BASHRC'` block (lines 148-171 in the `AGENT_SETUP` heredoc). The dotfiles `install.sh` will handle aliases and shell config.

Also remove the `cat >> ~/.tmux.conf` block (lines 174-182) — dotfiles handles this too.

Replace both blocks with a placeholder comment:

```bash
# Shell config and tmux handled by dotfiles install
echo "Agent user setup complete (shell config deferred to bootstrap)"
```

**Step 4: Commit**

```bash
cd ~/projects/infra/vultr-agent
git add cloud-init.sh
git commit -m "cloud-init: add zsh, defer shell config to dotfiles

Agent user now gets zsh as default shell.
Bash aliases and tmux config removed — handled by dotfiles
bootstrap after first connect."
git push
```

---

## Task 3: Write the VPS bootstrap script

This script runs once after cloud-init, on first connect. It clones dotfiles and claude-config via deploy keys, then runs their install scripts.

**Files:**
- Create: `~/projects/infra/vultr-agent/scripts/bootstrap-env.sh`

**Step 1: Write bootstrap-env.sh**

```bash
#!/bin/bash
set -euo pipefail

# =============================================================================
# Bootstrap VPS Environment
# =============================================================================
# Clones dotfiles and claude-config repos via deploy keys, runs their
# install scripts, and sets up zsh + zplug.
#
# Prerequisites:
#   - Deploy keys set up for both repos (via vultr-sync-project --gh)
#   - zsh installed (via cloud-init)
#
# Usage: Run from local machine:
#   ssh agent@<ip> 'bash -s' < scripts/bootstrap-env.sh
#
# Or after connecting:
#   bash ~/projects/infra/vultr-agent/scripts/bootstrap-env.sh
# =============================================================================

GITHUB_USER="snailuj"

echo "=== VPS Environment Bootstrap ==="
echo ""

# -----------------------------------------------------------------------------
# 1. Clone repos (skip if already cloned)
# -----------------------------------------------------------------------------

clone_if_missing() {
    local repo="$1"
    local dir="$2"
    local ssh_host="github.com-${repo}"

    if [[ -d "$dir/.git" ]]; then
        echo "[OK] $repo already cloned at $dir"
        cd "$dir" && git pull --ff-only 2>/dev/null || true
        return
    fi

    if [[ -d "$dir" ]]; then
        echo "[ERROR] $dir exists but is not a git repo. Remove manually."
        return 1
    fi

    echo "[CLONE] $repo -> $dir"
    mkdir -p "$(dirname "$dir")"
    git clone "git@${ssh_host}:${GITHUB_USER}/${repo}.git" "$dir"
}

clone_if_missing "dotfiles" "$HOME/projects/dotfiles"
clone_if_missing "claude-config" "$HOME/projects/claude-config"

# -----------------------------------------------------------------------------
# 2. Install zplug (zsh plugin manager)
# -----------------------------------------------------------------------------

if [[ ! -d "$HOME/.zplug" ]]; then
    echo ""
    echo "[INSTALL] zplug"
    git clone https://github.com/zplug/zplug "$HOME/.zplug"
else
    echo "[OK] zplug already installed"
fi

# -----------------------------------------------------------------------------
# 3. Run dotfiles installer
# -----------------------------------------------------------------------------

echo ""
echo "=== Running dotfiles install ==="

cd "$HOME/projects/dotfiles"

# The dotfiles install.sh does a lot (pyenv, nvm, vim-plug, etc.)
# We only need the core bits for a VPS agent. Run the relevant parts:
# - Create directories
# - Symlink dotfiles
# - Skip: pyenv, nvm, vim plugins, CoC, fzf (heavyweight, agent doesn't need them)

DOTFILES_DIR="$HOME/projects/dotfiles"

mkdir -p ~/.zsh

# Symlink core dotfiles
ln -sf "$DOTFILES_DIR/.zshrc" "$HOME/.zshrc"
ln -sf "$DOTFILES_DIR/.tmux.conf" "$HOME/.tmux.conf"

# Symlink zsh config files
for f in spaceship.zsh plugins.zsh environment.zsh languages.zsh misc.zsh; do
    if [[ -f "$DOTFILES_DIR/$f" ]]; then
        ln -sf "$DOTFILES_DIR/$f" "$HOME/.zsh/$f"
    fi
done

echo "[OK] Dotfiles symlinked"

# -----------------------------------------------------------------------------
# 4. Run claude-config installer
# -----------------------------------------------------------------------------

echo ""
echo "=== Running claude-config install ==="

mkdir -p "$HOME/.claude/skills"
"$HOME/projects/claude-config/install.sh"

# -----------------------------------------------------------------------------
# 5. Install tmux plugin manager
# -----------------------------------------------------------------------------

if [[ ! -d "$HOME/.tmux/plugins/tpm" ]]; then
    echo ""
    echo "[INSTALL] tmux plugin manager"
    mkdir -p ~/.tmux/plugins
    git clone https://github.com/tmux-plugins/tpm ~/.tmux/plugins/tpm
else
    echo "[OK] TPM already installed"
fi

# -----------------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------------

echo ""
echo "=== Bootstrap complete ==="
echo ""
echo "Next steps:"
echo "  1. Disconnect and reconnect (to get zsh)"
echo "  2. zplug will prompt to install plugins on first shell"
echo "  3. In tmux, press prefix + I to install tmux plugins"
```

```bash
chmod +x ~/projects/infra/vultr-agent/scripts/bootstrap-env.sh
```

**Step 2: Commit**

```bash
cd ~/projects/infra/vultr-agent
git add scripts/bootstrap-env.sh
git commit -m "Add bootstrap-env.sh: dotfiles + claude-config on fresh VPS

Clones both repos via deploy keys, symlinks dotfiles and custom
Claude skills, installs zplug and TPM. Run once after cloud-init."
git push
```

---

## Task 4: Add vultr-bootstrap command to scripts

Create a local convenience command that sets up deploy keys for both repos and then runs the bootstrap remotely.

**Files:**
- Create: `~/projects/infra/vultr-agent/scripts/bootstrap.sh` (the local-side orchestrator)
- Create: symlink `~/.local/bin/vultr-bootstrap` → above

**Step 1: Write the local orchestrator**

```bash
#!/bin/bash
set -euo pipefail

# =============================================================================
# Bootstrap a fresh VPS with dotfiles + claude-config
# =============================================================================
# Sets up deploy keys for both repos, then runs bootstrap-env.sh on the VPS.
#
# Prerequisites:
#   - Terraform deployed (instance exists)
#   - gh CLI authenticated locally
#
# Usage: vultr-bootstrap
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
SYNC_PROJECT="$SCRIPT_DIR/sync-project.sh"

echo "=== VPS Bootstrap ==="
echo ""

# Step 1: Deploy keys + clone for both repos
echo "--- Setting up dotfiles ---"
"$SYNC_PROJECT" --gh snailuj/dotfiles

echo ""
echo "--- Setting up claude-config ---"
"$SYNC_PROJECT" --gh snailuj/claude-config

# Step 2: Run bootstrap on VPS
TF_DIR="$(dirname "$SCRIPT_DIR")"
cd "$TF_DIR"
INSTANCE_IP=$(terraform output -raw instance_ip)

echo ""
echo "--- Running bootstrap on VPS ---"
ssh "agent@$INSTANCE_IP" 'bash -s' < "$SCRIPT_DIR/bootstrap-env.sh"

echo ""
echo "=== Bootstrap complete ==="
echo "Connect: ssh agent@$INSTANCE_IP"
```

```bash
chmod +x ~/projects/infra/vultr-agent/scripts/bootstrap.sh
```

**Step 2: Create symlink**

```bash
ln -sf ~/projects/infra/vultr-agent/scripts/bootstrap.sh ~/.local/bin/vultr-bootstrap
```

**Step 3: Commit**

```bash
cd ~/projects/infra/vultr-agent
git add scripts/bootstrap.sh
git commit -m "Add vultr-bootstrap: one-command VPS environment setup

Orchestrates deploy key creation for dotfiles + claude-config,
then runs bootstrap-env.sh remotely. Symlinked to vultr-bootstrap."
git push
```

---

## Task 5: Update vultr-agent context skill

Update the project context with the new bootstrap workflow.

**Files:**
- Modify: `~/projects/claude-config/skills/project-vultr-agent-context/SKILL.md`

**Step 1: Update the Commands section**

Add to the commands table:

```
vultr-bootstrap                          # Full env setup (deploy keys + dotfiles + skills)
```

**Step 2: Update the Next Steps / Key Decisions**

Replace next steps with current state. Add key decision:
- **Bootstrap-first provisioning** — cloud-init installs packages + zsh, `vultr-bootstrap` handles personalisation (dotfiles, skills, plugins)

**Step 3: Commit and push**

```bash
cd ~/projects/claude-config
git add -A
git commit -m "Update vultr-agent context with bootstrap workflow"
git push
```

---

## Task 6: Verify end-to-end on Claudius

Test the full flow against the existing VPS.

**Step 1: Run bootstrap against Claudius**

```bash
vultr-bootstrap
```

This will:
- Set up deploy key for `dotfiles` (or skip if exists)
- Set up deploy key for `claude-config` (or skip if exists)
- Clone both repos on VPS
- Symlink dotfiles + skills
- Install zplug + TPM

**Step 2: Connect and verify**

```bash
vultr-connect
```

Check:
- `echo $SHELL` → `/bin/zsh` (or `/usr/bin/zsh`)
- `ls -la ~/.zshrc` → symlink to `~/projects/dotfiles/.zshrc`
- `ls -la ~/.claude/skills/project-metaforge-context` → symlink to `~/projects/claude-config/skills/...`
- `cd ~/projects/claude-config && git remote -v` → `snailuj/claude-config`
- `cd ~/projects/dotfiles && git remote -v` → `snailuj/dotfiles`

**Step 3: Test skill editing round-trip**

On VPS:
```bash
cd ~/projects/claude-config
# Make a trivial edit to a skill
echo "# test" >> skills/project-vultr-agent-context/SKILL.md
git add -A && git commit -m "test: verify VPS push"
git push
```

On local:
```bash
cd ~/projects/claude-config
git pull  # Should get the test commit
git log --oneline -3
# Then revert the test
git revert HEAD --no-edit
git push
```

---

## Summary

| Task | What | Where |
|------|------|-------|
| 1 | Move claude-config to standalone repo + symlinks | `~/projects/claude-config/` |
| 2 | Add zsh to cloud-init, remove bash config | `vultr-agent/cloud-init.sh` |
| 3 | Write VPS-side bootstrap script | `vultr-agent/scripts/bootstrap-env.sh` |
| 4 | Write local orchestrator + symlink | `vultr-agent/scripts/bootstrap.sh` |
| 5 | Update project context skill | `claude-config/skills/project-vultr-agent-context/` |
| 6 | End-to-end verification on Claudius | Live test |
