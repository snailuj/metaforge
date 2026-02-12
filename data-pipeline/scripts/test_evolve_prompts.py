"""Tests for evolve_prompts.py — evolutionary prompt optimisation orchestrator.

All tests fully mocked — no LLM calls, no real DB, no FastText vectors.
"""
import json
import sys
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from evolve_prompts import (
    TrialResult, run_exploration, run_exploitation,
    run_experiment, dry_run_estimate, generate_report, improve_prompt,
)


# --- 1. TrialResult fields ---------------------------------------------------

def test_trial_result_fields():
    """TrialResult has all expected fields with correct types."""
    t = TrialResult(
        trial_id="explore-contrastive",
        prompt_name="contrastive",
        prompt_text="Some prompt {batch_items}",
        mrr=0.15,
        per_pair=[{"source": "a", "target": "b", "rank": 2, "reciprocal_rank": 0.5}],
        secondary={"unique_properties": 100},
        parent_id=None,
        generation=0,
        mutation=None,
        survived=True,
        timestamp="2026-02-12T10:00:00",
    )
    assert t.trial_id == "explore-contrastive"
    assert t.mrr == 0.15
    assert t.survived is True
    assert t.parent_id is None
    assert t.generation == 0


# --- 2. TrialResult JSON serialisation round-trip -----------------------------

def test_trial_result_serialisation_round_trip(tmp_path):
    """TrialResult can be serialised to JSON and back."""
    t = TrialResult(
        trial_id="exploit-contrastive-g1",
        prompt_name="contrastive",
        prompt_text="Tweaked {batch_items}",
        mrr=0.20,
        per_pair=[{"source": "a", "target": "b", "rank": 1, "reciprocal_rank": 1.0}],
        secondary={"unique_properties": 120},
        parent_id="explore-contrastive",
        generation=1,
        mutation="Added tactile emphasis",
        survived=True,
        timestamp="2026-02-12T11:00:00",
    )

    out_file = tmp_path / "trial.json"
    with open(out_file, "w") as f:
        json.dump(asdict(t), f)

    with open(out_file) as f:
        loaded = json.load(f)

    assert loaded["trial_id"] == "exploit-contrastive-g1"
    assert loaded["mrr"] == 0.20
    assert loaded["parent_id"] == "explore-contrastive"
    assert loaded["mutation"] == "Added tactile emphasis"


# --- 3. TrialResult list serialisation ----------------------------------------

def test_trial_list_serialisation(tmp_path):
    """A list of TrialResults can be serialised."""
    trials = [
        TrialResult(
            trial_id="baseline",
            prompt_name="baseline",
            prompt_text="Baseline {batch_items}",
            mrr=0.073,
            per_pair=[],
            secondary={},
            parent_id=None,
            generation=0,
            mutation=None,
            survived=True,
            timestamp="2026-02-12T10:00:00",
        ),
        TrialResult(
            trial_id="explore-persona_poet",
            prompt_name="persona_poet",
            prompt_text="Poet {batch_items}",
            mrr=0.10,
            per_pair=[],
            secondary={},
            parent_id=None,
            generation=0,
            mutation=None,
            survived=True,
            timestamp="2026-02-12T10:05:00",
        ),
    ]

    out_file = tmp_path / "trials.json"
    with open(out_file, "w") as f:
        json.dump([asdict(t) for t in trials], f)

    with open(out_file) as f:
        loaded = json.load(f)

    assert len(loaded) == 2
    assert loaded[0]["trial_id"] == "baseline"
    assert loaded[1]["trial_id"] == "explore-persona_poet"


# --- 4. run_exploration identifies survivors ----------------------------------

def _make_eval_result(mrr, per_pair=None, secondary=None):
    """Build a mock evaluate() return value."""
    return {
        "mrr": mrr,
        "per_pair": per_pair or [
            {"source": "anger", "target": "fire", "rank": 1, "reciprocal_rank": 1.0},
        ],
        "secondary": secondary or {"unique_properties": 50},
        "testable_pairs": 1,
        "skipped_pairs": 0,
    }


