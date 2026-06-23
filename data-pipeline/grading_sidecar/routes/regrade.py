"""Blind re-grade routes — the intra-rater reliability floor.

  GET  /api/grading/regrade/sample     → a class-stratified BLIND sample
       (prior verdict stripped so the re-grade can't be anchored)
  POST /api/grading/regrade            → record a fresh verdict to the SEPARATE
       blind file (never the gold judgements)
  GET  /api/grading/regrade/agreement  → self-agreement of gold vs blind re-grades

All gated by the X-Grading-Secret dependency (bypassed in dev). The sampler and
agreement maths live in grading_sidecar.regrade; these routes are thin IO wiring.
"""
from __future__ import annotations

import datetime as dt

import logging

from fastapi import APIRouter, Depends, Query

from ..auth import verify_secret
from ..chain_store import load_chains
from ..models import JudgementRecord, normalise_judgement
from ..persistence import append_jsonl, read_jsonl_skip_malformed
from ..regrade import sample_regrade, self_agreement
from ..signal_report import resolve_verdicts
from .. import paths as paths_mod

log = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(verify_secret)])


@router.get("/api/grading/regrade/sample")
def get_regrade_sample(n: int = Query(default=12, ge=1, le=100),
                       min_age_days: int = Query(default=3, ge=0),
                       seed: int = Query(default=1)) -> dict:
    """Draw a blind, class-stratified re-grade batch from the gold verdicts.

    Returns the CHAIN records (path included), not the verdicts: a ChainRecord
    carries no live/dead/linkage field, so the operator sees the chain to re-grade
    with no prior verdict to anchor on. A sampled signature with no surviving chain
    record is skipped (don't 500 a pruned line)."""
    judgements, _ = read_jsonl_skip_malformed(paths_mod.JUDGEMENTS_PATH)
    today = dt.date.today().isoformat()
    sample = sample_regrade(judgements, n=n, min_age_days=min_age_days,
                            today=today, seed=seed)
    chain_by_sig = {c["chain_signature"]: c for c in load_chains()}
    records, missing = [], 0
    for row in sample:
        chain = chain_by_sig.get(row["chain_signature"])
        if chain is None:
            missing += 1
            continue
        records.append(chain)
    if missing:
        log.warning("regrade sample: %d sampled signature(s) had no chain record", missing)
    return {"count": len(records), "records": records}


@router.post("/api/grading/regrade")
def post_regrade(record: JudgementRecord) -> dict:
    """Append a blind re-grade verdict to the SEPARATE blind file.

    Never JUDGEMENTS_PATH — see paths.REGRADES_PATH for why that separation is a
    safety property, not a convenience.
    """
    append_jsonl(paths_mod.REGRADES_PATH, record.model_dump(mode="json"))
    return record.model_dump(mode="json")


@router.get("/api/grading/regrade/agreement")
def get_regrade_agreement() -> dict:
    """Self-agreement (per-axis agreement + Cohen's κ) of gold vs blind re-grades.

    Both sides are resolved (latest-wins per chain_signature) before pairing, so a
    re-graded-twice chain compares its latest blind pass to its latest gold verdict.
    """
    gold, _ = read_jsonl_skip_malformed(paths_mod.JUDGEMENTS_PATH)
    regrades, _ = read_jsonl_skip_malformed(paths_mod.REGRADES_PATH)
    originals = [normalise_judgement(r) for r in resolve_verdicts(gold)]
    blind = [normalise_judgement(r) for r in resolve_verdicts(regrades)]
    return self_agreement(originals, blind)
