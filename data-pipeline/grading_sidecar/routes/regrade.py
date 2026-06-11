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

from fastapi import APIRouter, Depends, Query

from ..auth import verify_secret
from ..models import JudgementRecord, normalise_judgement
from ..persistence import append_jsonl, read_jsonl_skip_malformed
from ..regrade import sample_regrade, self_agreement
from ..signal_report import resolve_verdicts
from .. import paths as paths_mod

router = APIRouter(dependencies=[Depends(verify_secret)])

# Identity fields carried into a blind sample item — enough to locate and render
# the chain, deliberately WITHOUT any verdict-bearing field (metaphor, linkage,
# tiers, tags, notes, confidence). Whitelist, not blacklist, so a future verdict
# field can't leak into the blind view by omission.
_BLIND_FIELDS = ("chain_signature", "topic", "topic_synset_id", "vehicle",
                 "vehicle_synset_id", "proposer", "round")


@router.get("/api/grading/regrade/sample")
def get_regrade_sample(n: int = Query(default=12, ge=1, le=100),
                       min_age_days: int = Query(default=3, ge=0),
                       seed: int = Query(default=1)) -> dict:
    """Draw a blind, class-stratified re-grade batch from the gold verdicts."""
    judgements, _ = read_jsonl_skip_malformed(paths_mod.JUDGEMENTS_PATH)
    today = dt.date.today().isoformat()
    sample = sample_regrade(judgements, n=n, min_age_days=min_age_days,
                            today=today, seed=seed)
    blinded = [{k: row[k] for k in _BLIND_FIELDS if k in row} for row in sample]
    return {"count": len(blinded), "records": blinded}


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
