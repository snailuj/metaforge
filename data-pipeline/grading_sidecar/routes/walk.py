"""GET /api/grading/walk — the signal-prioritised grading walk.

Pure IO wiring over grading_sidecar.walk. Joins the chain rounds with triage
liveness + structural flags and the existing verdicts, then returns an
acquisition-ordered list of single chains to grade next/prev:

- liveness   ← triage_scores*.jsonl   (handpicked + r2 snapshots; {sig: score})
- structural ← triage_structural.jsonl ({sig: {bad_head, leap, weak_linkage}})
- graded     ← JUDGEMENTS_PATH         (skip already-graded; ?ungraded=0 keeps them)
- steering   ← JUDGEMENTS_PATH         (order topics toward under-collected panel axes)

Each entry carries the full chain record so the UI can render the path (graph
context on desktop, bare chain on mobile). Requires X-Grading-Secret (bypassed
in dev via GRADING_DEV=1 — see auth.py).
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, Query
from ..auth import verify_secret
from ..chain_store import load_chains as _load_chains
from ..models import normalise_judgement
from ..persistence import read_jsonl_skip_malformed
from .. import paths as paths_mod
from ..walk import assemble_paths, build_walk, collected_labels_from_verdicts

log = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(verify_secret)])

# Response contract. The triage priors (liveness + structural flags) that DROVE the
# ordering are deliberately excluded — surfacing a predicted score/flag would anchor
# the grader's fresh judgement (the walk's KEY INVARIANT). They never leave the server.
_WALK_PUBLIC_FIELDS = ("chain_signature", "topic", "vehicle", "dwell_index", "dwell_n")


def _load_liveness() -> dict[str, int]:
    """{chain_signature: score} unioned across all triage_scores* snapshots.

    Files are read in sorted order; a later snapshot's score wins on collision so
    a re-triage round supersedes an earlier one for the same signature.
    """
    by_sig: dict[str, int] = {}
    for p in sorted(paths_mod.GRADING_DIR.glob(paths_mod.TRIAGE_SCORES_GLOB)):
        recs, _ = read_jsonl_skip_malformed(p)
        for r in recs:
            sig = r.get("chain_signature")
            if sig is not None and "score" in r:
                by_sig[sig] = r["score"]
    return by_sig


def _load_structural() -> dict[str, dict]:
    """{chain_signature: {bad_head, leap, weak_linkage}} from the single flags file."""
    path = paths_mod.GRADING_DIR / paths_mod.TRIAGE_STRUCTURAL_NAME
    recs, _ = read_jsonl_skip_malformed(path)
    out: dict[str, dict] = {}
    for r in recs:
        sig = r.get("chain_signature")
        if sig is not None:
            out[sig] = {
                "bad_head": bool(r.get("bad_head")),
                "leap": bool(r.get("leap")),
                "weak_linkage": bool(r.get("weak_linkage")),
            }
    return out


@router.get("/api/grading/walk")
def get_walk(ungraded: bool = Query(default=True)) -> dict:
    chains = _load_chains()
    liveness_by_sig = _load_liveness()
    structural_by_sig = _load_structural()

    verdicts, _ = read_jsonl_skip_malformed(paths_mod.JUDGEMENTS_PATH)
    graded_sigs = {v["chain_signature"] for v in verdicts if "chain_signature" in v}
    collected = collected_labels_from_verdicts([normalise_judgement(v) for v in verdicts])

    paths = assemble_paths(chains, liveness_by_sig=liveness_by_sig,
                           structural_by_sig=structural_by_sig)
    walk = build_walk(
        paths,
        graded_sigs=graded_sigs if ungraded else set(),
        collected_labels=collected,
    )

    # Project to the public contract — priors stay server-side (anchoring guard).
    chain_by_sig = {c["chain_signature"]: c for c in chains}
    entries = [
        {**{k: entry[k] for k in _WALK_PUBLIC_FIELDS},
         "record": chain_by_sig.get(entry["chain_signature"])}
        for entry in walk
    ]
    return {"count": len(entries), "entries": entries}
