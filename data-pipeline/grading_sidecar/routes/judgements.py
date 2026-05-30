"""POST + GET /api/grading/judgements

POST appends a validated JudgementRecord to the JSONL file (atomic, fsync'd).
GET reads all records with an optional ?topic= filter.

Both routes require the X-Grading-Secret header (bypassed in dev via
GRADING_DEV=1 — see auth.py).
"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Query
from ..auth import verify_secret
from ..models import JudgementRecord
from ..persistence import append_jsonl, read_jsonl_skip_malformed
from .. import paths as paths_mod

router = APIRouter(dependencies=[Depends(verify_secret)])


@router.post("/api/grading/judgements")
def post_judgement(record: JudgementRecord) -> dict:
    append_jsonl(paths_mod.JUDGEMENTS_PATH, record.model_dump(mode="json"))
    return record.model_dump(mode="json")


@router.get("/api/grading/judgements")
def get_judgements(topic: Optional[str] = Query(default=None)) -> dict:
    records, skipped = read_jsonl_skip_malformed(paths_mod.JUDGEMENTS_PATH)
    if topic is not None:
        records = [r for r in records if r.get("topic") == topic]
    return {"count": len(records), "skipped_malformed": skipped, "records": records}
