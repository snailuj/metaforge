# Evolution v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement pair rotation, paired-comparison survival gate, dynamic stopping, and Bradley-Terry ranking for the evolutionary prompt optimisation pipeline.

**Architecture:** New `rotation.py` module handles subset selection and overlap tracking. `evolve_prompts.py` gains new TrialResult fields and uses the rotation module + paired-comparison gate instead of naive MRR comparison. New `bradley_terry.py` module provides cross-lineage ranking. All changes are backwards-compatible with v1 experiment logs.

**Tech Stack:** Python 3.12, numpy (already installed), pytest. No new dependencies — Bradley-Terry implemented from scratch using numpy (iterative MLE, ~30 lines).

**Design doc:** `docs/plans/2026-02-12-evolution-v2-design.md`

**Test runner:** `.venv/bin/python -m pytest scripts/<test_file>.py -v` (run from `data-pipeline/`)

**Fixture:** `data-pipeline/fixtures/metaphor_pairs_v2.json` (274 pairs, already committed)

---

## Task 1: Rotation Module — Pool Loading and Pair IDs

**Files:**
- Create: `data-pipeline/scripts/rotation.py`
- Test: `data-pipeline/scripts/test_rotation.py`

Each pair needs a stable ID for logging. Use `"{source}:{target}"` format.

**Step 1: Write failing tests**

```python
# test_rotation.py
"""Tests for rotation.py — pair pool management and subset selection."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from rotation import load_pool, PairPool


def test_load_pool_assigns_stable_ids(tmp_path):
    """Each pair gets a stable id in 'source:target' format."""
    fixture = [
        {"source": "anger", "target": "fire", "tier": "strong", "domain": "emotion", "register": None},
        {"source": "hope", "target": "light", "tier": "strong", "domain": "emotion", "register": None},
    ]
    path = tmp_path / "pairs.json"
    path.write_text(json.dumps(fixture))

    pool = load_pool(str(path))
    assert pool.pair_ids == ["anger:fire", "hope:light"]
    assert len(pool.pairs) == 2
    assert pool.pairs[0]["id"] == "anger:fire"


def test_load_pool_groups_by_tier(tmp_path):
    """Pool groups pairs by tier for quota-based selection."""
    fixture = [
        {"source": "a", "target": "b", "tier": "strong", "domain": "emotion", "register": None},
        {"source": "c", "target": "d", "tier": "medium", "domain": "emotion", "register": None},
        {"source": "e", "target": "f", "tier": "weak", "domain": "emotion", "register": None},
        {"source": "g", "target": "h", "tier": "strong", "domain": "cognition", "register": None},
    ]
    path = tmp_path / "pairs.json"
    path.write_text(json.dumps(fixture))

    pool = load_pool(str(path))
    assert len(pool.by_tier["strong"]) == 2
    assert len(pool.by_tier["medium"]) == 1
    assert len(pool.by_tier["weak"]) == 1


def test_pool_version_is_stable_hash(tmp_path):
    """Pool version is a SHA-256 hash of the file contents."""
    fixture = [{"source": "a", "target": "b", "tier": "strong", "domain": "emotion", "register": None}]
    path = tmp_path / "pairs.json"
    path.write_text(json.dumps(fixture))

    pool1 = load_pool(str(path))
    pool2 = load_pool(str(path))
    assert pool1.version == pool2.version
    assert pool1.version.startswith("sha256:")
    assert len(pool1.version) > 10


def test_pool_archetypal_pairs(tmp_path):
    """Pool tracks archetypal-register pairs separately."""
    fixture = [
        {"source": "soul", "target": "bird", "tier": "strong", "domain": "body", "register": "archetypal"},
        {"source": "a", "target": "b", "tier": "strong", "domain": "emotion", "register": None},
    ]
    path = tmp_path / "pairs.json"
    path.write_text(json.dumps(fixture))

    pool = load_pool(str(path))
    assert pool.archetypal_ids == ["soul:bird"]
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest scripts/test_rotation.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_pool'`

**Step 3: Implement**

```python
# rotation.py
"""Pair pool management and rotated subset selection for evolution v2.

Loads the metaphor pair fixture, assigns stable IDs, and selects subsets
with tiered quotas and controlled overlap between generations.
"""
import hashlib
import json
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
    raw = open(path).read()
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
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest scripts/test_rotation.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add data-pipeline/scripts/rotation.py data-pipeline/scripts/test_rotation.py
git commit -m "Feat: rotation module — pool loading with stable IDs and tier indexing"
```

---

## Task 2: Rotation Module — Subset Selection with Tiered Quotas

**Files:**
- Modify: `data-pipeline/scripts/rotation.py`
- Modify: `data-pipeline/scripts/test_rotation.py`

**Step 1: Write failing tests**

Add to `test_rotation.py`:

