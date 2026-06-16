"""Sense-check sampling + item building — anchors snap-correctness to human gold.

Pure functions (no IO): the route loads the flags / chains / labels / precomputes
and passes them in. Mirrors regrade.py: a deterministic, stratified, seed-stable
draw. The two strata — `flagged` (the subagent's wrong/rare endpoints) and
`random` (UNFLAGGED endpoints) — are both labelled by the operator so the analysis
can estimate the subagent's precision AND its silent false-negative rate.
"""
from __future__ import annotations

import random


def distinct_endpoints(chains: list[dict]) -> list[dict]:
    """Distinct (role, word, snapped_synset_id) endpoints across all chains.

    Topic and vehicle of every chain; deduped. Endpoints missing a word or synset
    are skipped (a chain.v1 record always has both, but stay defensive)."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for c in chains:
        for role, word, sid in (
            ("topic", c.get("topic"), c.get("topic_synset_id")),
            ("vehicle", c.get("vehicle"), c.get("vehicle_synset_id")),
        ):
            if not word or not sid:
                continue
            key = (role, word, str(sid))
            if key in seen:
                continue
            seen.add(key)
            out.append({"role": role, "word": word,
                        "snapped_synset_id": str(sid), "stratum": "random"})
    return out


def _take(pool: list[dict], k: int, rng: random.Random) -> list[dict]:
    """Deterministic sample of up to k from pool (sorted first for stability)."""
    ordered = sorted(pool, key=lambda e: (e["role"], e["word"], e["snapped_synset_id"]))
    return ordered if k >= len(ordered) else rng.sample(ordered, k)


def sample_sense_check(flags: list[dict], chains: list[dict], labels: list[dict],
                       *, n_flagged: int, n_random: int, seed: int) -> list[dict]:
    """Draw a deterministic, stratified sense-check sample.

    `flagged` stratum = up to n_flagged distinct endpoints present in `flags`;
    `random` stratum = up to n_random distinct endpoints NOT in flags. Endpoints
    already present in `labels` are excluded from both so successive sessions
    broaden coverage."""
    labelled = {(l.get("role"), l.get("word"), l.get("snapped_synset_id"))
                for l in labels}

    flagged: list[dict] = []
    seen: set[tuple] = set()
    for f in flags:
        key = (f.get("role"), f.get("word"),
               str(f["synset_id"]) if f.get("synset_id") is not None else None)
        if None in key or key in seen:
            continue
        seen.add(key)
        flagged.append({"role": key[0], "word": key[1],
                        "snapped_synset_id": key[2], "stratum": "flagged"})
    flagged_keys = {(e["role"], e["word"], e["snapped_synset_id"]) for e in flagged}

    flagged_pool = [e for e in flagged
                    if (e["role"], e["word"], e["snapped_synset_id"]) not in labelled]
    random_pool = [
        e for e in distinct_endpoints(chains)
        if (e["role"], e["word"], e["snapped_synset_id"]) not in flagged_keys
        and (e["role"], e["word"], e["snapped_synset_id"]) not in labelled
    ]

    rng = random.Random(seed)
    return _take(flagged_pool, n_flagged, rng) + _take(random_pool, n_random, rng)
