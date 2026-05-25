"""Tests for rotation.py — pair pool management and subset selection."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from rotation import compute_shared_mrr, get_failure_limit, load_pool, select_subset, PairPool, Subset


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
    assert abs(len(subset.pair_ids) - expected) <= 3


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
