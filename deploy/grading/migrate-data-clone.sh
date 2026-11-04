#!/usr/bin/env bash
# One-off cutover: move grading data from the .worktrees/grading-data git worktree
# to a standalone clone, then redeploy the sidecar with the sandboxed unit.
#
#   deploy/grading/migrate-data-clone.sh      (from .worktrees/next, as agent or root)
#
# Why: a worktree shares objects and refs with the main repo's .git, so the sidecar
# needed write access to the whole repo. A --no-hardlinks clone shares nothing, and
# is owned by the sidecar's own user (metaforge-grading) once deploy.sh has run.
#
# Git work on agent's repos (the old worktree, the main repo, the new clone before
# deploy.sh hands it over) runs as the worktree's owner via `sudo -u`, never as root.
#
# Idempotent: a failed run is fixed by re-running, and once the cutover has happened
# a further run exits at once without touching anything (the clone is live and has
# moved on from the frozen old worktree, so comparing them would only fail and then
# "restore" a stale unit).
# The sidecar is stopped while the data moves (stopping is the only way to know no
# write is mid-flight), so grading pauses briefly. If anything fails after the stop,
# the previous unit is put back and started again automatically. The old worktree
# is committed up to date and kept; it is detached from the branch on success so
# deploy/grading/sync-data-to-repo.sh can fast-forward the branch later.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=../lib/grading-host.sh
. "${REPO_ROOT}/deploy/lib/grading-host.sh"
# Overridable so deploy/grading/test-migrate-data-clone.sh can run against scratch trees.
SRC_REPO="${MF_SRC_REPO:-/home/agent/projects/metaforge}"
OLD_WT="${MF_OLD_WT:-${SRC_REPO}/.worktrees/grading-data}"
CLONE="${MF_CLONE:-/home/agent/projects/metaforge-grading-data}"
UNIT_FILE="${MF_UNIT_FILE:-/etc/systemd/system/metaforge-grading.service}"
UNIT_BACKUP="${MF_UNIT_BACKUP:-${CLONE}.service.pre-migration}"
DEPLOY="${MF_DEPLOY:-${REPO_ROOT}/deploy/grading/deploy.sh}"
SECRET_FILE="${MF_SECRET_FILE:-/etc/metaforge/grading_secret}"
BASE_URL="${MF_BASE_URL:-http://127.0.0.1:53775}"
SIDECAR_USER="${MF_SIDECAR_USER:-metaforge-grading}"
SERVICE=metaforge-grading
BRANCH=grading-data
SUBDIR=data-pipeline/grading

log() { echo "[$(date +%H:%M:%S)] $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

STOPPED=0 DONE=0 BACKUP_TAKEN=0
# Runs on every exit. After the stop and before the cutover is verified, put the
# previous unit back and start it, so a failed run never leaves grading down.
on_exit() {
    local rc=$?
    trap - EXIT
    if [ "$STOPPED" = 1 ] && [ "$DONE" != 1 ]; then
        echo "" >&2
        echo "MIGRATION FAILED (exit ${rc}). Restoring the previous sidecar." >&2
        # Only a unit captured by THIS run is trusted; an older backup may be stale.
        if [ "$BACKUP_TAKEN" = 1 ] \
           && as_user "$OWNER" git -C "$OLD_WT" checkout -q "$BRANCH" \
           && sudo cp "$UNIT_BACKUP" "$UNIT_FILE" \
           && sudo systemctl daemon-reload \
           && sudo systemctl start "$SERVICE"; then
            echo "Done: restored the previous unit from ${UNIT_BACKUP}, put ${OLD_WT} back on ${BRANCH}" >&2
            echo "and started ${SERVICE}. Verdicts written to ${CLONE} since the stop are committed there only." >&2
        else
            cat >&2 <<EOT
Automatic restore FAILED. By hand:
  git -C ${OLD_WT} checkout ${BRANCH}
  sudo cp ${UNIT_BACKUP} ${UNIT_FILE}
  sudo systemctl daemon-reload && sudo systemctl start ${SERVICE}
  curl -fsS ${BASE_URL}/api/grading/healthz
EOT
        fi
        echo "Fix the cause and re-run this script to retry." >&2
    fi
    exit "$rc"
}

# The unit runs code from .worktrees/next, so the venv and unit must come from there.
if [ "${MF_SKIP_CHECKOUT_CHECK:-0}" != 1 ] && [ "$REPO_ROOT" != "${SRC_REPO}/.worktrees/next" ]; then
    die "run this from ${SRC_REPO}/.worktrees/next (merged and pulled), not ${REPO_ROOT}."
fi
[ -f "${OLD_WT}/.git" ] || die "${OLD_WT} is not a git worktree"
OWNER="$(stat -c %U "$OLD_WT")"

trap on_exit EXIT

# True once the cutover has been done: the installed unit runs as the sidecar user or
# points at the clone, the clone belongs to the sidecar user, or the old worktree is
# detached (the last step of a successful run).
already_migrated() {
    local unit; unit="$(sudo cat "$UNIT_FILE" 2>/dev/null || true)"
    grep -q "^User=${SIDECAR_USER}\$" <<<"$unit" && return 0
    grep -qF "GRADING_DATA_GIT_ROOT=${CLONE}" <<<"$unit" && return 0
    [ -d "${CLONE}/.git" ] && [ "$(stat -c %U "$CLONE")" = "$SIDECAR_USER" ] && return 0
    [ "$(as_user "$OWNER" git -C "$OLD_WT" rev-parse --abbrev-ref HEAD)" = HEAD ] && return 0
    return 1
}

# Line count per file under a dir (every file the sidecar might append to), read as
# the dir's owner: the clone is 0750 and the invoking user may not be able to enter it.
inventory() { # <dir> <owner>
    as_user "$2" sh -c 'cd "$1" && find . -type f -print0 | sort -z | xargs -0 wc -l' _ "$1/${SUBDIR}"
}

# What the sidecar's /stats reports: non-empty lines of the judgements file that parse.
count_judgements() { # <dir>
    as_user "$OWNER" python3 -c '
import json, sys
n = 0
for raw in open(sys.argv[1], encoding="utf-8"):
    raw = raw.strip()
    if raw:
        try: json.loads(raw); n += 1
        except ValueError: pass
print(n)' "$1/${SUBDIR}/judgements_provisional.jsonl"
}

stats_count() { # authenticated read-only GET, secret kept out of argv
    printf 'X-Grading-Secret: %s\n' "$(sudo cat "$SECRET_FILE")" \
        | curl -fsS -H @- -H 'Host: metaforge-next.julianit.me' "${BASE_URL}/api/grading/stats" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["judgement_count"])'
}