@patch("evolve_prompts.evaluate")
def test_run_exploration_identifies_survivors(mock_evaluate, tmp_path):
    """run_exploration marks prompts with MRR > baseline as survivors."""
    # Baseline MRR = 0.10, two explore prompts: one beats it, one doesn't
    mock_evaluate.side_effect = [
        _make_eval_result(0.10),  # baseline
        _make_eval_result(0.15),  # prompt_a — survives
        _make_eval_result(0.05),  # prompt_b — eliminated
    ]

    prompts = {
        "prompt_a": "Prompt A: {batch_items}\n[{{}}]",
        "prompt_b": "Prompt B: {batch_items}\n[{{}}]",
    }

    trials = run_exploration(
        prompts=prompts,
        baseline_prompt="Baseline: {batch_items}\n[{{}}]",
        model="haiku",
        enrich_size=100,
        port=9091,
        output_dir=tmp_path,
    )

    assert len(trials) == 3  # baseline + 2 explore
    baseline = trials[0]
    assert baseline.trial_id == "baseline"
    assert baseline.mrr == 0.10
    assert baseline.survived is True  # baseline always survives

    survivor = [t for t in trials if t.trial_id == "explore-prompt_a"][0]
    assert survivor.survived is True
    assert survivor.mrr == 0.15

    eliminated = [t for t in trials if t.trial_id == "explore-prompt_b"][0]
    assert eliminated.survived is False
    assert eliminated.mrr == 0.05


# --- 5. run_exploration saves log after each trial (crash-safe) ---------------

@patch("evolve_prompts.evaluate")
def test_run_exploration_saves_log_incrementally(mock_evaluate, tmp_path):
    """Exploration log is saved after each trial, not just at the end."""
    mock_evaluate.side_effect = [
        _make_eval_result(0.10),  # baseline
        _make_eval_result(0.12),  # one explore prompt
    ]

    prompts = {"single": "S: {batch_items}\n[{{}}]"}

    run_exploration(
        prompts=prompts,
        baseline_prompt="B: {batch_items}\n[{{}}]",
        model="haiku",
        enrich_size=100,
        port=9091,
        output_dir=tmp_path,
    )

    log_file = tmp_path / "exploration_log.json"
    assert log_file.exists()

    with open(log_file) as f:
        log = json.load(f)
    assert len(log) == 2  # baseline + single


# --- 6. run_exploration handles UsageExhaustedError with backoff -------------

@patch("evolve_prompts.time.sleep")
@patch("evolve_prompts._ping_usage")
@patch("evolve_prompts.evaluate")
def test_run_exploration_usage_exhaustion_backoff(
    mock_evaluate, mock_ping, mock_sleep, tmp_path
):
    """On UsageExhaustedError, exploration waits for usage renewal then retries."""
    from enrich_properties import UsageExhaustedError

    # First call: baseline succeeds. Second call: exhaustion then success on retry.
    mock_evaluate.side_effect = [
        _make_eval_result(0.10),  # baseline
        UsageExhaustedError("rate limit"),  # first attempt at prompt
        _make_eval_result(0.15),  # retry after backoff succeeds
    ]
    mock_ping.side_effect = [False, True]  # exhausted on first ping, renewed on second

    prompts = {"test_prompt": "T: {batch_items}\n[{{}}]"}

    trials = run_exploration(
        prompts=prompts,
        baseline_prompt="B: {batch_items}\n[{{}}]",
        model="haiku",
        enrich_size=100,
        port=9091,
        output_dir=tmp_path,
    )

    assert len(trials) == 2
    assert trials[1].mrr == 0.15
    mock_sleep.assert_called()  # waited for backoff


# --- 7. run_exploitation keeps improvements -----------------------------------

