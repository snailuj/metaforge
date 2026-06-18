"""Sense-check routes — anchor snap-correctness to human gold.

  GET  /api/grading/sense-check/sample → a stratified sample of endpoints, each
       enriched with the snapped gloss, candidate senses, and all context chains.
  POST /api/grading/sense-check        → append one label to the SEPARATE labels
       file (never the gold judgements — see paths.SENSE_LABELS_PATH).

Sampler + item maths live in grading_sidecar.sense_check; these routes are thin IO.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from ..auth import verify_secret
from ..chain_store import load_chains
from ..models import SenseLabel
from ..persistence import append_jsonl, read_jsonl_skip_malformed
from ..sense_check import (build_sample_items, load_sense_candidates,
                           load_snapped_glosses, sample_sense_check)
from .. import paths as paths_mod

log = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(verify_secret)])


@router.get("/api/grading/sense-check/sample")
def get_sense_check_sample(n_flagged: int = Query(default=40, ge=0, le=200),
                           n_random: int = Query(default=40, ge=0, le=200),
                           seed: int = Query(default=1)) -> dict:
    """Draw a stratified sense-check sample and enrich it for the UI."""
    flags, _ = read_jsonl_skip_malformed(paths_mod.GRADING_DIR / paths_mod.SENSE_FLAGS_NAME)
    chains = load_chains(paths_mod.SENSECHECK_COHORTS, tag_cohort=True)
    labels, _ = read_jsonl_skip_malformed(paths_mod.SENSE_LABELS_PATH)
    endpoints = sample_sense_check(flags, chains, labels,
                                   n_flagged=n_flagged, n_random=n_random, seed=seed)
    candidates = load_sense_candidates(
        read_jsonl_skip_malformed, paths_mod.GRADING_DIR / paths_mod.SENSE_CANDIDATES_NAME)
    glosses = load_snapped_glosses(
        read_jsonl_skip_malformed, paths_mod.GRADING_DIR / paths_mod.CHAIN_GLOSSES_NAME)
    items = build_sample_items(endpoints, candidates, glosses, chains)
    log.debug("sense_check sample: %d items (flags=%d chains=%d labels=%d)",
              len(items), len(flags), len(chains), len(labels))
    return {"count": len(items), "items": items}


@router.post("/api/grading/sense-check")
def post_sense_label(label: SenseLabel) -> dict:
    """Append a sense label to the SEPARATE labels file. Never JUDGEMENTS_PATH."""
    append_jsonl(paths_mod.SENSE_LABELS_PATH, label.model_dump(mode="json"))
    return label.model_dump(mode="json")