```python
from rotation import load_pool, select_subset, PairPool


def _make_pool(tmp_path, n_strong=30, n_medium=40, n_weak=30, n_archetypal=4):
    """Helper: create a pool with given tier distribution."""
    pairs = []
    for i in range(n_strong):
        reg = "archetypal" if i < n_archetypal else None
        pairs.append({"source": f"s{i}", "target": f"ts{i}", "tier": "strong", "domain": "emotion", "register": reg})
    for i in range(n_medium):
        pairs.append({"source": f"m{i}", "target": f"tm{i}", "tier": "medium", "domain": "cognition", "register": None})
    for i in range(n_weak):
        pairs.append({"source": f"w{i}", "target": f"tw{i}", "tier": "weak", "domain": "nature", "register": None})
    path = tmp_path / "pairs.json"
    path.write_text(json.dumps(pairs))
    return load_pool(str(path))


def test_select_subset_respects_fraction(tmp_path):
    """Subset size is approximately fraction * pool size."""
    pool = _make_pool(tmp_path)
    subset = select_subset(pool, fraction=0.65, seed=42)
    expected = int(0.65 * 100)
    assert abs(len(subset.pair_ids) - expected) <= 3  # rounding tolerance


def test_select_subset_maintains_tier_proportions(tmp_path):
    """Subset tier distribution matches pool tier distribution within tolerance."""
    pool = _make_pool(tmp_path)
    subset = select_subset(pool, fraction=0.65, seed=42)

    pool_strong_frac = len(pool.by_tier["strong"]) / len(pool.pairs)
    subset_strong_count = sum(1 for pid in subset.pair_ids if pid in set(pool.by_tier["strong"]))
    subset_strong_frac = subset_strong_count / len(subset.pair_ids)

    assert abs(subset_strong_frac - pool_strong_frac) < 0.05


def test_select_subset_deterministic(tmp_path):
    """Same seed produces same subset."""
    pool = _make_pool(tmp_path)
    s1 = select_subset(pool, fraction=0.65, seed=42)
    s2 = select_subset(pool, fraction=0.65, seed=42)
    assert s1.pair_ids == s2.pair_ids


def test_select_subset_different_seeds_differ(tmp_path):
    """Different seeds produce different subsets."""
    pool = _make_pool(tmp_path)
    s1 = select_subset(pool, fraction=0.65, seed=42)
    s2 = select_subset(pool, fraction=0.65, seed=99)
    assert s1.pair_ids != s2.pair_ids


def test_select_subset_includes_archetypal(tmp_path):
    """Subset includes at least 2 archetypal pairs."""
    pool = _make_pool(tmp_path, n_archetypal=4)
    subset = select_subset(pool, fraction=0.65, seed=42)
    arch_in_subset = [pid for pid in subset.pair_ids if pid in set(pool.archetypal_ids)]
    assert len(arch_in_subset) >= 2
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest scripts/test_rotation.py::test_select_subset_respects_fraction -v`
Expected: FAIL — `ImportError: cannot import name 'select_subset'`

**Step 3: Implement**

Add to `rotation.py`:

```python
import random
from dataclasses import dataclass, field


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
        # Add/remove from the largest tier
        largest = max(tier_quotas, key=lambda t: tier_quotas[t])
        tier_quotas[largest] += target_size - total_quota

    carried: list[str] = []
    if previous_subset:
        # Carry over carry_fraction of previous subset, maintaining tier proportions
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
        # Track which are fresh (not in previous subset)
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
    seen = set()
    deduped = []
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
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest scripts/test_rotation.py -v`
Expected: PASS (9 tests)

**Step 5: Commit**

```bash
git add data-pipeline/scripts/rotation.py data-pipeline/scripts/test_rotation.py
git commit -m "Feat: rotation subset selection with tiered quotas and controlled overlap"
```

---

## Task 3: Rotation Module — Shared-Pair MRR Computation

**Files:**
- Modify: `data-pipeline/scripts/rotation.py`
- Modify: `data-pipeline/scripts/test_rotation.py`

The paired-comparison gate needs to compute MRR on shared pairs only.

**Step 1: Write failing tests**

Add to `test_rotation.py`:

```python
from rotation import compute_shared_mrr


def test_shared_mrr_filters_to_shared_pairs():
    """Only pairs present in both subsets contribute to MRR."""
    parent_per_pair = [
        {"source": "a", "target": "b", "rank": 1, "reciprocal_rank": 1.0},
        {"source": "c", "target": "d", "rank": 2, "reciprocal_rank": 0.5},
        {"source": "e", "target": "f", "rank": None, "reciprocal_rank": 0.0},
    ]
    parent_subset_ids = ["a:b", "c:d", "e:f"]

    child_per_pair = [
        {"source": "a", "target": "b", "rank": 2, "reciprocal_rank": 0.5},
        {"source": "c", "target": "d", "rank": 1, "reciprocal_rank": 1.0},
        {"source": "g", "target": "h", "rank": 3, "reciprocal_rank": 0.333},
    ]
    child_subset_ids = ["a:b", "c:d", "g:h"]

    result = compute_shared_mrr(
        parent_per_pair=parent_per_pair,
        parent_subset_ids=parent_subset_ids,
        child_per_pair=child_per_pair,
        child_subset_ids=child_subset_ids,
    )

    # Shared pairs: a:b and c:d
    assert result["shared_ids"] == ["a:b", "c:d"]
    assert result["parent_mrr_shared"] == (1.0 + 0.5) / 2  # 0.75
    assert result["child_mrr_shared"] == (0.5 + 1.0) / 2  # 0.75
    assert result["shared_delta"] == 0.0


def test_shared_mrr_positive_delta():
    """Positive delta when child outperforms parent on shared pairs."""
    parent_per_pair = [
        {"source": "a", "target": "b", "rank": 10, "reciprocal_rank": 0.1},
    ]
    child_per_pair = [
        {"source": "a", "target": "b", "rank": 1, "reciprocal_rank": 1.0},
    ]
    result = compute_shared_mrr(
        parent_per_pair=parent_per_pair,
        parent_subset_ids=["a:b"],
        child_per_pair=child_per_pair,
        child_subset_ids=["a:b"],
    )
    assert result["shared_delta"] == pytest.approx(0.9)


def test_shared_mrr_no_overlap_returns_zero():
    """When no shared pairs, all MRR values are 0.0."""
    result = compute_shared_mrr(
        parent_per_pair=[{"source": "a", "target": "b", "rank": 1, "reciprocal_rank": 1.0}],
        parent_subset_ids=["a:b"],
        child_per_pair=[{"source": "c", "target": "d", "rank": 1, "reciprocal_rank": 1.0}],
        child_subset_ids=["c:d"],
    )
    assert result["shared_ids"] == []
    assert result["parent_mrr_shared"] == 0.0
    assert result["child_mrr_shared"] == 0.0
    assert result["shared_delta"] == 0.0
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest scripts/test_rotation.py::test_shared_mrr_filters_to_shared_pairs -v`
Expected: FAIL — `ImportError: cannot import name 'compute_shared_mrr'`

