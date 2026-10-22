"""GET /api/grading/guided-walk — the operator-prefilled guided walk.

Serves an EXACT ordered candidate list written offline into
guided_walk_provisional.jsonl (one candidate per line: chain_signature, order,
cohort, judge_verdict, batch). Unlike the signal walk, there is no triage
ordering — the operator (or the agent teeing up a bootstrap round) fixes the
order. The route joins each candidate with its full chain record for rendering
and serves the latest batch by default (?batch= overrides).

Anchoring guard (same invariant as walk.py): the stored `judge_verdict` and the
`cohort` (eval/train) are the whole point of a blind held-out round — they NEVER
leave the server. A candidate whose chain record is missing is dropped, not
500ed. Chains are resolved across ALL cohorts (spike/curated/stock) because
fresh bootstrap candidates come from the broad stock corpus the grading views
don't otherwise glob.
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, Query
from ..auth import verify_secret
from ..chain_store import load_chains as _load_chains
from ..persistence import read_jsonl_skip_malformed
from .. import paths as paths_mod

log = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(verify_secret)])

# Everything the browser is allowed to see per candidate. `order` drives display
# position; the record carries the chain for rendering. Deliberately excludes
# judge_verdict + cohort (anchoring guard) — see module docstring.
_PUBLIC_ENTRY_FIELDS = ("chain_signature", "topic", "vehicle", "order")
_ALL_COHORTS = ["spike", "curated", "stock"]


def _load_candidates() -> list[dict]:
    """Raw candidate rows from guided_walk_provisional.jsonl (may be empty)."""
    path = paths_mod.GRADING_DIR / paths_mod.GUIDED_WALK_NAME
    if not path.exists():
        return []
    recs, skipped = read_jsonl_skip_malformed(path)
    if skipped:
        log.warning("guided-walk: skipped %d malformed candidate line(s)", skipped)
    return [r for r in recs if r.get("chain_signature")]


def _resolve_batch(candidates: list[dict], requested: str | None) -> str | None:
    """The batch to serve: the requested one, else the lexicographically latest
    present (batch ids are date-stamped, e.g. 2026-07-05-r1, so max = newest)."""
    batches = {c.get("batch") for c in candidates if c.get("batch") is not None}
    if requested is not None:
        return requested
    return max(batches) if batches else None


@router.get("/api/grading/guided-walk")
def get_guided_walk(batch: str | None = Query(default=None)) -> dict:
    candidates = _load_candidates()
    active_batch = _resolve_batch(candidates, batch)
    if active_batch is None:
        return {"count": 0, "batch": None, "entries": []}

    rows = sorted((c for c in candidates if c.get("batch") == active_batch),
                  key=lambda c: c.get("order", 0))
    chain_by_sig = {c["chain_signature"]: c for c in _load_chains(_ALL_COHORTS)}

    entries = []
    for cand in rows:
        record = chain_by_sig.get(cand["chain_signature"])
        if record is None:
            log.warning("guided-walk: no chain for %s (batch %s) — dropped",
                        cand["chain_signature"], active_batch)
            continue
        entries.append({
            "chain_signature": cand["chain_signature"],
            "topic": record.get("topic"),
            "vehicle": record.get("vehicle"),
            "order": cand.get("order", 0),
            "record": record,
        })
    return {"count": len(entries), "batch": active_batch, "entries": entries}
