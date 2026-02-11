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


# ===========================================================================
# 2. Helper functions
# ===========================================================================

def test_baseline_trial_returns_baseline(sample_trials):
    """_baseline_trial returns the trial with trial_id 'baseline'."""
    from generate_evolution_report import _baseline_trial

    result = _baseline_trial(sample_trials)
    assert result["trial_id"] == "baseline"
    assert result["mrr"] == 0.08


def test_exploration_trials_returns_gen0_non_baseline(sample_trials):
    """_exploration_trials returns gen 0 trials excluding baseline."""
    from generate_evolution_report import _exploration_trials

    result = _exploration_trials(sample_trials)
    ids = [t["trial_id"] for t in result]
    assert "baseline" not in ids
    assert "explore-alpha" in ids
    assert "explore-beta" in ids
    assert len(result) == 2


def test_exploitation_trials_returns_gen_above_0(sample_trials):
    """_exploitation_trials returns trials with generation > 0."""
    from generate_evolution_report import _exploitation_trials

    result = _exploitation_trials(sample_trials)
    assert len(result) == 1
    assert result[0]["trial_id"] == "exploit-alpha-g1"


def test_non_degenerate_trials_excludes_mrr_zero():
    """_non_degenerate_trials filters out MRR=0 trials."""
    from generate_evolution_report import _non_degenerate_trials

    trials = [
        _make_trial("t1", "a", 0.10),
        _make_trial("t2", "b", 0.0),
        _make_trial("t3", "c", 0.05),
    ]
    result = _non_degenerate_trials(trials)
    assert len(result) == 2
    assert all(t["mrr"] > 0 for t in result)


def test_best_trial_returns_highest_mrr(sample_trials):
    """_best_trial returns the trial with the highest MRR."""
    from generate_evolution_report import _best_trial

    result = _best_trial(sample_trials)
    assert result["trial_id"] == "exploit-alpha-g1"
    assert result["mrr"] == 0.12


def test_lineages_groups_by_prompt_name(sample_trials):
    """_lineages groups trials by prompt_name, sorted by generation."""
    from generate_evolution_report import _lineages

    result = _lineages(sample_trials)
    assert "baseline" in result
    assert "alpha" in result
    assert "beta" in result
    # alpha lineage should be sorted: gen 0 then gen 1
    alpha = result["alpha"]
    assert alpha[0]["generation"] == 0
    assert alpha[1]["generation"] == 1


def test_pearson_r_perfect_correlation():
    """_pearson_r returns 1.0 for perfectly correlated data."""
    from generate_evolution_report import _pearson_r

    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [2.0, 4.0, 6.0, 8.0, 10.0]
    r = _pearson_r(xs, ys)
    assert abs(r - 1.0) < 1e-10


def test_pearson_r_negative_correlation():
    """_pearson_r returns -1.0 for perfectly negatively correlated data."""
    from generate_evolution_report import _pearson_r

    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [10.0, 8.0, 6.0, 4.0, 2.0]
    r = _pearson_r(xs, ys)
    assert abs(r - (-1.0)) < 1e-10


def test_pearson_r_insufficient_data():
    """_pearson_r returns 0.0 for fewer than 3 data points."""
    from generate_evolution_report import _pearson_r

    assert _pearson_r([1.0], [2.0]) == 0.0
    assert _pearson_r([1.0, 2.0], [3.0, 4.0]) == 0.0


def test_avg_rr_by_pair(sample_trials):
    """_avg_rr_by_pair computes mean reciprocal rank per source→target pair."""
    from generate_evolution_report import _avg_rr_by_pair

    result = _avg_rr_by_pair(sample_trials)
    # anger→fire has RR=1.0 in all 4 trials
    assert "anger → fire" in result
    assert result["anger → fire"] == 1.0
    # joy→fountain has RR=0.0 in all 4 trials
    assert result["joy → fountain"] == 0.0


def test_tier_mrr_split(sample_trials):
    """_tier_mrr_split returns average MRR per tier across non-degenerate trials."""
    from generate_evolution_report import _tier_mrr_split

    result = _tier_mrr_split(sample_trials)
    assert "strong" in result
    assert "medium" in result


def test_hit_rate_computes_fraction_found():
    """_hit_rate returns fraction of pairs with reciprocal_rank > 0."""
    from generate_evolution_report import _hit_rate

    trial = _make_trial("t", "a", 0.5, per_pair=[
        {"source": "a", "target": "b", "reciprocal_rank": 1.0, "tier": "s"},
        {"source": "c", "target": "d", "reciprocal_rank": 0.0, "tier": "s"},
        {"source": "e", "target": "f", "reciprocal_rank": 0.5, "tier": "m"},
    ])
    from generate_evolution_report import _hit_rate
    assert abs(_hit_rate(trial) - 2.0 / 3.0) < 1e-10


def test_format_pct_positive():
    """_format_pct formats positive percentage with + prefix."""
    from generate_evolution_report import _format_pct

    assert _format_pct(0.254) == "+25.4%"


def test_format_pct_negative():
    """_format_pct formats negative percentage with - prefix."""
    from generate_evolution_report import _format_pct

    assert _format_pct(-0.15) == "-15.0%"


def test_format_correlation_descriptions():
    """_format_correlation maps r values to English descriptions."""
    from generate_evolution_report import _format_correlation

    assert "strong positive" == _format_correlation(0.85)
    assert "moderate positive" == _format_correlation(0.55)
    assert "weak" in _format_correlation(0.15)
    assert "strong negative" == _format_correlation(-0.85)
    assert "moderate negative" == _format_correlation(-0.55)