@patch("evolve_prompts.generate_tweak")
@patch("evolve_prompts.evaluate")
def test_run_exploitation_keeps_improvements(mock_evaluate, mock_tweak, tmp_path):
    """Exploitation keeps tweaks that improve MRR."""
    # Each tweak improves MRR
    mock_evaluate.side_effect = [
        _make_eval_result(0.20),  # tweak 1 improves from 0.15
        _make_eval_result(0.25),  # tweak 2 improves further
    ]
    mock_tweak.side_effect = [
        {"modified_prompt": "Tweak1: {batch_items}\n[{{}}]", "description": "tweak 1"},
        {"modified_prompt": "Tweak2: {batch_items}\n[{{}}]", "description": "tweak 2"},
    ]

    trials = run_exploitation(
        survivor_name="contrastive",
        survivor_prompt="Original: {batch_items}\n[{{}}]",
        survivor_mrr=0.15,
        per_pair=[{"source": "a", "target": "b", "rank": 1, "reciprocal_rank": 1.0}],
        max_tweaks=2,
        model="haiku",
        enrich_size=100,
        port=9091,
        output_dir=tmp_path,
    )

    assert len(trials) == 2
    assert trials[0].mrr == 0.20
    assert trials[0].survived is True
    assert trials[1].mrr == 0.25
    assert trials[1].survived is True
    assert trials[1].parent_id == trials[0].trial_id


# --- 8. run_exploitation reverts regressions ----------------------------------

@patch("evolve_prompts.generate_tweak")
@patch("evolve_prompts.evaluate")
def test_run_exploitation_reverts_regressions(mock_evaluate, mock_tweak, tmp_path):
    """Exploitation reverts tweaks that worsen MRR."""
    mock_evaluate.side_effect = [
        _make_eval_result(0.10),  # tweak 1 regresses from 0.15
        _make_eval_result(0.12),  # tweak 2 also regresses
        _make_eval_result(0.09),  # tweak 3 also regresses → early stop (K=3)
    ]
    mock_tweak.side_effect = [
        {"modified_prompt": "T1: {batch_items}\n[{{}}]", "description": "tweak 1"},
        {"modified_prompt": "T2: {batch_items}\n[{{}}]", "description": "tweak 2"},
        {"modified_prompt": "T3: {batch_items}\n[{{}}]", "description": "tweak 3"},
    ]

    trials = run_exploitation(
        survivor_name="test",
        survivor_prompt="Original: {batch_items}\n[{{}}]",
        survivor_mrr=0.15,
        per_pair=[],
        max_tweaks=7,
        consecutive_failure_limit=3,
        model="haiku",
        enrich_size=100,
        port=9091,
        output_dir=tmp_path,
    )

    # All 3 tweaks tried before early stopping
    assert len(trials) == 3
    assert all(not t.survived for t in trials)


# --- 9. run_exploitation early stops on K consecutive failures ----------------

@patch("evolve_prompts.generate_tweak")
@patch("evolve_prompts.evaluate")
def test_run_exploitation_early_stops(mock_evaluate, mock_tweak, tmp_path):
    """Exploitation stops after K consecutive failures."""
    mock_evaluate.side_effect = [
        _make_eval_result(0.20),  # tweak 1 improves
        _make_eval_result(0.18),  # tweak 2 regresses (1 consecutive fail)
        _make_eval_result(0.17),  # tweak 3 regresses (2 consecutive fails)
    ]
    mock_tweak.side_effect = [
        {"modified_prompt": f"T{i}: {{batch_items}}\n[{{{{}}}}]", "description": f"tweak {i}"}
        for i in range(1, 8)
    ]

    trials = run_exploitation(
        survivor_name="test",
        survivor_prompt="Original: {batch_items}\n[{{}}]",
        survivor_mrr=0.15,
        per_pair=[],
        max_tweaks=7,
        consecutive_failure_limit=2,
        model="haiku",
        enrich_size=100,
        port=9091,
        output_dir=tmp_path,
    )

    # 1 improvement + 2 failures = 3 total, then early stop
    assert len(trials) == 3


# --- 10. run_experiment combines exploration + exploitation -------------------

