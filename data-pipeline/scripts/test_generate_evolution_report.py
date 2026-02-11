"""Tests for generate_evolution_report.py — comprehensive evolution experiment report.

All LLM-calling tests mock invoke_claude — no real API calls.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


# ---------------------------------------------------------------------------
# Fixtures: reusable trial data
# ---------------------------------------------------------------------------

def _make_trial(
    trial_id, prompt_name, mrr, generation=0, survived=True,
    parent_id=None, mutation=None, prompt_text="P {batch_items}",
    per_pair=None, secondary=None,
):
    """Build a trial dict matching experiment_log.json schema."""
    return {
        "trial_id": trial_id,
        "prompt_name": prompt_name,
        "prompt_text": prompt_text,
        "mrr": mrr,
        "per_pair": per_pair or [
            {"source": "anger", "target": "fire", "rank": 1,
             "reciprocal_rank": 1.0, "tier": "strong"},
            {"source": "joy", "target": "fountain", "rank": None,
             "reciprocal_rank": 0.0, "tier": "medium"},
        ],
        "secondary": secondary or {
            "unique_properties": 100,
            "hapax_count": 60,
            "hapax_rate": 0.6,
            "avg_properties_per_synset": 11.0,
        },
        "parent_id": parent_id,
        "generation": generation,
        "mutation": mutation,
        "survived": survived,
        "timestamp": "2026-02-12T10:00:00+00:00",
    }


@pytest.fixture
def sample_trials():
    """Minimal realistic trial set: baseline + 2 explore + 1 exploit."""
    return [
        _make_trial("baseline", "baseline", 0.08, survived=True),
        _make_trial("explore-alpha", "alpha", 0.10, survived=True),
        _make_trial("explore-beta", "beta", 0.05, survived=False),
        _make_trial(
            "exploit-alpha-g1", "alpha", 0.12,
            generation=1, survived=True,
            parent_id="explore-alpha", mutation="Added emphasis",
        ),
    ]


@pytest.fixture
def sample_pairs():
    """Minimal metaphor pairs fixture."""
    return [
        {"source": "anger", "target": "fire", "tier": "strong"},
        {"source": "joy", "target": "fountain", "tier": "medium"},
        {"source": "time", "target": "river", "tier": "strong"},
    ]


# ===========================================================================
# 1. Data loading
# ===========================================================================

def test_load_experiment_log_returns_list_of_dicts(tmp_path):
    """load_experiment_log reads JSON array and returns list of dicts."""
    from generate_evolution_report import load_experiment_log

    data = [_make_trial("baseline", "baseline", 0.08)]
    log_file = tmp_path / "log.json"
    log_file.write_text(json.dumps(data))

    result = load_experiment_log(log_file)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["trial_id"] == "baseline"


def test_load_experiment_log_raises_on_missing_file(tmp_path):
    """load_experiment_log raises FileNotFoundError for missing file."""
    from generate_evolution_report import load_experiment_log

    with pytest.raises(FileNotFoundError):
        load_experiment_log(tmp_path / "nonexistent.json")


def test_load_metaphor_pairs_returns_list_of_dicts(tmp_path):
    """load_metaphor_pairs reads JSON array of pair dicts."""
    from generate_evolution_report import load_metaphor_pairs

    pairs = [{"source": "anger", "target": "fire", "tier": "strong"}]
    pair_file = tmp_path / "pairs.json"
    pair_file.write_text(json.dumps(pairs))

    result = load_metaphor_pairs(pair_file)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["source"] == "anger"
