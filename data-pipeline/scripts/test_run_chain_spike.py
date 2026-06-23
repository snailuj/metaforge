"""Tests for run_chain_spike.build_prompt — pure-function coverage only.

No Sonnet calls are made here; T28 / operator triggers run the actual spike.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_chain_spike import build_prompt


def test_prompt_requests_phrase_and_head():
    p = build_prompt(
        topic="anger", gloss="strong emotion",
        haiku_metaphors=[{"vehicle": "fire", "shared_features": [{"concept": "heat"}]}],
    )
    assert '"phrase"' in p
    assert '"head"' in p


def test_prompt_requests_emitted_gloss_per_step():
    # emit-the-sense: every step must carry the model's intended one-line sense,
    # so the downstream snap is gloss-matched rather than lowest-id guesswork.
    p = build_prompt(
        topic="anger", gloss="strong emotion",
        haiku_metaphors=[{"vehicle": "fire", "shared_features": [{"concept": "heat"}]}],
    )
    assert '"gloss"' in p                 # third step key requested
    assert p.count('"gloss"') >= 2        # in the key spec AND the JSON shape
    assert "sense" in p.lower()           # explains it's the intended sense


def test_prompt_includes_anti_examples_when_provided():
    p = build_prompt(
        topic="anger", gloss="g",
        haiku_metaphors=[{"vehicle": "fire", "shared_features": []}],
        anti_examples=[{"chain": ["anger", "x", "fire"], "notes": "padding sideways"}],
    )
    assert "AVOID" in p.upper() or "Avoid" in p
    assert "padding sideways" in p


def test_prompt_omits_anti_examples_block_when_empty():
    p1 = build_prompt(topic="anger", gloss="g",
                      haiku_metaphors=[{"vehicle": "fire", "shared_features": []}])
    p2 = build_prompt(topic="anger", gloss="g",
                      haiku_metaphors=[{"vehicle": "fire", "shared_features": []}],
                      anti_examples=[])
    # No anti-example block in either
    assert "AVOID" not in p1.upper()
    assert "AVOID" not in p2.upper()


def test_prompt_lists_haiku_vehicles_with_their_features():
    p = build_prompt(topic="anger", gloss="g", haiku_metaphors=[
        {"vehicle": "fire", "shared_features": [{"concept": "heat"}, {"concept": "burning"}]},
        {"vehicle": "volcano", "shared_features": [{"concept": "pressure"}]},
    ])
    assert "fire" in p and "heat" in p and "burning" in p
    assert "volcano" in p and "pressure" in p


def test_prompt_includes_avoid_vehicles_when_provided():
    """Sonnet has creative licence to SUBSTITUTE vehicles, so it must also see
    the over-used list — a soft diversity nudge against the corpus-wide head."""
    p = build_prompt(
        topic="anger", gloss="g",
        haiku_metaphors=[{"vehicle": "fire", "shared_features": []}],
        avoid_vehicles=["fermentation", "undertow"],
    )
    assert "over-used" in p.lower()
    assert "fermentation" in p
    assert "undertow" in p
    assert "unless" in p.lower()  # soft, not a hard ban


def test_prompt_omits_avoid_block_when_absent_or_empty():
    p1 = build_prompt(topic="anger", gloss="g",
                      haiku_metaphors=[{"vehicle": "fire", "shared_features": []}])
    p2 = build_prompt(topic="anger", gloss="g",
                      haiku_metaphors=[{"vehicle": "fire", "shared_features": []}],
                      avoid_vehicles=[])
    assert "over-used" not in p1.lower()
    assert "over-used" not in p2.lower()


def test_prompt_requires_context_free_hops():
    """Each adjacent pair must read as apt in isolation, not leaning on context
    accumulated earlier in the chain — so an edge stays valid when reused by a
    different path (the reusable-edge property the metaphor graph relies on)."""
    p = build_prompt(
        topic="anger", gloss="g",
        haiku_metaphors=[{"vehicle": "fire", "shared_features": []}],
    ).lower()
    assert "stand on its own" in p
    assert "in isolation" in p
    assert "context accumulated earlier" in p
