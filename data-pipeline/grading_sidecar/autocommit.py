"""15-min auto-commit of data-pipeline/grading/ — see spec → Sidecar → Auto-commit timer.

Does NOT push (would require VPS credentials). Julian pushes from his dev box.
Errors logged, never raised."""
from __future__ import annotations
import asyncio
import datetime as dt
import logging
import subprocess

log = logging.getLogger(__name__)


def autocommit_once(repo_root: str, grading_subdir: str) -> None:
    """One-shot: git add <subdir>; git commit -m '...' . Idempotent / tolerant
    of 'nothing to commit' (commit returncode 1)."""
    try:
        subprocess.run(
            ["git", "-C", repo_root, "add", grading_subdir],
            check=True, capture_output=True,
        )
        ts = dt.datetime.now(dt.timezone.utc).isoformat()
        result = subprocess.run(
            ["git", "-C", repo_root, "commit", "-m", f"wip(grading): autosave {ts}"],
            capture_output=True,
        )
        if result.returncode not in (0, 1):
            log.warning(
                "autocommit unexpected returncode=%d stderr=%s",
                result.returncode,
                result.stderr.decode("utf-8", "replace"),
            )
    except Exception as exc:
        log.error("autocommit failed: %s", exc, exc_info=True)


async def autocommit_loop(
    repo_root: str,
    grading_subdir: str,
    interval_sec: float = 900,
) -> None:
    """Sleep interval_sec, then autocommit; repeat until cancelled."""
    while True:
        await asyncio.sleep(interval_sec)
        autocommit_once(repo_root, grading_subdir)
