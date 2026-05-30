"""Append-only design notes endpoint.

GET  /api/grading/design-notes  — return full file content (empty string if absent).
POST /api/grading/design-notes  — append a timestamped Markdown block and fsync.

File format: concatenated blocks of the form

    ## <ISO-8601 UTC timestamp>

    <content>

Each POST prepends a blank line before the heading so blocks are visually
separated even when the file is viewed raw. The file is created on first POST;
the parent directory is created if needed.

fcntl.flock (LOCK_EX) guards against concurrent writers on the same host;
os.fsync guarantees the block survives a crash before the HTTP response is sent.
"""
from __future__ import annotations
import datetime as dt
import fcntl
import os

from fastapi import APIRouter, Depends
from ..auth import verify_secret
from ..models import DesignNotePost
from .. import paths as paths_mod

router = APIRouter(dependencies=[Depends(verify_secret)])


@router.get("/api/grading/design-notes")
def get_design_notes() -> dict:
    """Return the full design-notes file content, or an empty string if absent."""
    path = paths_mod.DESIGN_NOTES_PATH
    if not path.exists():
        return {"content": ""}
    return {"content": path.read_text(encoding="utf-8")}


@router.post("/api/grading/design-notes")
def post_design_note(payload: DesignNotePost) -> dict:
    """Append a timestamped block to the design-notes file.

    Returns the UTC timestamp of the appended block and the number of characters
    written (including heading and surrounding whitespace) so callers can confirm
    a non-zero write.
    """
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    block = f"\n## {ts}\n\n{payload.content}\n"
    path = paths_mod.DESIGN_NOTES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(block)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    return {"ts": ts, "appended_chars": len(block)}