**Step 3: Implement**

Add to `rotation.py`:

```python
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
```

**Step 4: Run tests**

Run: `.venv/bin/python -m pytest scripts/test_rotation.py -v`
Expected: PASS (12 tests)

**Step 5: Commit**

```bash
git add data-pipeline/scripts/rotation.py data-pipeline/scripts/test_rotation.py
git commit -m "Feat: compute shared-pair MRR for paired-comparison survival gate"
```

---

## Task 4: Dynamic Stopping — Failure Limit by Generation

**Files:**
- Modify: `data-pipeline/scripts/rotation.py`
- Modify: `data-pipeline/scripts/test_rotation.py`

Pure function, no dependencies on the rest of the system.

**Step 1: Write failing tests**

Add to `test_rotation.py`:

```python
from rotation import get_failure_limit


def test_failure_limit_gen_1_to_3():
    """Generations 1-3 have failure limit 5."""
    assert get_failure_limit(1) == 5
    assert get_failure_limit(2) == 5
    assert get_failure_limit(3) == 5


def test_failure_limit_gen_4_to_6():
    """Generations 4-6 have failure limit 3."""
    assert get_failure_limit(4) == 3
    assert get_failure_limit(5) == 3
    assert get_failure_limit(6) == 3


def test_failure_limit_gen_7_to_10():
    """Generations 7-10 have failure limit 2."""
    assert get_failure_limit(7) == 2
    assert get_failure_limit(8) == 2
    assert get_failure_limit(10) == 2
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest scripts/test_rotation.py::test_failure_limit_gen_1_to_3 -v`
Expected: FAIL — `ImportError: cannot import name 'get_failure_limit'`

**Step 3: Implement**

Add to `rotation.py`:

```python
def get_failure_limit(generation: int) -> int:
    """Return the consecutive failure limit for a given generation.

    Dynamic schedule:
        gen 1-3: 5 (early exploration)
        gen 4-6: 3 (narrowing)
        gen 7+:  2 (plateau detection)
    """
    if generation <= 3:
        return 5
    elif generation <= 6:
        return 3
    else:
        return 2
```

**Step 4: Run tests**

Run: `.venv/bin/python -m pytest scripts/test_rotation.py -v`
Expected: PASS (15 tests)

**Step 5: Commit**

```bash
git add data-pipeline/scripts/rotation.py data-pipeline/scripts/test_rotation.py
git commit -m "Feat: dynamic consecutive failure limit by generation"
```

---

## Task 5: Bradley-Terry Module

**Files:**
- Create: `data-pipeline/scripts/bradley_terry.py`
- Create: `data-pipeline/scripts/test_bradley_terry.py`

Simple iterative MLE implementation using numpy. No external dependencies.

**Step 1: Write failing tests**

```python
# test_bradley_terry.py
"""Tests for bradley_terry.py — cross-lineage prompt ranking."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from bradley_terry import BradleyTerryRanker


def test_ranker_initial_rating():
    """New prompts start at rating 1500."""
    ranker = BradleyTerryRanker()
    ranker.record_trial("prompt_a", [
        {"source": "a", "target": "b", "reciprocal_rank": 1.0},
    ])
    assert ranker.ratings["prompt_a"] == pytest.approx(1500.0, abs=50)


def test_ranker_better_prompt_higher_rating():
    """A prompt that finds more pairs gets a higher rating."""
    ranker = BradleyTerryRanker()

    good_pairs = [
        {"source": "a", "target": "b", "reciprocal_rank": 1.0},
        {"source": "c", "target": "d", "reciprocal_rank": 0.5},
        {"source": "e", "target": "f", "reciprocal_rank": 0.33},
    ]
    bad_pairs = [
        {"source": "a", "target": "b", "reciprocal_rank": 0.0},
        {"source": "c", "target": "d", "reciprocal_rank": 0.0},
        {"source": "e", "target": "f", "reciprocal_rank": 0.1},
    ]

    ranker.record_trial("good_prompt", good_pairs)
    ranker.record_trial("bad_prompt", bad_pairs)

    assert ranker.ratings["good_prompt"] > ranker.ratings["bad_prompt"]


def test_ranker_get_rating_unknown():
    """Unknown prompt returns default rating."""
    ranker = BradleyTerryRanker()
    assert ranker.get_rating("unknown") == 1500.0


def test_ranker_serialise_round_trip():
    """Ranker state can be saved and restored."""
    ranker = BradleyTerryRanker()
    ranker.record_trial("prompt_a", [
        {"source": "a", "target": "b", "reciprocal_rank": 1.0},
    ])

    state = ranker.to_dict()
    restored = BradleyTerryRanker.from_dict(state)
    assert restored.ratings["prompt_a"] == pytest.approx(ranker.ratings["prompt_a"])


def test_ranker_multiple_trials_accumulate():
    """Multiple trials for the same prompt refine its rating."""
    ranker = BradleyTerryRanker()
    pairs = [{"source": "a", "target": "b", "reciprocal_rank": 1.0}]

    ranker.record_trial("prompt_a", pairs)
    r1 = ranker.ratings["prompt_a"]

    ranker.record_trial("prompt_a", pairs)
    r2 = ranker.ratings["prompt_a"]

    # Rating should be stable or slightly adjusted, not wildly different
    assert abs(r2 - r1) < 100
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest scripts/test_bradley_terry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bradley_terry'`