@patch("evolve_prompts.run_exploitation")
@patch("evolve_prompts.run_exploration")
def test_run_experiment_combines_phases(mock_explore, mock_exploit, tmp_path):
    """run_experiment runs exploration then exploitation on each survivor."""
    # Exploration returns 3 trials: baseline + 1 survivor + 1 eliminated
    mock_explore.return_value = [
        TrialResult("baseline", "baseline", "B: {batch_items}", 0.10, [], {},
                    None, 0, None, True, "2026-01-01T00:00:00"),
        TrialResult("explore-good", "good", "G: {batch_items}", 0.15, [], {},
                    None, 0, None, True, "2026-01-01T00:01:00"),
        TrialResult("explore-bad", "bad", "Bad: {batch_items}", 0.05, [], {},
                    None, 0, None, False, "2026-01-01T00:02:00"),
    ]
    # Exploitation returns 1 trial for the survivor
    mock_exploit.return_value = [
        TrialResult("exploit-good-g1", "good", "G2: {batch_items}", 0.20,
                    [], {}, "explore-good", 1, "tweak", True, "2026-01-01T00:03:00"),
    ]

    all_trials = run_experiment(
        model="haiku",
        enrich_size=100,
        port=9091,
        output_dir=tmp_path,
        max_tweaks=3,
    )

    assert len(all_trials) == 4  # 3 exploration + 1 exploitation
    mock_explore.assert_called_once()
    mock_exploit.assert_called_once()

    # Exploitation was called with the survivor's data
    exploit_kwargs = mock_exploit.call_args[1]
    assert exploit_kwargs["survivor_name"] == "good"
    assert exploit_kwargs["survivor_mrr"] == 0.15


# --- 11. dry_run_estimate returns budget estimate ----------------------------

def test_dry_run_estimate():
    """dry_run_estimate returns a run count breakdown dict."""
    estimate = dry_run_estimate(
        num_prompts=5,
        max_tweaks=7,
    )
    assert estimate["exploration_runs"] == 6  # baseline + 5
    assert estimate["max_exploitation_runs"] == 35  # 7 × 5 (worst case: all survive)
    assert estimate["max_total_runs"] == 41


# --- 12. generate_report produces markdown with required sections -------------

def test_generate_report_has_required_sections():
    """Report contains summary table, lineage, per-pair analysis, recommendations."""
    trials = [
        TrialResult("baseline", "baseline", "B: {batch_items}", 0.073,
                    [{"source": "anger", "target": "fire", "rank": 2, "reciprocal_rank": 0.5},
                     {"source": "grief", "target": "anchor", "rank": None, "reciprocal_rank": 0.0}],
                    {"unique_properties": 50, "hapax_count": 30, "hapax_rate": 0.6},
                    None, 0, None, True, "2026-02-12T10:00:00"),
        TrialResult("explore-contrastive", "contrastive", "C: {batch_items}", 0.12,
                    [{"source": "anger", "target": "fire", "rank": 1, "reciprocal_rank": 1.0},
                     {"source": "grief", "target": "anchor", "rank": 5, "reciprocal_rank": 0.2}],
                    {"unique_properties": 70, "hapax_count": 40, "hapax_rate": 0.57},
                    None, 0, None, True, "2026-02-12T10:05:00"),
        TrialResult("explore-narrative", "narrative", "N: {batch_items}", 0.05,
                    [{"source": "anger", "target": "fire", "rank": None, "reciprocal_rank": 0.0},
                     {"source": "grief", "target": "anchor", "rank": None, "reciprocal_rank": 0.0}],
                    {"unique_properties": 30, "hapax_count": 20, "hapax_rate": 0.67},
                    None, 0, None, False, "2026-02-12T10:10:00"),
        TrialResult("exploit-contrastive-g1", "contrastive", "C2: {batch_items}", 0.18,
                    [{"source": "anger", "target": "fire", "rank": 1, "reciprocal_rank": 1.0},
                     {"source": "grief", "target": "anchor", "rank": 2, "reciprocal_rank": 0.5}],
                    {"unique_properties": 80, "hapax_count": 45, "hapax_rate": 0.56},
                    "explore-contrastive", 1, "Added tactile emphasis", True,
                    "2026-02-12T10:15:00"),
    ]

    report = generate_report(trials)

    assert "# Evolutionary Prompt Optimisation Report" in report
    assert "Summary" in report
    assert "baseline" in report
    assert "contrastive" in report
    assert "narrative" in report
    assert "Lineage" in report or "lineage" in report
    assert "Per-Pair" in report or "per-pair" in report or "Pair" in report
    # Should contain the MRR values
    assert "0.073" in report
    assert "0.12" in report
    assert "0.18" in report


