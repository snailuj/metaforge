"""Tests for the immutable loop metric module."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

from evaluate_loop_metric import (
    bootstrap_e2e_ratio,
    compare_metrics,
    end_to_end_ratio,
)


# ---------------------------------------------------------------------------
# end_to_end_ratio
# ---------------------------------------------------------------------------


def _row(topic, cohort, status="scored", score=0.5, vehicle="v"):
    return {
        "topic": topic, "vehicle": vehicle, "cohort": cohort,
        "status": status, "score": score,
    }


def test_e2e_promote_rate_uses_full_cohort_denominator():
    rows = [
        _row("t1", "apt", "scored", 0.9),
        _row("t1", "apt", "gate_dropped", None),
        _row("t1", "apt", "no_properties", None),
        _row("t2", "inapt", "scored", 0.1),
        _row("t2", "inapt", "gate_dropped", None),
    ]
    r = end_to_end_ratio(rows, threshold=0.5)
    assert r.n_apt_total == 3
    assert r.n_inapt_total == 2
    assert r.n_apt_promoted == 1
    assert r.n_inapt_promoted == 0


def test_e2e_zero_inapt_promotion_returns_inf():
    rows = [
        _row("t1", "apt", "scored", 0.9),
        _row("t2", "inapt", "scored", 0.1),
    ]
    r = end_to_end_ratio(rows, threshold=0.5)
    assert r.ratio == float("inf")


def test_e2e_zero_apt_and_zero_inapt_returns_zero():
    """0/0 -> 0.0 by convention so callers don't trip on NaN."""
    rows = [
        _row("t1", "apt", "scored", 0.1),
        _row("t2", "inapt", "scored", 0.1),
    ]
    r = end_to_end_ratio(rows, threshold=0.5)
    assert r.ratio == 0.0


def test_e2e_default_threshold_uses_median():
    rows = [
        _row("t1", "apt", "scored", 0.1),
        _row("t2", "apt", "scored", 0.9),
        _row("t3", "inapt", "scored", 0.5),
    ]
    r = end_to_end_ratio(rows)
    # median of [0.1, 0.5, 0.9] == 0.5
    assert r.threshold == 0.5


def test_e2e_empty_cohorts_safe():
    r = end_to_end_ratio([])
    assert r.n_apt_total == 0
    assert r.n_inapt_total == 0
    assert r.ratio == 0.0


def test_e2e_gate_dropped_counts_as_denominator_not_numerator():
    """The whole reason this metric exists: gate-dropped inapt vehicles
    should COUNT in the inapt denominator (since the system declined
    them) so a good gate shows up as a high ratio."""
    rows = [
        _row("t1", "apt", "scored", 0.9),
    ]
    # Add 9 gate-dropped inapt — none promoted, but they're all in the
    # denominator. Inapt rate = 0, apt rate = 1.0 → ratio = inf.
    rows += [_row(f"i{i}", "inapt", "gate_dropped", None) for i in range(9)]
    r = end_to_end_ratio(rows, threshold=0.5)
    assert r.n_inapt_total == 9
    assert r.inapt_promote_rate == 0.0
    assert r.ratio == float("inf")


# ---------------------------------------------------------------------------
# bootstrap_e2e_ratio
# ---------------------------------------------------------------------------


def _build_balanced_cohort(n_topics: int = 20):
    """Build a cohort where apt scores cluster high, inapt low — so
    every resample should yield a positive ratio."""
    rows = []
    for i in range(n_topics):
        rows.append(_row(f"t{i}", "apt", "scored", 0.7 + 0.01 * i))
        rows.append(_row(f"t{i}", "inapt", "scored", 0.2 + 0.01 * i))
    return rows


def test_bootstrap_resamples_at_topic_level():
    """All vehicles for a sampled topic must stay together."""
    rows = _build_balanced_cohort(20)
    r = bootstrap_e2e_ratio(rows, n_resamples=5, sample_fraction=0.5, seed=42)
    assert r.sample_size_topics == 10
    assert r.n_resamples == 5
    assert len(r.per_resample_ratio) == 5


def test_bootstrap_deterministic_with_seed():
    rows = _build_balanced_cohort(15)
    r1 = bootstrap_e2e_ratio(rows, n_resamples=8, seed=999)
    r2 = bootstrap_e2e_ratio(rows, n_resamples=8, seed=999)
    assert r1.per_resample_ratio == r2.per_resample_ratio


def test_bootstrap_p10_p90_bracket_median():
    rows = _build_balanced_cohort(30)
    r = bootstrap_e2e_ratio(rows, n_resamples=20, seed=7)
    assert r.p10_ratio <= r.median_ratio <= r.p90_ratio


def test_bootstrap_empty_cohort_safe():
    r = bootstrap_e2e_ratio([], n_resamples=5)
    assert r.median_ratio == 0.0
    assert r.per_resample_ratio == []


# ---------------------------------------------------------------------------
# compare_metrics commit gate
# ---------------------------------------------------------------------------


def _metrics(p2_med: float, lak: float) -> dict:
    return {
        "phase2": {"median_ratio": p2_med},
        "lakoff": {"ratio": lak},
    }


def test_gate_passes_when_p2_improves_and_lakoff_holds():
    v = compare_metrics(_metrics(2.0, 1.5), _metrics(2.5, 1.5))
    assert v.passed
    assert v.phase2_improved
    assert not v.lakoff_degraded


def test_gate_fails_when_p2_does_not_improve():
    v = compare_metrics(_metrics(2.0, 1.5), _metrics(2.0, 1.5))
    assert not v.passed
    assert not v.phase2_improved


def test_gate_fails_on_lakoff_degradation_beyond_tolerance():
    # 2.0 → 1.85 is a 7.5% drop, beyond the default 5% tolerance
    v = compare_metrics(_metrics(2.0, 2.0), _metrics(2.5, 1.85))
    assert not v.passed
    assert v.lakoff_degraded


def test_gate_passes_on_small_lakoff_drop_within_tolerance():
    # 2.0 → 1.92 is a 4% drop, within the default 5% tolerance
    v = compare_metrics(_metrics(2.0, 2.0), _metrics(2.5, 1.92))
    assert v.passed
    assert not v.lakoff_degraded


def test_gate_tolerates_zero_baseline_lakoff():
    """If baseline Lakoff is 0.0 we can't form a relative tolerance —
    any non-degenerate current value passes the Lakoff check."""
    v = compare_metrics(_metrics(0.5, 0.0), _metrics(1.0, 0.5))
    assert v.passed


def test_gate_reasons_describe_each_check():
    v = compare_metrics(_metrics(2.0, 2.0), _metrics(2.5, 1.95))
    assert any("phase2 median" in r for r in v.reasons)
    assert any("lakoff" in r.lower() for r in v.reasons)
    assert any("verdict" in r.lower() for r in v.reasons)