if already_migrated; then
    log "Already migrated (${CLONE} is live); nothing to do."
    exit 0
fi

log "1. Back up the live unit, then stop the sidecar"
sudo cp "$UNIT_FILE" "$UNIT_BACKUP"
BACKUP_TAKEN=1
STOPPED=1
sudo systemctl stop "$SERVICE"

log "2. Commit anything the autocommit had not yet saved in ${OLD_WT}"
IDENT_N="$(as_user "$OWNER" git -C "$SRC_REPO" log -1 --format=%an "$BRANCH")"
IDENT_E="$(as_user "$OWNER" git -C "$SRC_REPO" log -1 --format=%ae "$BRANCH")"
as_user "$OWNER" git -C "$OLD_WT" add "${SUBDIR}/"
if as_user "$OWNER" git -C "$OLD_WT" diff --cached --quiet; then
    log "   nothing to commit"
else
    as_user "$OWNER" git -C "$OLD_WT" -c user.name="$IDENT_N" -c user.email="$IDENT_E" commit -q \
        -m "wip(grading): final autosave before data clone migration $(date -u +%FT%TZ)"
fi
EXPECTED="$(count_judgements "$OLD_WT")"
log "   ${EXPECTED} judgements in the old worktree"

log "3. Create or update the clone ${CLONE}"
if [ ! -e "$CLONE" ]; then
    as_user "$OWNER" git clone -q --no-hardlinks --branch "$BRANCH" --single-branch "$SRC_REPO" "$CLONE"
    CLONE_OWNER="$OWNER"
else
    [ -d "${CLONE}/.git" ] || die "${CLONE}/.git is not a directory: that is a worktree, not a clone"
    CLONE_OWNER="$(stat -c %U "$CLONE")"   # the sidecar user after a deploy, agent before
    as_user "$CLONE_OWNER" git -c safe.directory='*' -C "$CLONE" pull -q --ff-only "$SRC_REPO" "$BRANCH"
fi
cgit() { as_user "$CLONE_OWNER" git -c safe.directory='*' -C "$CLONE" "$@"; }
cgit rev-parse --is-inside-work-tree > /dev/null
[ ! -e "${CLONE}/.git/objects/info/alternates" ] || die "clone borrows objects from another repo"

log "4. Commit identity from the latest ${BRANCH} autocommit"
cgit config user.name "$IDENT_N"
cgit config user.email "$IDENT_E"

log "5. Check the clone holds exactly the data the worktree has (every file, by line count)"
INV_OLD="$(inventory "$OLD_WT" "$OWNER")"
INV_NEW="$(inventory "$CLONE" "$CLONE_OWNER")"
if [ "$INV_OLD" != "$INV_NEW" ]; then
    diff <(echo "$INV_OLD") <(echo "$INV_NEW") >&2 || true
    die "the clone and the worktree differ (see above; a file may be gitignored)"
fi

log "6. Redeploy the sidecar (user, ownership, venv, unit, restart, checks)"
MF_MIGRATING=1 "$DEPLOY"

log "7. Verify"
curl -fsS "${BASE_URL}/api/grading/healthz"; echo
AFTER="$(stats_count)"
[ "$AFTER" = "$EXPECTED" ] || die "the old worktree held ${EXPECTED} judgements and the sidecar now reports ${AFTER}"
log "   ${AFTER} judgements, as expected"
# Writes, as the sidecar user: what the autocommit and the judgement POSTs need. No
# fake verdict is posted; these touch only scratch files and the index lock.
as_user "$SIDECAR_USER" test -w "${CLONE}/.git/index" || die "${SIDECAR_USER} cannot write ${CLONE}/.git/index"
for d in "${CLONE}/.git" "${CLONE}/${SUBDIR}"; do
    as_user "$SIDECAR_USER" sh -c 'touch "$1/.mf-write-check" && rm "$1/.mf-write-check"' _ "$d" \
        || die "${SIDECAR_USER} cannot write in ${d}"
done
as_user "$SIDECAR_USER" git -c safe.directory='*' -C "$CLONE" add -- "${SUBDIR}/" \
    || die "${SIDECAR_USER} cannot run git add in the clone"
log "   ${SIDECAR_USER} can write the clone"

log "8. Detach the old worktree from ${BRANCH} (it is kept, not deleted)"
as_user "$OWNER" git -C "$OLD_WT" checkout -q --detach

DONE=1
log "Done. Keep ${OLD_WT} until the clone has run a day. To bring verdicts back to the"
log "repo's ${BRANCH} branch: deploy/grading/sync-data-to-repo.sh"
