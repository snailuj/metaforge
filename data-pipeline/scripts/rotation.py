"""Pair pool management and rotated subset selection for evolution v2.

Loads the metaphor pair fixture, assigns stable IDs, and selects subsets
with tiered quotas and controlled overlap between generations.
"""
import hashlib
import json
import random
from dataclasses import dataclass, field


@dataclass
class PairPool:
    """Loaded pair pool with indexing structures."""
    pairs: list[dict]
    pair_ids: list[str]
    by_tier: dict[str, list[str]] = field(default_factory=dict)
    archetypal_ids: list[str] = field(default_factory=list)
    version: str = ""


def load_pool(path: str) -> PairPool:
    """Load pair pool from JSON, assign stable IDs, index by tier.

    Each pair gets an 'id' field of format 'source:target'.
    Pool version is a SHA-256 hash of the raw file contents.
    """
    with open(path) as f:
        raw = f.read()
    version = "sha256:" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    pairs = json.loads(raw)
    for p in pairs:
        p["id"] = f"{p['source']}:{p['target']}"

    pair_ids = [p["id"] for p in pairs]

    by_tier: dict[str, list[str]] = {}
    for p in pairs:
        by_tier.setdefault(p["tier"], []).append(p["id"])

    archetypal_ids = [p["id"] for p in pairs if p.get("register") == "archetypal"]

    return PairPool(
        pairs=pairs,
        pair_ids=pair_ids,
        by_tier=by_tier,
        archetypal_ids=archetypal_ids,
        version=version,
    )


@dataclass
class Subset:
    """A selected subset of the pair pool for one generation."""
    pair_ids: list[str]
    seed: int
    carried_from_parent: list[str] = field(default_factory=list)
    fresh_ids: list[str] = field(default_factory=list)


def select_subset(
    pool: PairPool,
    fraction: float = 0.65,
    seed: int = 0,
    previous_subset: "Subset | None" = None,
    carry_fraction: float = 0.50,
    min_archetypal: int = 2,
) -> Subset:
    """Select a rotated subset of the pool with tiered quotas.

    Args:
        pool: Full pair pool.
        fraction: Fraction of pool to include (~0.65).
        seed: RNG seed for reproducibility.
        previous_subset: If provided, carry over carry_fraction of its pairs.
        carry_fraction: Fraction of previous subset to carry over (0.50).
        min_archetypal: Minimum archetypal-register pairs in subset.

    Returns:
        Subset with pair_ids, seed, and overlap tracking.
    """
    rng = random.Random(seed)
    target_size = round(fraction * len(pool.pairs))

    # Compute per-tier quotas proportional to pool distribution
    tier_quotas: dict[str, int] = {}
    for tier, ids in pool.by_tier.items():
        tier_quotas[tier] = round(len(ids) / len(pool.pairs) * target_size)

    # Adjust for rounding — match target_size exactly
    total_quota = sum(tier_quotas.values())
    if total_quota != target_size:
        largest = max(tier_quotas, key=lambda t: tier_quotas[t])
        tier_quotas[largest] += target_size - total_quota

    carried: list[str] = []
    if previous_subset:
        prev_by_tier: dict[str, list[str]] = {}
        prev_set = set(previous_subset.pair_ids)
        for tier, ids in pool.by_tier.items():
            prev_by_tier[tier] = [pid for pid in ids if pid in prev_set]

        for tier, prev_ids in prev_by_tier.items():
            n_carry = round(carry_fraction * len(prev_ids))
            n_carry = min(n_carry, tier_quotas.get(tier, 0))
            rng_copy = random.Random(seed + hash(tier))
            sample = rng_copy.sample(prev_ids, min(n_carry, len(prev_ids)))
            carried.extend(sample)

    carried_set = set(carried)

    # Fill remaining quota per tier from non-carried pairs
    selected: list[str] = list(carried)
    fresh: list[str] = []
    for tier, quota in tier_quotas.items():
        already = sum(1 for pid in selected if pid in set(pool.by_tier[tier]))
        remaining = quota - already
        if remaining <= 0:
            continue
        candidates = [pid for pid in pool.by_tier[tier] if pid not in carried_set]
        sample = rng.sample(candidates, min(remaining, len(candidates)))
        selected.extend(sample)
        if previous_subset:
            prev_set = set(previous_subset.pair_ids)
            fresh.extend(pid for pid in sample if pid not in prev_set)
        else:
            fresh.extend(sample)

    # Guarantee minimum archetypal pairs
    arch_in = [pid for pid in selected if pid in set(pool.archetypal_ids)]
    if len(arch_in) < min_archetypal:
        missing = [pid for pid in pool.archetypal_ids if pid not in set(selected)]
        needed = min(min_archetypal - len(arch_in), len(missing))
        extras = rng.sample(missing, needed)
        selected.extend(extras)

    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for pid in selected:
        if pid not in seen:
            seen.add(pid)
            deduped.append(pid)

    return Subset(
        pair_ids=deduped,
        seed=seed,
        carried_from_parent=carried,
        fresh_ids=fresh,
    )


def compute_shared_mrr(
    parent_per_pair: list[dict],
    parent_subset_ids: list[str],
    child_per_pair: list[dict],
    child_subset_ids: list[str],
) -> dict:
    """Compute MRR on pairs shared between parent and child subsets.

    Returns dict with shared_ids, parent_mrr_shared, child_mrr_shared,
    and shared_delta.
    """
    parent_set = set(parent_subset_ids)
    child_set = set(child_subset_ids)
    shared = sorted(parent_set & child_set)

    if not shared:
        return {
            "shared_ids": [],
            "parent_mrr_shared": 0.0,
            "child_mrr_shared": 0.0,
            "shared_delta": 0.0,
        }

    def _mrr_for_pairs(per_pair: list[dict], pair_ids: set[str]) -> float:
        rrs = []
        for pp in per_pair:
            pid = f"{pp['source']}:{pp['target']}"
            if pid in pair_ids:
                rrs.append(pp.get("reciprocal_rank", 0.0))
        return sum(rrs) / len(rrs) if rrs else 0.0

    shared_set = set(shared)
    parent_mrr = _mrr_for_pairs(parent_per_pair, shared_set)
    child_mrr = _mrr_for_pairs(child_per_pair, shared_set)

    return {
        "shared_ids": shared,
        "parent_mrr_shared": parent_mrr,
        "child_mrr_shared": child_mrr,
        "shared_delta": child_mrr - parent_mrr,
    }
