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
