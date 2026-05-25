"""Tests for seed_exploration.py — inject external MRR results into exploration log."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from seed_exploration import build_trial_result, seed_exploration_log


# --- 1. build_trial_result populates correct fields --------------------------

def test_build_trial_result_fields():
    """build_trial_result creates a TrialResult-compatible dict with correct fields."""
    mrr_results = {
        "mrr": 0.095,
        "per_pair": [{"source": "a", "target": "b", "rank": 1, "reciprocal_rank": 1.0}],
        "secondary": {"unique_properties": 100},
    }
    result = build_trial_result("persona_poet", "Poet prompt {batch_items}", mrr_results, baseline_mrr=0.08)

    assert result["trial_id"] == "explore-persona_poet"
    assert result["prompt_name"] == "persona_poet"
    assert result["prompt_text"] == "Poet prompt {batch_items}"
    assert result["mrr"] == 0.095
    assert result["per_pair"] == mrr_results["per_pair"]
    assert result["secondary"] == mrr_results["secondary"]
    assert result["parent_id"] is None
    assert result["generation"] == 0
    assert result["mutation"] is None
    assert result["survived"] is True  # 0.095 > 0.08
    # v2 fields should be None
    assert result["mrr_shared"] is None
    assert result["parent_mrr_shared"] is None
    assert result["shared_delta"] is None


def test_build_trial_result_does_not_survive():
    """build_trial_result sets survived=False when MRR <= baseline."""
    mrr_results = {
        "mrr": 0.05,
        "per_pair": [],
        "secondary": {},
    }
    result = build_trial_result("bad_prompt", "Bad {batch_items}", mrr_results, baseline_mrr=0.08)
    assert result["survived"] is False


# --- 2. seed_exploration_log appends to existing log -------------------------

def test_seed_appends_to_existing_log(tmp_path):
    """seed_exploration_log appends a new entry to a log that already has baseline."""
    log_path = tmp_path / "exploration_log.json"
    existing = [{
        "trial_id": "baseline",
        "prompt_name": "baseline",
        "prompt_text": "Baseline {batch_items}",
        "mrr": 0.08,
        "per_pair": [],
        "secondary": {},
        "parent_id": None,
        "generation": 0,
        "mutation": None,
        "survived": True,
        "timestamp": "2026-02-13T00:00:00",
        "enrichment_coverage": 1.0,
        "valid": True,
    }]
    log_path.write_text(json.dumps(existing))

    mrr_file = tmp_path / "mrr_results.json"
    mrr_file.write_text(json.dumps({
        "mrr": 0.095,
        "per_pair": [{"source": "a", "target": "b", "rank": 1, "reciprocal_rank": 1.0}],
        "secondary": {"unique_properties": 50},
    }))

    seed_exploration_log(str(mrr_file), "persona_poet", str(log_path))

    with open(log_path) as f:
        log = json.load(f)
    assert len(log) == 2
    assert log[1]["trial_id"] == "explore-persona_poet"
    assert log[1]["mrr"] == 0.095


# --- 3. seed_exploration_log rejects duplicate prompt_name -------------------

def test_seed_rejects_duplicate(tmp_path):
    """seed_exploration_log raises ValueError if prompt_name already in log."""
    log_path = tmp_path / "exploration_log.json"
    existing = [
        {
            "trial_id": "baseline", "prompt_name": "baseline",
            "prompt_text": "B", "mrr": 0.08, "per_pair": [], "secondary": {},
            "parent_id": None, "generation": 0, "mutation": None,
            "survived": True, "timestamp": "2026-02-13T00:00:00",
        },
        {
            "trial_id": "explore-persona_poet", "prompt_name": "persona_poet",
            "prompt_text": "P", "mrr": 0.09, "per_pair": [], "secondary": {},
            "parent_id": None, "generation": 0, "mutation": None,
            "survived": True, "timestamp": "2026-02-13T00:01:00",
        },
    ]
    log_path.write_text(json.dumps(existing))

    mrr_file = tmp_path / "mrr_results.json"
    mrr_file.write_text(json.dumps({"mrr": 0.10, "per_pair": [], "secondary": {}}))

    with pytest.raises(ValueError, match="already in log"):
        seed_exploration_log(str(mrr_file), "persona_poet", str(log_path))


# --- 4. seed_exploration_log creates log if missing --------------------------

def test_seed_creates_log_if_missing(tmp_path):
    """seed_exploration_log works when no existing log file exists."""
    log_path = tmp_path / "exploration_log.json"
    assert not log_path.exists()

    mrr_file = tmp_path / "mrr_results.json"
    mrr_file.write_text(json.dumps({
        "mrr": 0.095,
        "per_pair": [],
        "secondary": {},
    }))

    # No baseline in log means baseline_mrr defaults to 0.0
    seed_exploration_log(str(mrr_file), "persona_poet", str(log_path))

    with open(log_path) as f:
        log = json.load(f)
    assert len(log) == 1
    assert log[0]["trial_id"] == "explore-persona_poet"
    assert log[0]["survived"] is True  # any positive MRR > 0.0