**Step 3: Implement**

```python
# bradley_terry.py
"""Bradley-Terry ranking for cross-lineage prompt comparison.

Uses a simplified ELO-style update rather than full MLE:
each pair in a trial is a "match" — the prompt's reciprocal rank
determines the win probability, and the rating updates accordingly.

This gives a single scalar rating per prompt variant that stabilises
after ~10-15 trials, answering "which lineage should we invest in?"
"""
import numpy as np


DEFAULT_RATING = 1500.0
K_FACTOR = 32.0  # ELO K-factor — controls update magnitude


class BradleyTerryRanker:
    """Track and update prompt variant ratings across trials.

    Each trial's per-pair results update the prompt's rating using
    ELO-style updates where the "opponent" is a virtual baseline
    prompt at the default rating.
    """

    def __init__(self, k_factor: float = K_FACTOR):
        self.ratings: dict[str, float] = {}
        self.trial_counts: dict[str, int] = {}
        self.k_factor = k_factor

    def record_trial(
        self,
        prompt_id: str,
        per_pair: list[dict],
    ) -> float:
        """Record a trial's results and update the prompt's rating.

        Args:
            prompt_id: Unique identifier for the prompt variant.
            per_pair: List of dicts with 'reciprocal_rank' field.

        Returns:
            Updated rating for this prompt.
        """
        if prompt_id not in self.ratings:
            self.ratings[prompt_id] = DEFAULT_RATING
            self.trial_counts[prompt_id] = 0

        rating = self.ratings[prompt_id]
        self.trial_counts[prompt_id] += 1

        # Compute actual score: mean reciprocal rank across pairs
        rrs = [p.get("reciprocal_rank", 0.0) for p in per_pair]
        actual_score = float(np.mean(rrs)) if rrs else 0.0

        # Expected score from current rating vs baseline
        expected = 1.0 / (1.0 + 10.0 ** ((DEFAULT_RATING - rating) / 400.0))

        # Update
        rating += self.k_factor * (actual_score - expected)
        self.ratings[prompt_id] = rating

        return rating

    def get_rating(self, prompt_id: str) -> float:
        """Get the current rating for a prompt (default if unknown)."""
        return self.ratings.get(prompt_id, DEFAULT_RATING)

    def to_dict(self) -> dict:
        """Serialise ranker state."""
        return {
            "ratings": dict(self.ratings),
            "trial_counts": dict(self.trial_counts),
            "k_factor": self.k_factor,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BradleyTerryRanker":
        """Restore ranker from serialised state."""
        ranker = cls(k_factor=data.get("k_factor", K_FACTOR))
        ranker.ratings = dict(data.get("ratings", {}))
        ranker.trial_counts = dict(data.get("trial_counts", {}))
        return ranker
```

**Step 4: Run tests**

Run: `.venv/bin/python -m pytest scripts/test_bradley_terry.py -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add data-pipeline/scripts/bradley_terry.py data-pipeline/scripts/test_bradley_terry.py
git commit -m "Feat: Bradley-Terry ELO ranker for cross-lineage prompt comparison"
```

---

## Task 6: Extend TrialResult with v2 Instrumentation Fields

**Files:**
- Modify: `data-pipeline/scripts/evolve_prompts.py`
- Modify: `data-pipeline/scripts/test_evolve_prompts.py`

Add the 8 new fields from the design doc. Backward-compatible defaults.

**Step 1: Write failing tests**

Add to `test_evolve_prompts.py`:

```python
def test_trial_result_v2_fields():
    """TrialResult has v2 instrumentation fields with defaults."""
    t = TrialResult(
        trial_id="test", prompt_name="test", prompt_text="x",
        mrr=0.1, per_pair=[], secondary={}, parent_id=None,
        generation=0, mutation=None, survived=True,
        timestamp="2026-01-01",
    )
    # v1 defaults
    assert t.enrichment_coverage == 1.0
    assert t.valid is True
    # v2 defaults
    assert t.mrr_shared is None
    assert t.parent_mrr_shared is None
    assert t.shared_delta is None
    assert t.eval_subset is None
    assert t.shared_with_parent is None
    assert t.rotation_seed is None
    assert t.pool_version is None
    assert t.elo_rating is None


def test_trial_result_v2_fields_serialise(tmp_path):
    """v2 fields survive JSON round-trip."""
    t = TrialResult(
        trial_id="test", prompt_name="test", prompt_text="x",
        mrr=0.1, per_pair=[], secondary={}, parent_id=None,
        generation=0, mutation=None, survived=True,
        timestamp="2026-01-01",
        mrr_shared=0.09, parent_mrr_shared=0.08,
        shared_delta=0.01, eval_subset=["a:b", "c:d"],
        shared_with_parent=["a:b"], rotation_seed=42,
        pool_version="sha256:abc123", elo_rating=1523.4,
    )
    d = asdict(t)
    assert d["mrr_shared"] == 0.09
    assert d["eval_subset"] == ["a:b", "c:d"]
    assert d["elo_rating"] == 1523.4

    # Round-trip via JSON
    out = tmp_path / "t.json"
    out.write_text(json.dumps(d))
    loaded = json.loads(out.read_text())
    t2 = TrialResult(**loaded)
    assert t2.mrr_shared == 0.09
    assert t2.rotation_seed == 42
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest scripts/test_evolve_prompts.py::test_trial_result_v2_fields -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'mrr_shared'`

