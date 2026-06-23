"""Blind re-grade sampling + self-agreement — the intra-rater reliability floor.

The audit's universal prerequisite: no κ gate or geometry-concordance lift is
interpretable until we know the operator agrees with himself. This module draws a
class-stratified blind sample of already-resolved live/dead verdicts (old enough
that re-grading tests *stability*, not short-term memory) and scores how a fresh
pass agrees with the original on each verdict axis.

SAFETY: this only READS verdicts and returns a sample. The regrade verdicts the
operator produces must be written to a SEPARATE JSONL (never the gold file) — the
canonical resolver is latest-wins per chain_signature, so a regrade landing in the
main file would silently overwrite the original it is meant to be compared against.
That separation is the route's job; this module never writes.
"""
from __future__ import annotations

import datetime as dt
import random

from .models import effective_linkage, normalise_judgement
from .signal_report import binary_label, resolve_verdicts


def _age_days(ts: str, today: str) -> int:
    """Whole days between a verdict's ISO timestamp and `today` (YYYY-MM-DD)."""
    return (dt.date.fromisoformat(today) - dt.date.fromisoformat(ts[:10])).days


def _allocate(counts: dict[str, int], n: int) -> dict[str, int]:
    """Proportional class allocation summing to min(n, total), largest-remainder.

    Keeps the sample's live:dead ratio close to the corpus ratio so a reliability
    estimate is not dominated by whichever class happens to be larger. Ties broken
    by class name for determinism.
    """
    total = sum(counts.values())
    if total <= n:
        return dict(counts)
    exact = {k: n * c / total for k, c in counts.items()}
    floor = {k: int(v) for k, v in exact.items()}
    remainder = n - sum(floor.values())
    order = sorted(counts, key=lambda k: (-(exact[k] - floor[k]), k))
    for k in order[:remainder]:
        floor[k] += 1
    return floor


def sample_regrade(judgements: list[dict], *, n: int, min_age_days: int,
                   today: str, seed: int) -> list[dict]:
    """Draw a deterministic, class-stratified blind re-grade sample.

    Resolves verdicts (latest-wins, superseded dropped), keeps only live/dead
    pairings graded at least `min_age_days` ago, allocates `n` proportionally
    across the live/dead classes, and seed-samples within each class. The resolved
    verdict rides along on each row for SERVER-SIDE pairing; the route MUST strip
    it before sending to the client — that is what makes the re-grade blind.
    """
    resolved = [normalise_judgement(r) for r in resolve_verdicts(judgements)]
    eligible = [r for r in resolved
                if binary_label(r) is not None
                and _age_days(r.get("ts", ""), today) >= min_age_days]

    by_class: dict[str, list[dict]] = {}
    for r in eligible:
        by_class.setdefault(binary_label(r), []).append(r)

    alloc = _allocate({cls: len(rows) for cls, rows in by_class.items()}, n)

    rng = random.Random(seed)
    sample: list[dict] = []
    for cls in ("live", "dead"):
        pool = sorted(by_class.get(cls, []), key=lambda r: r["chain_signature"])
        k = alloc.get(cls, 0)
        sample.extend(pool if k >= len(pool) else rng.sample(pool, k))
    return sample


def _axis_agreement(label_pairs: list[tuple]) -> dict:
    """Observed agreement + 2-class Cohen's κ over (original, regrade) label pairs.

    κ is None when undefined (no pairs, or expected agreement == 1 because every
    label is identical) — an honest "undefined", never a divide-by-zero crash.
    """
    n = len(label_pairs)
    if n == 0:
        return {"agreement": None, "kappa": None}
    po = sum(1 for a, b in label_pairs if a == b) / n
    labels = {lab for pair in label_pairs for lab in pair}
    pe = sum((sum(a == lab for a, _ in label_pairs) / n)
             * (sum(b == lab for _, b in label_pairs) / n)
             for lab in labels)
    kappa = None if (1 - pe) == 0 else (po - pe) / (1 - pe)
    return {"agreement": round(po, 4),
            "kappa": round(kappa, 4) if kappa is not None else None}


def self_agreement(originals: list[dict], regrades: list[dict]) -> dict:
    """Pair originals to regrades by chain_signature; score each verdict axis.

    Linkage is compared under effective_linkage so the tag-implies-bad convention
    (a `leap`/`merge`/`bad_head` tag forces bad) is honoured on both sides — an
    original tagged-but-untapped and a regrade explicitly tapped bad AGREE.
    Unmatched signatures on either side are ignored (no spurious pair).
    """
    re_by_sig = {r["chain_signature"]: r for r in regrades}
    pairs = [(o, re_by_sig[o["chain_signature"]])
             for o in originals if o["chain_signature"] in re_by_sig]
    metaphor = _axis_agreement([(o.get("metaphor"), r.get("metaphor")) for o, r in pairs])
    linkage = _axis_agreement([
        (effective_linkage(normalise_judgement(o)), effective_linkage(normalise_judgement(r)))
        for o, r in pairs])
    return {"n_pairs": len(pairs), "metaphor": metaphor, "linkage": linkage}