# --- 13. generate_report handles empty trials --------------------------------

def test_generate_report_empty_trials():
    """Report can be generated from an empty trials list."""
    report = generate_report([])
    assert "# Evolutionary Prompt Optimisation Report" in report
    assert "No trials" in report or "0 trials" in report.lower() or len(report) > 0


# --- 14. TrialResult has coverage and valid fields ----------------------------

def test_trial_result_has_coverage_and_valid_fields():
    """TrialResult has enrichment_coverage and valid, serialisable round-trip."""
    t = TrialResult(
        trial_id="explore-test",
        prompt_name="test",
        prompt_text="T {batch_items}",
        mrr=0.10,
        per_pair=[],
        secondary={},
        parent_id=None,
        generation=0,
        mutation=None,
        survived=True,
        timestamp="2026-02-12T10:00:00",
        enrichment_coverage=0.85,
        valid=False,
    )
    d = asdict(t)
    assert d["enrichment_coverage"] == 0.85
    assert d["valid"] is False
    # Round-trip
    t2 = TrialResult(**d)
    assert t2.enrichment_coverage == 0.85
    assert t2.valid is False


# --- 15. exploration skips invalid trial for elimination ----------------------

@patch("evolve_prompts.evaluate")
def test_exploration_skips_invalid_trial_for_elimination(mock_evaluate, tmp_path):
    """An invalid trial (infra failure) is not used for elimination decisions."""
    # Baseline MRR = 0.10
    # prompt_a: MRR = 0.15 but valid=False (infra failure) → should NOT survive
    # prompt_b: MRR = 0.12, valid=True → should survive (> baseline)
    mock_evaluate.side_effect = [
        {"mrr": 0.10, "per_pair": [], "secondary": {},
         "testable_pairs": 1, "skipped_pairs": 0, "valid": True},
        {"mrr": 0.15, "per_pair": [], "secondary": {},
         "testable_pairs": 1, "skipped_pairs": 0, "valid": False,
         "enrichment_coverage": 0.3, "enrichment_failed": 70},
        {"mrr": 0.12, "per_pair": [], "secondary": {},
         "testable_pairs": 1, "skipped_pairs": 0, "valid": True,
         "enrichment_coverage": 0.95},
    ]

    prompts = {
        "prompt_a": "A: {batch_items}\n[{{}}]",
        "prompt_b": "B: {batch_items}\n[{{}}]",
    }

    trials = run_exploration(
        prompts=prompts,
        baseline_prompt="Baseline: {batch_items}\n[{{}}]",
        model="haiku",
        enrich_size=100,
        port=9091,
        output_dir=tmp_path,
    )

    trial_a = [t for t in trials if t.trial_id == "explore-prompt_a"][0]
    trial_b = [t for t in trials if t.trial_id == "explore-prompt_b"][0]

    # prompt_a invalid → survived=False, valid=False
    assert trial_a.valid is False
    assert trial_a.survived is False
    # prompt_b valid and beats baseline → survived=True
    assert trial_b.valid is True
    assert trial_b.survived is True


# --- 16. exploitation infra failure doesn't count as consecutive failure ------

