"""GET /api/grading/glosses — synset_id -> {pos, definition} for chain synsets.

Lets the grader disambiguate a topic's sense (noun vs adjective for "antique",
etc.). Served from a precomputed file (the sidecar has no DB); absence yields an
empty map so the UI degrades to head-only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import verify_secret
from ..persistence import read_jsonl_skip_malformed
from .. import paths as paths_mod

router = APIRouter(dependencies=[Depends(verify_secret)])


@router.get("/api/grading/glosses")
def get_glosses() -> dict:
    path = paths_mod.GRADING_DIR / paths_mod.CHAIN_GLOSSES_NAME
    records, _ = read_jsonl_skip_malformed(path)
    glosses = {
        r["synset_id"]: {"pos": r.get("pos"), "definition": r.get("definition")}
        for r in records if r.get("synset_id")
    }
    return {"glosses": glosses}
