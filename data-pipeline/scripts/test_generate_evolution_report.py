"""Tests for generate_evolution_report.py — comprehensive evolution experiment report.

All LLM-calling tests mock invoke_claude — no real API calls.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

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


# ===========================================================================
# 3. Deterministic section generators
# ===========================================================================

def test_section_methodology_mentions_pair_count(sample_trials):
    """section_methodology includes the number of pairs evaluated."""
    from generate_evolution_report import section_methodology

    md = section_methodology(sample_trials)
    assert "## 2. Methodology" in md
    # Should mention exploration prompt count (2 non-baseline gen-0 trials)
    assert "2" in md
    # Should describe MRR scoring
    assert "MRR" in md


def test_section_exploration_results_has_table(sample_trials):
    """section_exploration_results contains a markdown table with all gen-0 trials."""
    from generate_evolution_report import section_exploration_results

    md = section_exploration_results(sample_trials)
    assert "## 3. Exploration Results" in md
    # Table headers
    assert "Prompt" in md
    assert "MRR" in md
    # Should contain baseline and both explore prompts
    assert "baseline" in md
    assert "alpha" in md
    assert "beta" in md


def test_section_exploration_results_sorted_by_mrr_desc(sample_trials):
    """Exploration table rows are sorted by MRR descending."""
    from generate_evolution_report import section_exploration_results

    md = section_exploration_results(sample_trials)
    lines = md.split("\n")
    # Find table data rows (skip header, separator)
    data_rows = [l for l in lines if l.startswith("|") and "Prompt" not in l and "---" not in l]
    mrrs = []
    for row in data_rows:
        cells = [c.strip() for c in row.split("|") if c.strip()]
        # MRR is second column
        mrrs.append(float(cells[1]))
    assert mrrs == sorted(mrrs, reverse=True)


def test_section_cross_generation_analysis_has_correlations():
    """section_cross_generation_analysis includes correlation table."""
    from generate_evolution_report import section_cross_generation_analysis

    trials = [
        _make_trial("t1", "a", 0.10, secondary={
            "unique_properties": 100, "hapax_count": 60,
            "hapax_rate": 0.6, "avg_properties_per_synset": 11.0,
        }),
        _make_trial("t2", "b", 0.15, secondary={
            "unique_properties": 200, "hapax_count": 120,
            "hapax_rate": 0.6, "avg_properties_per_synset": 12.0,
        }),
        _make_trial("t3", "c", 0.20, secondary={
            "unique_properties": 300, "hapax_count": 180,
            "hapax_rate": 0.6, "avg_properties_per_synset": 13.0,
        }),
    ]
    md = section_cross_generation_analysis(trials)
    assert "## 5. Cross-Generation Analysis" in md
    assert "Metric" in md
    assert "unique_properties" in md
    # Should describe correlation strength
    assert "positive" in md or "negative" in md or "weak" in md


def test_section_per_pair_analysis_has_top_10(sample_trials, sample_pairs):
    """section_per_pair_analysis shows easiest, hardest, and never-found pairs."""
    from generate_evolution_report import section_per_pair_analysis

    md = section_per_pair_analysis(sample_trials, sample_pairs)
    assert "## 6. Per-Pair Analysis" in md
    assert "Easiest" in md or "easiest" in md
    assert "Hardest" in md or "hardest" in md


def test_section_per_pair_analysis_tier_split(sample_trials, sample_pairs):
    """section_per_pair_analysis includes tier comparison."""
    from generate_evolution_report import section_per_pair_analysis

    md = section_per_pair_analysis(sample_trials, sample_pairs)
    assert "strong" in md
    assert "medium" in md


def test_section_appendix_prompts_includes_all_unique(sample_trials):
    """section_appendix_prompts shows every unique prompt text in fenced blocks."""
    from generate_evolution_report import section_appendix_prompts

    md = section_appendix_prompts(sample_trials)
    assert "## 8. Appendix A" in md
    assert "```" in md
    # Each trial_id should appear as a label
    for t in sample_trials:
        assert t["trial_id"] in md


def test_section_appendix_per_pair_detail_uses_best_trial(sample_trials):
    """section_appendix_per_pair_detail shows the per-pair table for the best trial."""
    from generate_evolution_report import section_appendix_per_pair_detail

    md = section_appendix_per_pair_detail(sample_trials)
    assert "## 9. Appendix B" in md
    # Best trial is exploit-alpha-g1 (MRR=0.12)
    assert "exploit-alpha-g1" in md
    assert "anger" in md


# ===========================================================================
# 4. LLM prose functions
# ===========================================================================

def test_build_briefing_contains_key_metrics(sample_trials, sample_pairs):
    """_build_briefing returns structured dict with all computed metrics."""
    from generate_evolution_report import _build_briefing

    briefing = _build_briefing(sample_trials, sample_pairs)
    assert "best_trial_id" in briefing
    assert "best_mrr" in briefing
    assert "baseline_mrr" in briefing
    assert "improvement_pct" in briefing
    assert "survivor_count" in briefing
    assert "total_trials" in briefing
    assert "correlations" in briefing
    assert "tier_split" in briefing


def test_executive_summary_prompt_includes_briefing_data(sample_trials, sample_pairs):
    """_executive_summary_prompt produces a prompt containing key metrics."""
    from generate_evolution_report import _build_briefing, _executive_summary_prompt

    briefing = _build_briefing(sample_trials, sample_pairs)
    prompt = _executive_summary_prompt(briefing)
    assert str(briefing["best_mrr"]) in prompt
    assert str(briefing["total_trials"]) in prompt


def test_discussion_prompt_includes_briefing_data(sample_trials, sample_pairs):
    """_discussion_prompt produces a prompt containing correlation and tier data."""
    from generate_evolution_report import _build_briefing, _discussion_prompt

    briefing = _build_briefing(sample_trials, sample_pairs)
    prompt = _discussion_prompt(briefing)
    # Should contain the JSON briefing
    assert "correlations" in prompt
    assert "tier_split" in prompt


def _mock_invoke_result(text):
    """Build a mock CompletedProcess mimicking claude CLI JSON output."""
    events = [
        {"type": "result", "result": text, "is_error": False},
    ]
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = json.dumps(events)
    proc.stderr = ""
    return proc


@patch("generate_evolution_report.invoke_claude")
def test_llm_prose_calls_invoke_claude_and_extracts_text(mock_invoke):
    """_llm_prose calls invoke_claude and returns the result text."""
    from generate_evolution_report import _llm_prose

    mock_invoke.return_value = _mock_invoke_result("This is the analysis.")
    result = _llm_prose({"key": "value"}, "Write analysis.", model="haiku")
    assert result == "This is the analysis."
    mock_invoke.assert_called_once()


@patch("generate_evolution_report.invoke_claude")
def test_section_executive_summary_with_llm(mock_invoke, sample_trials):
    """section_executive_summary calls LLM and includes the returned prose."""
    from generate_evolution_report import section_executive_summary

    mock_invoke.return_value = _mock_invoke_result("The experiment showed promising results.")
    md = section_executive_summary(sample_trials, model="haiku")
    assert "## 1. Executive Summary" in md
    assert "promising results" in md


def test_section_executive_summary_no_llm(sample_trials):
    """section_executive_summary with no_llm=True produces placeholder text."""
    from generate_evolution_report import section_executive_summary

    md = section_executive_summary(sample_trials, model="haiku", no_llm=True)
    assert "## 1. Executive Summary" in md
    assert "LLM" in md or "placeholder" in md.lower() or "skipped" in md.lower()


# ===========================================================================
# 5. Composition + CLI
# ===========================================================================

def test_generate_report_contains_all_sections(sample_trials, sample_pairs):
    """generate_report with no_llm=True includes all 9 numbered sections."""
    from generate_evolution_report import generate_report

    report = generate_report(sample_trials, sample_pairs, model="haiku", no_llm=True)
    assert "# Evolutionary Prompt Optimisation — Experiment Report" in report
    for i in range(1, 10):
        assert f"## {i}." in report, f"Missing section {i}"


def test_generate_report_edge_case_no_exploitation():
    """generate_report handles trials with no exploitation phase."""
    from generate_evolution_report import generate_report

    trials = [
        _make_trial("baseline", "baseline", 0.08),
        _make_trial("explore-alpha", "alpha", 0.10, survived=True),
    ]
    pairs = [{"source": "anger", "target": "fire", "tier": "strong"}]
    report = generate_report(trials, pairs, model="haiku", no_llm=True)
    assert "No exploitation" in report


def test_main_writes_output_file(tmp_path, sample_trials, sample_pairs):
    """main() writes the report to the specified output path."""
    from generate_evolution_report import main

    log_file = tmp_path / "log.json"
    log_file.write_text(json.dumps(sample_trials))

    pairs_file = tmp_path / "pairs.json"
    pairs_file.write_text(json.dumps(sample_pairs))

    output_file = tmp_path / "report.md"

    with patch("sys.argv", [
        "generate_evolution_report.py",
        "--experiment-log", str(log_file),
        "--pairs", str(pairs_file),
        "--output", str(output_file),
        "--no-llm",
    ]):
        main()

    assert output_file.exists()
    content = output_file.read_text()
    assert "# Evolutionary Prompt Optimisation" in content


# ===========================================================================
# 6. Backward compatibility — legacy logs without new fields
# ===========================================================================

def test_report_handles_legacy_trials():
    """Report generator handles trial dicts missing enrichment_coverage and valid."""
    from generate_evolution_report import generate_report

    legacy_trials = [
        {
            "trial_id": "baseline",
            "prompt_name": "baseline",
            "prompt_text": "B {batch_items}",
            "mrr": 0.08,
            "per_pair": [
                {"source": "anger", "target": "fire", "rank": 1,
                 "reciprocal_rank": 1.0, "tier": "strong"},
            ],
            "secondary": {
                "unique_properties": 100, "hapax_count": 60,
                "hapax_rate": 0.6, "avg_properties_per_synset": 11.0,
            },
            "parent_id": None,
            "generation": 0,
            "mutation": None,
            "survived": True,
            "timestamp": "2026-01-01T00:00:00",
            # NOTE: no enrichment_coverage, no valid
        },
        {
            "trial_id": "explore-alpha",
            "prompt_name": "alpha",
            "prompt_text": "A {batch_items}",
            "mrr": 0.10,
            "per_pair": [
                {"source": "anger", "target": "fire", "rank": 2,
                 "reciprocal_rank": 0.5, "tier": "strong"},
            ],
            "secondary": {
                "unique_properties": 120, "hapax_count": 70,
                "hapax_rate": 0.58, "avg_properties_per_synset": 12.0,
            },
            "parent_id": None,
            "generation": 0,
            "mutation": None,
            "survived": True,
            "timestamp": "2026-01-01T00:01:00",
        },
    ]
    pairs = [{"source": "anger", "target": "fire", "tier": "strong"}]

    # Should not crash
    report = generate_report(legacy_trials, pairs, model="haiku", no_llm=True)
    assert "# Evolutionary Prompt Optimisation" in report
    assert "baseline" in report
    assert "alpha" in report
