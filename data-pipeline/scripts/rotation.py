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