**Step 3: Modify TrialResult in `evolve_prompts.py`**

Add after the existing default fields (`enrichment_coverage`, `valid`):

```python
@dataclass
class TrialResult:
    """Record of a single prompt evaluation trial."""
    trial_id: str
    prompt_name: str
    prompt_text: str
    mrr: float
    per_pair: list[dict]
    secondary: dict
    parent_id: Optional[str]
    generation: int
    mutation: Optional[str]
    survived: bool
    timestamp: str
    enrichment_coverage: float = 1.0
    valid: bool = True
    # v2 instrumentation
    mrr_shared: Optional[float] = None
    parent_mrr_shared: Optional[float] = None
    shared_delta: Optional[float] = None
    eval_subset: Optional[list[str]] = None
    shared_with_parent: Optional[list[str]] = None
    rotation_seed: Optional[int] = None
    pool_version: Optional[str] = None
    elo_rating: Optional[float] = None
```

**Step 4: Run tests**

Run: `.venv/bin/python -m pytest scripts/test_evolve_prompts.py -v`
Expected: PASS (all existing + 2 new)

**Step 5: Commit**

```bash
git add data-pipeline/scripts/evolve_prompts.py data-pipeline/scripts/test_evolve_prompts.py
git commit -m "Feat: extend TrialResult with v2 instrumentation fields"
```

---

## Task 7: Wire Rotation into evaluate_mrr

**Files:**
- Modify: `data-pipeline/scripts/evaluate_mrr.py`
- Modify: `data-pipeline/scripts/test_evaluate_mrr.py`

The `evaluate()` function currently loads all pairs. It needs to accept an optional `eval_subset` parameter — a list of pair IDs to filter down to. This keeps the rotation logic in the orchestrator while the evaluator just filters.

**Step 1: Write failing test**

Add to `test_evaluate_mrr.py`:

```python
def test_evaluate_filters_to_eval_subset(mock_pipeline, mock_server, tmp_path):
    """When eval_subset is provided, only those pairs are queried."""
    pairs_file = tmp_path / "pairs.json"
    pairs_file.write_text(json.dumps([
        {"source": "anger", "target": "fire", "tier": "strong", "domain": "emotion", "register": None},
        {"source": "hope", "target": "light", "tier": "strong", "domain": "emotion", "register": None},
        {"source": "time", "target": "river", "tier": "strong", "domain": "time", "register": None},
    ]))

    # Only eval anger:fire and time:river
    result = evaluate(
        enrichment_file="dummy.json",
        pairs_file=str(pairs_file),
        port=mock_server.port,
        eval_subset=["anger:fire", "time:river"],
    )

    # Should only contain 2 pairs (or fewer if some skipped)
    queried_sources = {p["source"] for p in result["per_pair"]}
    assert "hope" not in queried_sources
```

Note: This test will need to use whatever mock fixtures already exist in `test_evaluate_mrr.py`. Adapt the fixtures/mocks to match the existing test patterns — check the file header for `mock_pipeline`, `mock_server` fixture definitions. If they don't exist by those names, use the existing mock patterns.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest scripts/test_evaluate_mrr.py::test_evaluate_filters_to_eval_subset -v`
Expected: FAIL — `TypeError: evaluate() got an unexpected keyword argument 'eval_subset'`

**Step 3: Modify `evaluate()` in `evaluate_mrr.py`**

Add `eval_subset: list[str] = None` parameter. After loading pairs and before resolving synsets, filter:

```python
def evaluate(
    # ... existing params ...
    eval_subset: list[str] = None,
) -> dict:
    # ... existing code up to pairs loading ...
    pairs = load_metaphor_pairs(pairs_file)

    # Filter to eval subset if provided
    if eval_subset:
        subset_set = set(eval_subset)
        pairs = [p for p in pairs if f"{p['source']}:{p['target']}" in subset_set]

    # ... rest of function unchanged ...
```

**Step 4: Run tests**

Run: `.venv/bin/python -m pytest scripts/test_evaluate_mrr.py -v`
Expected: PASS (all existing + 1 new)

**Step 5: Commit**

```bash
git add data-pipeline/scripts/evaluate_mrr.py data-pipeline/scripts/test_evaluate_mrr.py
git commit -m "Feat: add eval_subset filter to evaluate() for rotation support"
```

---

## Task 8: Wire Rotation + Survival Gate into Exploitation

**Files:**
- Modify: `data-pipeline/scripts/evolve_prompts.py`
- Modify: `data-pipeline/scripts/test_evolve_prompts.py`

This is the biggest change. `run_exploitation()` needs to:
1. Accept a `PairPool` and use `select_subset()` per generation
2. Use `compute_shared_mrr()` for the survival decision instead of raw MRR comparison
3. Apply `get_failure_limit()` instead of a fixed consecutive limit
4. Pass `eval_subset` to the evaluator
5. Track the BradleyTerryRanker
6. Populate all v2 TrialResult fields

**Step 1: Write failing tests**

Add to `test_evolve_prompts.py`:

