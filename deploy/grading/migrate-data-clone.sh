#!/usr/bin/env bash
# One-off cutover: move grading data from the .worktrees/grading-data git worktree
# to a standalone clone, then redeploy the sidecar with the sandboxed unit.
#
#   sudo deploy/grading/migrate-data-clone.sh      (from the .worktrees/next checkout)
#
# Why: a worktree shares objects and refs with the main repo's .git, so the sidecar
# needed write access to the whole repo. A --no-hardlinks clone shares nothing.
#
# Idempotent: every step is safe to repeat, so a failed run is fixed by re-running.
# The old worktree is committed up to date and left in place; it is never deleted.
# The sidecar stays stopped while the data is moved, so there is a short gap in
# grading (no way to detect a mid-write otherwise: stopping is what makes it safe).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# Overridable so deploy/grading/test-migrate-data-clone.sh can run against scratch trees.
SRC_REPO="${MF_SRC_REPO:-/home/agent/projects/metaforge}"
OLD_WT="${MF_OLD_WT:-${SRC_REPO}/.worktrees/grading-data}"
CLONE="${MF_CLONE:-/home/agent/projects/metaforge-grading-data}"
UNIT_FILE="${MF_UNIT_FILE:-/etc/systemd/system/metaforge-grading.service}"
UNIT_BACKUP="${MF_UNIT_BACKUP:-${CLONE}.service.pre-migration}"
DEPLOY="${MF_DEPLOY:-${REPO_ROOT}/deploy/grading/deploy.sh}"
SECRET_FILE="${MF_SECRET_FILE:-/etc/metaforge/grading_secret}"
BASE_URL="${MF_BASE_URL:-http://127.0.0.1:53775}"
SERVICE=metaforge-grading
BRANCH=grading-data
SUBDIR=data-pipeline/grading

log() { echo "[$(date +%H:%M:%S)] $*"; }

rollback_help() {
    cat >&2 <<EOT

MIGRATION FAILED. The old worktree ${OLD_WT} is untouched and still holds every
verdict up to the stop. To go back to the previous unit:
  sudo systemctl stop ${SERVICE}
  sudo cp ${UNIT_BACKUP} ${UNIT_FILE}     # the unit that was live before this run
  sudo systemctl daemon-reload && sudo systemctl start ${SERVICE}
  curl -fsS ${BASE_URL}/api/grading/healthz
(If the backup is missing, take the unit from git history: git show <commit before
the sandbox change>:deploy/grading/metaforge-grading.service.) Verdicts written to
the clone since the cutover are committed there; the old worktree will not have them.
To retry instead, fix the cause and re-run this script.
EOT
}
trap rollback_help ERR

# The unit runs code from .worktrees/next, so the venv and unit must come from there.
if [ "${MF_SKIP_CHECKOUT_CHECK:-0}" != 1 ] && [ "$REPO_ROOT" != "${SRC_REPO}/.worktrees/next" ]; then
    echo "ERROR: run this from ${SRC_REPO}/.worktrees/next (merged and pulled), not ${REPO_ROOT}." >&2
    exit 1
fi
[ -f "${OLD_WT}/.git" ] || { echo "ERROR: ${OLD_WT} is not a git worktree" >&2; exit 1; }

judgement_count() { # prints the sidecar's authenticated judgement_count
    printf 'X-Grading-Secret: %s\n' "$(sudo cat "$SECRET_FILE")" \
        | curl -fsS -H @- -H 'Host: metaforge-next.julianit.me' "${BASE_URL}/api/grading/stats" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["judgement_count"])'
}

log "1. Judgement count before the stop"
BEFORE="$(judgement_count)"
log "   ${BEFORE} judgements"

log "2. Back up the live unit and stop the sidecar"
if [ ! -e "$UNIT_BACKUP" ]; then sudo cp "$UNIT_FILE" "$UNIT_BACKUP"; fi
sudo systemctl stop "$SERVICE"

log "3. Commit anything the autocommit had not yet saved in ${OLD_WT}"
git -C "$OLD_WT" add "${SUBDIR}/"
if git -C "$OLD_WT" diff --cached --quiet; then
    log "   nothing to commit"
else
    git -C "$OLD_WT" commit -q -m "wip(grading): final autosave before data clone migration $(date -u +%FT%TZ)"
fi

log "4. Create or update the clone ${CLONE}"
if [ ! -e "$CLONE" ]; then
    git clone -q --no-hardlinks --branch "$BRANCH" --single-branch "$SRC_REPO" "$CLONE"
else
    [ -d "${CLONE}/.git" ] || { echo "ERROR: ${CLONE}/.git is not a directory: that is a worktree, not a clone" >&2; exit 1; }
    git -C "$CLONE" pull -q --ff-only "$SRC_REPO" "$BRANCH"
fi
git -C "$CLONE" rev-parse --is-inside-work-tree > /dev/null
[ ! -e "${CLONE}/.git/objects/info/alternates" ] || { echo "ERROR: clone borrows objects from another repo" >&2; exit 1; }

log "5. Commit identity from the latest ${BRANCH} autocommit"
git -C "$CLONE" config user.name "$(git -C "$SRC_REPO" log -1 --format=%an "$BRANCH")"
git -C "$CLONE" config user.email "$(git -C "$SRC_REPO" log -1 --format=%ae "$BRANCH")"

log "6. Check the clone holds every data file the worktree has"
MISSING="$(comm -23 <(cd "${OLD_WT}/${SUBDIR}" && find . -type f | sort) <(cd "${CLONE}/${SUBDIR}" && find . -type f | sort))"
if [ -n "$MISSING" ]; then
    echo "ERROR: files in the worktree but not the clone (ignored by git?):" >&2
    echo "$MISSING" >&2
    exit 1
fi

log "7. Redeploy the sidecar (venv, unit, restart, checks)"
"$DEPLOY"

log "8. Verify"
curl -fsS "${BASE_URL}/api/grading/healthz"; echo
AFTER="$(judgement_count)"
if [ "$AFTER" != "$BEFORE" ]; then
    echo "ERROR: judgement count was ${BEFORE} before the stop and is ${AFTER} now" >&2
    exit 1
fi
log "   ${AFTER} judgements, unchanged"

trap - ERR
log "Done. The old worktree ${OLD_WT} is kept; remove it only once the clone has run a day."
