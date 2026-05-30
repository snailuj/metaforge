"""GET /api/grading/stats — aggregate counts for chain files and judgements."""
from __future__ import annotations
import datetime as dt
from fastapi import APIRouter, Depends
from ..auth import verify_secret
from ..persistence import read_jsonl_skip_malformed
from .. import paths as paths_mod

router = APIRouter(dependencies=[Depends(verify_secret)])


@router.get("/api/grading/stats")
def get_stats() -> dict:
    chain_count = 0
    for p in paths_mod.GRADING_DIR.glob(paths_mod.CHAINS_GLOB):
        recs, _ = read_jsonl_skip_malformed(p)
        chain_count += len(recs)
    judgements, _ = read_jsonl_skip_malformed(paths_mod.JUDGEMENTS_PATH)
    last_judgement_ts = max((j.get("ts", "") for j in judgements), default="") or None
    return {
        "chain_count": chain_count,
        "judgement_count": len(judgements),
        "last_judgement_ts": last_judgement_ts,
        "schema_version": {"chain": "chain.v1", "judgement": "judgement.v1"},
        "server_ts": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
