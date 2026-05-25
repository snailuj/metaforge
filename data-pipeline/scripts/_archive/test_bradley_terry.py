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