```python
from rotation import PairPool, Subset


def _make_mock_pool():
    """Create a minimal PairPool for testing."""
    pairs = [
        {"id": "a:b", "source": "a", "target": "b", "tier": "strong", "domain": "emotion", "register": None},
        {"id": "c:d", "source": "c", "target": "d", "tier": "medium", "domain": "cognition", "register": None},
        {"id": "e:f", "source": "e", "target": "f", "tier": "weak", "domain": "nature", "register": None},
    ]
    return PairPool(
        pairs=pairs,
        pair_ids=["a:b", "c:d", "e:f"],
        by_tier={"strong": ["a:b"], "medium": ["c:d"], "weak": ["e:f"]},
        archetypal_ids=[],
        version="sha256:test123",
    )


@patch("evolve_prompts._evaluate_with_backoff")
@patch("evolve_prompts.generate_tweak")
@patch("evolve_prompts.improve_prompt")
def test_exploitation_v2_uses_paired_comparison(mock_improve, mock_tweak, mock_eval, tmp_path):
    """Exploitation uses shared-pair MRR delta > epsilon for survival, not raw MRR."""
    mock_improve.side_effect = lambda prompt, **kw: prompt

    # Parent per_pair on subset [a:b, c:d]
    parent_per_pair = [
        {"source": "a", "target": "b", "rank": 10, "reciprocal_rank": 0.1},
        {"source": "c", "target": "d", "rank": 5, "reciprocal_rank": 0.2},
    ]

    # Tweak returns a modified prompt
    mock_tweak.return_value = {"modified_prompt": "tweaked {batch_items}", "description": "test tweak"}

    # Child scores better on shared pairs — delta > 0.005
    mock_eval.return_value = {
        "mrr": 0.5,
        "per_pair": [
            {"source": "a", "target": "b", "rank": 1, "reciprocal_rank": 1.0},
            {"source": "c", "target": "d", "rank": 2, "reciprocal_rank": 0.5},
        ],
        "secondary": {},
        "valid": True,
        "enrichment_coverage": 1.0,
    }

    pool = _make_mock_pool()
    trials = run_exploitation(
        survivor_name="test",
        survivor_prompt="original {batch_items}",
        survivor_mrr=0.15,
        per_pair=parent_per_pair,
        max_tweaks=1,
        model="haiku",
        port=9999,
        output_dir=tmp_path,
        pair_pool=pool,
        parent_eval_subset=["a:b", "c:d"],
    )

    assert len(trials) == 1
    assert trials[0].survived is True
    assert trials[0].mrr_shared is not None
    assert trials[0].shared_delta > 0.005
    assert trials[0].eval_subset is not None
    assert trials[0].pool_version == "sha256:test123"


@patch("evolve_prompts._evaluate_with_backoff")
@patch("evolve_prompts.generate_tweak")
@patch("evolve_prompts.improve_prompt")
def test_exploitation_v2_dynamic_failure_limit(mock_improve, mock_tweak, mock_eval, tmp_path):
    """Exploitation uses dynamic failure limit: gen 1-3 allows 5 consecutive failures."""
    mock_improve.side_effect = lambda prompt, **kw: prompt
    mock_tweak.return_value = {"modified_prompt": "tweaked {batch_items}", "description": "test"}

    # Every eval returns worse than parent — should fail
    mock_eval.return_value = {
        "mrr": 0.0,
        "per_pair": [{"source": "a", "target": "b", "rank": None, "reciprocal_rank": 0.0}],
        "secondary": {},
        "valid": True,
        "enrichment_coverage": 1.0,
    }

    pool = _make_mock_pool()
    trials = run_exploitation(
        survivor_name="test",
        survivor_prompt="original {batch_items}",
        survivor_mrr=0.15,
        per_pair=[{"source": "a", "target": "b", "rank": 5, "reciprocal_rank": 0.2}],
        max_tweaks=10,
        model="haiku",
        port=9999,
        output_dir=tmp_path,
        pair_pool=pool,
        parent_eval_subset=["a:b"],
    )

    # Dynamic limit for gen 1-3 is 5, so should stop after 5 failures
    assert len(trials) == 5
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest scripts/test_evolve_prompts.py::test_exploitation_v2_uses_paired_comparison -v`
Expected: FAIL — `TypeError: run_exploitation() got an unexpected keyword argument 'pair_pool'`

**Step 3: Modify `run_exploitation()` in `evolve_prompts.py`**

Add new parameters: `pair_pool`, `parent_eval_subset`, `ranker`, `survival_epsilon`.

Key changes:
1. Import `select_subset`, `compute_shared_mrr`, `get_failure_limit`, `Subset` from `rotation`
2. Import `BradleyTerryRanker` from `bradley_terry`
3. Each generation calls `select_subset(pool, seed=..., previous_subset=...)`
4. Pass `eval_subset=subset.pair_ids` to `_evaluate_with_backoff`
5. Use `compute_shared_mrr()` + epsilon for survival decision
6. Use `get_failure_limit(gen)` instead of fixed `consecutive_failure_limit`
7. Populate all v2 TrialResult fields

The modification is substantial but localised to `run_exploitation()`. Here is the updated function signature and core loop logic:

```python
def run_exploitation(
    survivor_name: str,
    survivor_prompt: str,
    survivor_mrr: float,
    per_pair: list[dict],
    max_tweaks: int = 10,
    consecutive_failure_limit: int = 3,  # v1 compat; ignored if pair_pool provided
    model: str = "haiku",
    enrich_size: int = 700,
    port: int = 9091,
    output_dir: Path = None,
    verbose: bool = False,
    exploit_model: str = "haiku",
    improver_model: str = "sonnet",
    fixture_vocab: frozenset[str] = None,
    # v2 parameters
    pair_pool: "PairPool | None" = None,
    parent_eval_subset: "list[str] | None" = None,
    ranker: "BradleyTerryRanker | None" = None,
    survival_epsilon: float = 0.005,
) -> list[TrialResult]:
```

Inside the loop, the key change for each generation:

