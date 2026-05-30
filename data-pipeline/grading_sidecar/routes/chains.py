"""GET /api/grading/chains

Unions all round files matching CHAINS_GLOB, applies optional ?topic= filter,
and returns records with a count of skipped malformed lines.

Requires X-Grading-Secret header (bypassed in dev via GRADING_DEV=1 — see auth.py).
"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Query
from ..auth import verify_secret
from ..persistence import read_jsonl_skip_malformed
from .. import paths as paths_mod

router = APIRouter(dependencies=[Depends(verify_secret)])


@router.get("/api/grading/chains")
def get_chains(topic: Optional[str] = Query(default=None)) -> dict:
    records: list[dict] = []
    skipped = 0
    for p in sorted(paths_mod.GRADING_DIR.glob(paths_mod.CHAINS_GLOB)):
        recs, s = read_jsonl_skip_malformed(p)
        records.extend(recs)
        skipped += s
    if topic is not None:
        records = [r for r in records if r.get("topic") == topic]
    return {"count": len(records), "skipped_malformed": skipped, "records": records}