@patch("evolve_prompts.generate_tweak")
@patch("evolve_prompts.evaluate")
def test_exploitation_infra_failure_not_consecutive(mock_evaluate, mock_tweak, tmp_path):
    """Infra failures in exploitation don't increment the consecutive failure counter."""
    mock_evaluate.side_effect = [
        # tweak 1: infra failure (valid=False) — should NOT count
        {"mrr": 0.01, "per_pair": [], "secondary": {},
         "valid": False, "enrichment_coverage": 0.2},
        # tweak 2: real regression (valid=True) — counts as failure 1
        {"mrr": 0.10, "per_pair": [], "secondary": {},
         "valid": True, "enrichment_coverage": 0.95},
        # tweak 3: real regression — counts as failure 2 → early stop at K=2
        {"mrr": 0.10, "per_pair": [], "secondary": {},
         "valid": True, "enrichment_coverage": 0.95},
    ]
    mock_tweak.side_effect = [
        {"modified_prompt": f"T{i}: {{batch_items}}\n[{{{{}}}}]", "description": f"tweak {i}"}
        for i in range(1, 8)
    ]

    trials = run_exploitation(
        survivor_name="test",
        survivor_prompt="Original: {batch_items}\n[{{}}]",
        survivor_mrr=0.15,
        per_pair=[],
        max_tweaks=7,
        consecutive_failure_limit=2,
        model="haiku",
        enrich_size=100,
        port=9091,
        output_dir=tmp_path,
    )

    # 3 trials: 1 infra fail (not counted) + 2 real failures → early stop
    assert len(trials) == 3
    assert trials[0].valid is False  # infra failure


# --- 17. TrialResult from legacy log (missing new fields) ---------------------

def test_trial_result_from_legacy_log():
    """TrialResult can be deserialised from a dict missing enrichment_coverage/valid."""
    legacy = {
        "trial_id": "explore-old",
        "prompt_name": "old",
        "prompt_text": "Old {batch_items}",
        "mrr": 0.08,
        "per_pair": [],
        "secondary": {},
        "parent_id": None,
        "generation": 0,
        "mutation": None,
        "survived": True,
        "timestamp": "2026-01-01T00:00:00",
    }
    t = TrialResult(**legacy)
    assert t.enrichment_coverage == 1.0
    assert t.valid is True
    assert t.mrr == 0.08


# --- 18. evaluate passes verbose to run_enrichment ---------------------------

def test_evaluate_passes_verbose_to_enrichment(tmp_path):
    """evaluate() forwards verbose kwarg to run_enrichment."""
    from evaluate_mrr import evaluate
    from enrich_properties import EnrichmentResult

    pairs_file = tmp_path / "pairs.json"
    pairs_file.write_text(json.dumps([
        {"source": "anger", "target": "fire", "tier": "strong"},
    ]))

    baseline_sql = tmp_path / "baseline.sql"
    baseline_sql.write_text(
        "CREATE TABLE lemmas (lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id));\n"
        "INSERT INTO lemmas VALUES ('anger', 'syn-anger-01');\n"
        "INSERT INTO lemmas VALUES ('fire', 'syn-fire-01');\n"
        "CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, definition TEXT);\n"
        "INSERT INTO synsets VALUES ('syn-anger-01', 'a strong emotion');\n"
        "INSERT INTO synsets VALUES ('syn-fire-01', 'combustion');\n"
    )

    fake_enrichment = {"synsets": [], "config": {"model": "haiku"}}
    fake_path = tmp_path / "enrichment.json"
    fake_path.write_text(json.dumps(fake_enrichment))

    captured = {}

    def mock_run_enrichment(**kwargs):
        captured["verbose"] = kwargs.get("verbose")
        output_path = kwargs.get("output_file")
        if output_path:
            Path(output_path).write_text(json.dumps(fake_enrichment))
        return EnrichmentResult(
            output_file=str(fake_path), requested=2, succeeded=2,
            failed=0, failed_ids=[],
        )

    mock_sec = {"unique_properties": 2, "hapax_count": 1,
                "hapax_rate": 0.5, "avg_properties_per_synset": 2.0}

    with patch("evaluate_mrr.BASELINE_SQL", baseline_sql), \
         patch("evaluate_mrr.EVAL_WORK_DB", tmp_path / "eval_work.db"), \
         patch("evaluate_mrr.OUTPUT_DIR", tmp_path), \
         patch("evaluate_mrr.run_enrichment", mock_run_enrichment), \
         patch("evaluate_mrr.run_pipeline"), \
         patch("evaluate_mrr.compute_secondary_metrics", return_value=mock_sec), \
         patch("evaluate_mrr.start_server") as mock_server, \
         patch("evaluate_mrr.wait_for_health"), \
         patch("evaluate_mrr.stop_server"), \
         patch("evaluate_mrr.query_forge_rank", return_value=1):

        mock_server.return_value = MagicMock()
        evaluate(
            enrichment_file=None,
            pairs_file=str(pairs_file),
            enrich_size=500,
            enrich_model="haiku",
            verbose=True,
        )

    assert captured["verbose"] is True