```python
    # v2: select rotated subset
    if pair_pool is not None:
        seed = hash((survivor_name, gen)) & 0xFFFFFFFF
        prev_subset = Subset(pair_ids=current_eval_subset, seed=0) if current_eval_subset else None
        subset = select_subset(pair_pool, seed=seed, previous_subset=prev_subset)
        eval_pair_ids = subset.pair_ids
    else:
        eval_pair_ids = None
        subset = None

    result = _evaluate_with_backoff(
        prompt_template=tweak["modified_prompt"],
        model=model,
        enrich_size=enrich_size,
        port=port,
        verbose=verbose,
        eval_subset=eval_pair_ids,
    )

    # v2: paired comparison on shared pairs
    if pair_pool is not None and current_eval_subset:
        shared = compute_shared_mrr(
            parent_per_pair=current_per_pair,
            parent_subset_ids=current_eval_subset,
            child_per_pair=result["per_pair"],
            child_subset_ids=eval_pair_ids,
        )
        improved = trial_valid and shared["shared_delta"] > survival_epsilon
    else:
        # v1 fallback
        improved = trial_valid and result["mrr"] > current_mrr

    # v2: dynamic failure limit
    if pair_pool is not None:
        failure_limit = get_failure_limit(gen)
    else:
        failure_limit = consecutive_failure_limit
```

Fill the v2 TrialResult fields:

```python
    trial = TrialResult(
        # ... existing fields ...
        mrr_shared=shared["child_mrr_shared"] if pair_pool else None,
        parent_mrr_shared=shared["parent_mrr_shared"] if pair_pool else None,
        shared_delta=shared["shared_delta"] if pair_pool else None,
        eval_subset=eval_pair_ids,
        shared_with_parent=shared["shared_ids"] if pair_pool else None,
        rotation_seed=subset.seed if subset else None,
        pool_version=pair_pool.version if pair_pool else None,
        elo_rating=ranker.get_rating(trial_id) if ranker else None,
    )
```

After recording the trial, update the ranker:

```python
    if ranker:
        ranker.record_trial(trial_id, result["per_pair"])
        trial.elo_rating = ranker.get_rating(trial_id)
```

**Step 4: Run tests**

Run: `.venv/bin/python -m pytest scripts/test_evolve_prompts.py -v`
Expected: PASS (all existing + 2 new)

**Step 5: Commit**

```bash
git add data-pipeline/scripts/evolve_prompts.py data-pipeline/scripts/test_evolve_prompts.py
git commit -m "Feat: wire rotation, paired-comparison gate, and dynamic stopping into exploitation"
```

---

## Task 9: Wire Rotation into Exploration and run_experiment

**Files:**
- Modify: `data-pipeline/scripts/evolve_prompts.py`
- Modify: `data-pipeline/scripts/test_evolve_prompts.py`

