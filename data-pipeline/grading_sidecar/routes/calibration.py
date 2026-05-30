"""GET /api/grading/calibration-sample — random sample of chains for a given round."""
from __future__ import annotations
import random
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from ..auth import verify_secret
from ..persistence import read_jsonl_skip_malformed
from .. import paths as paths_mod

router = APIRouter(dependencies=[Depends(verify_secret)])


@router.get("/api/grading/calibration-sample")
def calibration_sample(
    n: int = Query(default=10, ge=1, le=100),
    round: int = Query(default=1, ge=1),
    seed: Optional[int] = Query(default=None),
) -> dict:
    target = paths_mod.GRADING_DIR / f"sonnet_chains_provisional_r{round}.jsonl"
    recs, _ = read_jsonl_skip_malformed(target)
    if not recs:
        raise HTTPException(404, f"no chains for round {round}")
    rng = random.Random(seed if seed is not None else 0)
    rng.shuffle(recs)
    return {"records": recs[:n]}
