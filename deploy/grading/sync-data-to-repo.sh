#!/usr/bin/env bash
# Fast-forward the main repo's grading-data branch to the data clone's tip, so
# verdicts that now live in the standalone clone still reach the repo.
#
#   deploy/grading/sync-data-to-repo.sh
#
# Idempotent; safe from cron as any user with sudo to agent. The repo is touched as
# its owner (agent), never as root, and only the grading-data ref changes: the clone
# is fetched into a side ref first. Needs agent to be in group metaforge-grading
# (deploy.sh adds it), because the clone is owned by the sidecar's user.
# Refuses if the branch is checked out in a worktree (git would desync that
# worktree); the migration detaches the old data worktree for this reason.
set -euo pipefail

SRC_REPO="${MF_SRC_REPO:-/home/agent/projects/metaforge}"
CLONE="${MF_CLONE:-/home/agent/projects/metaforge-grading-data}"
BRANCH=grading-data
SIDE_REF="refs/grading-clone/${BRANCH}"
OWNER="$(stat -c %U "$SRC_REPO")"

agit() { sudo -u "$OWNER" -H git -C "$SRC_REPO" "$@"; }

[ -d "${CLONE}/.git" ] || { echo "ERROR: ${CLONE} is not a git clone" >&2; exit 1; }

# A worktree holding the branch is reported as "branch refs/heads/grading-data".
if agit worktree list --porcelain | grep -qx "branch refs/heads/${BRANCH}"; then
    echo "ERROR: ${BRANCH} is checked out in a worktree; detach it first:" >&2
    agit worktree list --porcelain | awk -v b="refs/heads/${BRANCH}" '/^worktree /{w=$2} $0=="branch " b {print "  git -C " w " checkout --detach"}' >&2
    exit 1
fi

# safe.directory: the clone belongs to another user. Command-line config is honoured
# and is passed on to the upload-pack child.
agit -c safe.directory="$CLONE" fetch -q --no-tags "$CLONE" "+refs/heads/${BRANCH}:${SIDE_REF}"
OLD="$(agit rev-parse "refs/heads/${BRANCH}")"
NEW="$(agit rev-parse "$SIDE_REF")"

if [ "$OLD" = "$NEW" ]; then
    echo "${BRANCH} already at ${NEW:0:10}"
elif agit merge-base --is-ancestor "$OLD" "$NEW"; then
    agit update-ref -m "sync grading data clone" "refs/heads/${BRANCH}" "$NEW" "$OLD"
    echo "${BRANCH} fast-forwarded ${OLD:0:10} -> ${NEW:0:10}"
else
    echo "ERROR: ${BRANCH} and the clone have diverged (${OLD:0:10} vs ${NEW:0:10}); resolve by hand." >&2
    exit 1
fi
