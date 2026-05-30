"""GET /api/grading/topics — lean list of distinct topics across all chain files."""
from __future__ import annotations
from fastapi import APIRouter, Depends
from ..auth import verify_secret
from ..persistence import read_jsonl_skip_malformed
from .. import paths as paths_mod

router = APIRouter(dependencies=[Depends(verify_secret)])


@router.get("/api/grading/topics")
def get_topics() -> dict:
    seen: dict[str, dict] = {}
    for p in sorted(paths_mod.GRADING_DIR.glob(paths_mod.CHAINS_GLOB)):
        recs, _ = read_jsonl_skip_malformed(p)
        for r in recs:
            seen.setdefault(r["topic"], {
                "topic": r["topic"], "topic_synset_id": r["topic_synset_id"]
            })
    return {"topics": sorted(seen.values(), key=lambda x: x["topic"])}
