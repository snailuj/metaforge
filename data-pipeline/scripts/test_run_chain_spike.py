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