Exploration also needs rotation: each exploration trial should use a rotated subset (with no carry-over since there's no parent). The `run_experiment()` function needs to load the pool, create the ranker, and thread them through.

**Step 1: Write failing test**

```python
@patch("evolve_prompts._evaluate_with_backoff")
def test_exploration_v2_populates_eval_subset(mock_eval, tmp_path):
    """Exploration trials record eval_subset when pool is provided."""
    mock_eval.return_value = {
        "mrr": 0.1,
        "per_pair": [{"source": "a", "target": "b", "rank": 5, "reciprocal_rank": 0.2}],
        "secondary": {},
        "valid": True,
        "enrichment_coverage": 1.0,
    }

    pool = _make_mock_pool()
    trials = run_exploration(
        prompts={"test_prompt": "Test {batch_items}"},
        baseline_prompt="Baseline {batch_items}",
        model="haiku",
        port=9999,
        output_dir=tmp_path,
        pair_pool=pool,
    )

    # Baseline + 1 prompt = 2 trials
    assert len(trials) == 2
    for t in trials:
        assert t.eval_subset is not None
        assert t.pool_version == "sha256:test123"
```

**Step 2: Run test to verify it fails**

Expected: FAIL — `TypeError: run_exploration() got an unexpected keyword argument 'pair_pool'`

**Step 3: Modify `run_exploration()` and `run_experiment()`**

Add `pair_pool` parameter to `run_exploration()`. When provided, select a subset per trial (no carry-over) and pass `eval_subset` to the evaluator.

In `run_experiment()`:
1. Load pool from `metaphor_pairs_v2.json` (or `--pairs` arg)
2. Create `BradleyTerryRanker`
3. Pass pool and ranker to both exploration and exploitation
4. Update CLI to accept `--pairs` pointing to v2 fixture
5. Update `DEFAULT_PAIRS` in evaluate_mrr.py to point to `metaphor_pairs_v2.json`

**Step 4: Run tests**

Run: `.venv/bin/python -m pytest scripts/test_evolve_prompts.py -v`
Expected: PASS (all existing + 1 new)

**Step 5: Commit**

```bash
git add data-pipeline/scripts/evolve_prompts.py data-pipeline/scripts/test_evolve_prompts.py
git commit -m "Feat: wire rotation and ranker into exploration and run_experiment"
```

---

## Task 10: Update Report Generator

**Files:**
- Modify: `data-pipeline/scripts/generate_evolution_report.py`
- Modify: `data-pipeline/scripts/test_generate_evolution_report.py`

The existing report generator needs to surface the new v2 fields. Key additions:

1. Show rotation stats in the summary (pool size, subset size, overlap %)
2. Show shared-pair delta alongside raw MRR in the summary table
3. Show ELO ratings in the cross-lineage comparison
4. Add a rotation coverage section (how many unique pairs were tested across all trials)

**Step 1: Write failing tests**

```python
def test_summary_table_includes_shared_delta():
    """Summary table shows shared_delta when present."""
    trials = [_make_trial(
        trial_id="test",
        mrr=0.1,
        mrr_shared=0.09,
        shared_delta=0.01,
    )]
    table = _build_summary_table(trials)
    assert "shared_delta" in table.lower() or "0.01" in table


def test_elo_section_present_when_ratings_exist():
    """Report includes ELO ranking section when ratings are available."""
    trials = [
        _make_trial(trial_id="a", elo_rating=1550.0),
        _make_trial(trial_id="b", elo_rating=1480.0),
    ]
    report = generate_evolution_report(trials)
    assert "1550" in report
    assert "1480" in report
```

Note: Adapt `_make_trial` helper and `_build_summary_table`/`generate_evolution_report` to match whatever naming the existing test file uses. Read the existing test file first.

**Step 2-5: Implement, test, commit**

Follow TDD cycle. The report changes are additive — existing sections remain, new sections are appended.

```bash
git commit -m "Feat: surface v2 rotation stats, shared deltas, and ELO in evolution report"
```

---

## Task 11: Update DEFAULT_PAIRS and CLI

**Files:**
- Modify: `data-pipeline/scripts/evaluate_mrr.py` (line 39: `DEFAULT_PAIRS`)
- Modify: `data-pipeline/scripts/evolve_prompts.py` (CLI `--pairs` default)

**Step 1: Write failing test**

```python
def test_default_pairs_points_to_v2():
    """DEFAULT_PAIRS should reference metaphor_pairs_v2.json."""
    from evaluate_mrr import DEFAULT_PAIRS
    assert DEFAULT_PAIRS.name == "metaphor_pairs_v2.json"
```

**Step 2: Run test to verify it fails**

Expected: FAIL — `assert 'metaphor_pairs.json' == 'metaphor_pairs_v2.json'`

**Step 3: Modify**

In `evaluate_mrr.py` line 39:
```python
DEFAULT_PAIRS = FIXTURES_DIR / "metaphor_pairs_v2.json"
```

In `evolve_prompts.py`, update `run_experiment()` default pairs_file and CLI.

**Step 4: Run all tests**

Run: `.venv/bin/python -m pytest scripts/ -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git commit -m "Feat: switch default fixture to metaphor_pairs_v2.json (274 pairs)"
```

---

## Task 12: Integration Test — Full v2 Dry Run

**Files:**
- Modify: `data-pipeline/scripts/test_evolve_prompts.py`

Verify the full system hangs together with a mocked dry run that exercises the v2 code path.

**Step 1: Write test**

```python
@patch("evolve_prompts._evaluate_with_backoff")
def test_full_v2_experiment_mocked(mock_eval, tmp_path):
    """Full mocked experiment exercises rotation, paired comparison, ELO."""
    call_count = 0

    def mock_eval_fn(**kwargs):
        nonlocal call_count
        call_count += 1
        return {
            "mrr": 0.1 + call_count * 0.01,
            "per_pair": [
                {"source": "a", "target": "b", "rank": max(1, 10 - call_count),
                 "reciprocal_rank": 1.0 / max(1, 10 - call_count)},
            ],
            "secondary": {"unique_properties": 100},
            "valid": True,
            "enrichment_coverage": 1.0,
        }

    mock_eval.side_effect = mock_eval_fn

    pool = _make_mock_pool()

    # Run exploration
    trials = run_exploration(
        prompts={"test": "Test {batch_items}"},
        baseline_prompt="Baseline {batch_items}",
        model="haiku",
        port=9999,
        output_dir=tmp_path,
        pair_pool=pool,
    )

    assert len(trials) == 2
    assert all(t.pool_version is not None for t in trials)

    # Verify experiment log is valid JSON
    log_path = tmp_path / "exploration_log.json"
    assert log_path.exists()
    loaded = json.loads(log_path.read_text())
    assert len(loaded) == 2
```

**Step 2-5: Run, verify pass, commit**

```bash
git commit -m "Test: integration test for v2 rotation + paired comparison flow"
```

---

## Task 13: Update EVOLVE_README

**Files:**
- Modify: `data-pipeline/scripts/EVOLVE_README.md`

Update the documentation to reflect v2 changes:
- New fixture (274 pairs, v2 schema)
- Rotation algorithm
- Paired-comparison gate
- Dynamic stopping
- Bradley-Terry ranking
- New CLI flags
- Updated run counts

**Step 1: Update the README**

No TDD needed — documentation only.

**Step 2: Commit**

```bash
git commit -m "Docs: update EVOLVE_README for v2 rotation, survival criteria, and ELO"
```

---

## Summary

| Task | Description | New tests |
|:---:|---|:---:|
| 1 | Rotation: pool loading + pair IDs | 4 |
| 2 | Rotation: subset selection + tiered quotas | 5 |
| 3 | Rotation: shared-pair MRR computation | 3 |
| 4 | Dynamic stopping: failure limit by generation | 3 |
| 5 | Bradley-Terry ELO ranker | 5 |
| 6 | Extend TrialResult with v2 fields | 2 |
| 7 | Wire rotation into evaluate_mrr | 1 |
| 8 | Wire rotation + survival gate into exploitation | 2 |
| 9 | Wire rotation into exploration + run_experiment | 1 |
| 10 | Update report generator | 2 |
| 11 | Switch DEFAULT_PAIRS to v2 | 1 |
| 12 | Integration test | 1 |
| 13 | Update EVOLVE_README | 0 |
| **Total** | | **30** |

Estimated: ~30 new tests, 13 atomic commits, 3 new files, 5 modified files.