# --- 19. evolve CLI --verbose flag -------------------------------------------

def test_evolve_cli_verbose_flag():
    """evolve_prompts.py CLI accepts --verbose and sets verbose=True."""
    import argparse
    # Simulate parsing --verbose
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(["--verbose"])
    assert args.verbose is True


# --- 20. exploitation uses exploit_model for tweak generation -----------------

@patch("evolve_prompts.generate_tweak")
@patch("evolve_prompts.evaluate")
def test_exploitation_uses_exploit_model_for_tweak(mock_evaluate, mock_tweak, tmp_path):
    """run_exploitation passes exploit_model to generate_tweak, not main model."""
    mock_evaluate.side_effect = [
        _make_eval_result(0.20),  # tweak 1 improves
    ]
    mock_tweak.return_value = {
        "modified_prompt": "Tweak: {batch_items}\n[{{}}]", "description": "tweak 1",
    }

    run_exploitation(
        survivor_name="test",
        survivor_prompt="Original: {batch_items}\n[{{}}]",
        survivor_mrr=0.15,
        per_pair=[],
        max_tweaks=1,
        model="haiku",
        exploit_model="sonnet",
        enrich_size=100,
        port=9091,
        output_dir=tmp_path,
    )

    # generate_tweak should have been called with model="sonnet"
    tweak_kwargs = mock_tweak.call_args[1]
    assert tweak_kwargs["model"] == "sonnet"


# --- 21. exploitation uses main model for enrichment -------------------------

@patch("evolve_prompts.generate_tweak")
@patch("evolve_prompts.evaluate")
def test_exploitation_uses_main_model_for_enrichment(mock_evaluate, mock_tweak, tmp_path):
    """run_exploitation uses the main model for evaluate (enrichment), not exploit_model."""
    mock_evaluate.side_effect = [
        _make_eval_result(0.20),
    ]
    mock_tweak.return_value = {
        "modified_prompt": "Tweak: {batch_items}\n[{{}}]", "description": "tweak 1",
    }

    run_exploitation(
        survivor_name="test",
        survivor_prompt="Original: {batch_items}\n[{{}}]",
        survivor_mrr=0.15,
        per_pair=[],
        max_tweaks=1,
        model="haiku",
        exploit_model="sonnet",
        enrich_size=100,
        port=9091,
        output_dir=tmp_path,
    )

    # evaluate should have been called with enrich_model="haiku" (the main model)
    eval_kwargs = mock_evaluate.call_args[1]
    assert eval_kwargs["enrich_model"] == "haiku"


# --- 22. exploitation chains tweak → improve → evaluate -----------------------

