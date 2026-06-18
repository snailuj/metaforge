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


def context_for(role: str, word: str, synset_id: str, chains: list[dict]) -> list[dict]:
    """Every chain the endpoint appears in (pairing + steps), for the context panel.

    Matched on role's synset_id AND word, so the same synset under a different
    surface word isn't conflated."""
    sfield = "topic_synset_id" if role == "topic" else "vehicle_synset_id"
    wfield = "topic" if role == "topic" else "vehicle"
    out: list[dict] = []
    for c in chains:
        if str(c.get(sfield)) == str(synset_id) and c.get(wfield) == word:
            out.append({"topic": c.get("topic"), "vehicle": c.get("vehicle"),
                        "chain": c.get("chain", []),
                        "chain_signature": c.get("chain_signature")})
    return out


def build_sample_items(endpoints: list[dict], candidates: dict[str, list[dict]],
                       glosses: dict[str, dict], chains: list[dict]) -> list[dict]:
    """Enrich sampled endpoints with snapped gloss/POS, candidate senses, context.

    `glosses` = synset_id -> {pos, definition} (the chain_glosses precompute, reused
    for the SNAPPED gloss). `candidates` = lemma -> [senses] (the new precompute, the
    picker list). Both degrade gracefully to None / [] when absent."""
    items: list[dict] = []
    for e in endpoints:
        sid, word, role = e["snapped_synset_id"], e["word"], e["role"]
        g = glosses.get(sid, {})
        ctx = context_for(role, word, sid, chains)
        items.append({
            "role": role, "word": word, "snapped_synset_id": sid,
            "stratum": e.get("stratum", "random"),
            "snapped_gloss": g.get("definition"), "pos": g.get("pos"),
            "candidates": candidates.get(word, []),
            "context": {"chains": ctx},
            "chain_signature": ctx[0]["chain_signature"] if ctx else None,
        })
    return items


def load_sense_candidates(read_jsonl, candidates_path) -> dict[str, list[dict]]:
    """lemma -> [senses] from the precompute (DB-free). Missing file -> {}."""
    rows, _ = read_jsonl(candidates_path)
    return {r["lemma"]: r.get("senses", []) for r in rows if r.get("lemma")}


def load_snapped_glosses(read_jsonl, glosses_path) -> dict[str, dict]:
    """synset_id -> {pos, definition} from chain_glosses. Missing file -> {}."""
    rows, _ = read_jsonl(glosses_path)
    return {r["synset_id"]: {"pos": r.get("pos"), "definition": r.get("definition")}
            for r in rows if r.get("synset_id")}