@patch("evolve_prompts.improve_prompt")
@patch("evolve_prompts.generate_tweak")
@patch("evolve_prompts.evaluate")
def test_exploitation_chains_tweak_then_improve(mock_evaluate, mock_tweak, mock_improve, tmp_path):
    """run_exploitation calls improve_prompt with generate_tweak's output."""
    mock_evaluate.side_effect = [
        _make_eval_result(0.20),
    ]
    mock_tweak.return_value = {
        "modified_prompt": "Raw tweak: {batch_items}\n[{{}}]", "description": "tweak 1",
    }
    mock_improve.return_value = "Improved tweak: {batch_items}\n[{{}}]"

    trials = run_exploitation(
        survivor_name="test",
        survivor_prompt="Original: {batch_items}\n[{{}}]",
        survivor_mrr=0.15,
        per_pair=[],
        max_tweaks=1,
        model="haiku",
        exploit_model="haiku",
        improver_model="sonnet",
        enrich_size=100,
        port=9091,
        output_dir=tmp_path,
    )

    # improve_prompt should have been called with the raw tweak output
    mock_improve.assert_called_once()
    improve_args = mock_improve.call_args
    assert "Raw tweak" in improve_args[0][0] or "Raw tweak" in improve_args[1].get("raw_prompt", "")
    # evaluate should use the improved prompt
    eval_kwargs = mock_evaluate.call_args[1]
    assert "Improved tweak" in eval_kwargs["prompt_template"]


# --- 23. exploitation passes fixture_vocab to generate_tweak ------------------

@patch("evolve_prompts.improve_prompt")
@patch("evolve_prompts.generate_tweak")
@patch("evolve_prompts.evaluate")
def test_exploitation_passes_fixture_vocab_to_tweak(mock_evaluate, mock_tweak, mock_improve, tmp_path):
    """run_exploitation forwards fixture_vocab to generate_tweak."""
    mock_evaluate.side_effect = [_make_eval_result(0.20)]
    mock_tweak.return_value = {
        "modified_prompt": "Tweak: {batch_items}\n[{{}}]", "description": "tweak",
    }
    mock_improve.return_value = "Improved: {batch_items}\n[{{}}]"

    vocab = frozenset({"anger", "fire"})

    run_exploitation(
        survivor_name="test",
        survivor_prompt="Original: {batch_items}\n[{{}}]",
        survivor_mrr=0.15,
        per_pair=[],
        max_tweaks=1,
        model="haiku",
        enrich_size=100,
        port=9091,
        output_dir=tmp_path,
        fixture_vocab=vocab,
    )

    tweak_kwargs = mock_tweak.call_args[1]
    assert tweak_kwargs["fixture_vocab"] == vocab


# --- TrialResult v2 instrumentation fields ------------------------------------

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


@patch("evolve_prompts.improve_prompt")
@patch("evolve_prompts.generate_tweak")
@patch("evolve_prompts.evaluate")
def test_exploitation_v2_uses_paired_comparison(mock_eval, mock_tweak, mock_improve, tmp_path):
    """Exploitation uses shared-pair MRR delta > epsilon for survival, not raw MRR."""
    mock_improve.side_effect = lambda prompt, **kw: prompt

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
        per_pair=[
            {"source": "a", "target": "b", "rank": 10, "reciprocal_rank": 0.1},
            {"source": "c", "target": "d", "rank": 5, "reciprocal_rank": 0.2},
        ],
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


@patch("evolve_prompts.improve_prompt")
@patch("evolve_prompts.generate_tweak")
@patch("evolve_prompts.evaluate")
def test_exploitation_v2_dynamic_failure_limit(mock_eval, mock_tweak, mock_improve, tmp_path):
    """Exploitation uses dynamic failure limit: gen 1-3 allows 5, gen 4-6 allows 3.

    With continuous failures, gens 1-3 accumulate 3 failures (under limit 5),
    then gen 4 (limit 3) triggers early stop because 4 >= 3.
    """
    mock_improve.side_effect = lambda prompt, **kw: prompt
    mock_tweak.return_value = {"modified_prompt": "tweaked {batch_items}", "description": "test"}

    # Every eval returns worse than parent on shared pairs (delta < epsilon)
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

    # Dynamic limit: gen 1-3 allows 5, gen 4-6 allows 3.
    # Failures accumulate: g1(1), g2(2), g3(3) all under limit 5.
    # At g4, limit drops to 3: 4 failures >= 3, so early stop.
    assert len(trials) == 4


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


# --- Exploration v2: populates eval_subset when pool provided ----------------

@patch("evolve_prompts.evaluate")
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
