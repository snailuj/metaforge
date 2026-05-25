"""Pure-function metrics for the Karpathy improvement loop.

This module is **immutable per loop iteration** — iteration subagents
MUST NOT modify it. The metric is the loop's truth signal; an agent
that changes the metric to fit its change is fitting the metric, not
the cascade.

Two metrics live here:

- ``end_to_end_ratio`` — fraction of apt vehicles a system promotes
  vs fraction of inapt vehicles it promotes. Denominator is the FULL
  cohort, including gate-dropped / unresolved / missing-concreteness /
  no-properties statuses. This is the fix for FU-1 (separation_score
  reports near-zero discrimination on a system with 2.5× end-to-end
  signal).

- ``bootstrap_e2e_ratio`` — resamples topics with replacement (N=10
  by default) and returns the median ratio across resamples plus
  uncertainty bands (p10 / p90). The median is the loop's commit-gate
  metric; the bands surface noise floor.

Plus the commit-gate evaluator ``compare_metrics`` which takes a
baseline + current result dict and emits a structured pass/fail
verdict.
"""
from __future__ import annotations

import random
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Sequence


# ---------------------------------------------------------------------------
# Per-vehicle row shape
# ---------------------------------------------------------------------------
# Every input vehicle is represented as a dict with at least these keys:
#   {
#     "topic":    "anger",
#     "vehicle":  "fire",
#     "cohort":   "apt" | "inapt",
#     "status":   "scored" | "gate_dropped" | "unresolved" |
#                 "missing_concreteness" | "no_properties",
#     "score":    float | None,   # None unless status == "scored"
#   }
# Extra keys (e.g. inapt_reason_type, synset ids) are tolerated and
# preserved through bootstrap resampling.


# ---------------------------------------------------------------------------
# End-to-end ratio
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class E2EResult:
    """Output of ``end_to_end_ratio``.

    ``ratio`` is infinity when ``inapt_promote_rate == 0`` (a system
    that promotes some apt but zero inapt). That's the theoretical
    maximum — we don't clamp it because the caller wants to see that
    the system is in 'perfect discrimination on this sample' state.
    """
    n_apt_total: int
    n_inapt_total: int
    n_apt_promoted: int
    n_inapt_promoted: int
    apt_promote_rate: float
    inapt_promote_rate: float
    ratio: float
    threshold: float


def end_to_end_ratio(
    rows: Sequence[dict],
    threshold: Optional[float] = None,
) -> E2EResult:
    """Compute the end-to-end discrimination ratio over the full cohort.

    A vehicle is "promoted" iff (status == "scored") AND
    (score > threshold). Gate-dropped, unresolved, missing-concreteness
    and no-properties rows all count as 'system declined to promote' —
    they belong in the denominator.

    If ``threshold`` is None, the median of the combined scored cohort
    is used. This is the loop's default — it's a stable per-cohort
    reference that doesn't require an external calibration step.

    Empty cohorts: a cohort with zero rows contributes 0.0 promote
    rate (no vehicles to promote). The ratio is then 0/0 → 0.0 by
    convention so callers don't have to special-case empties.
    """
    apt = [r for r in rows if r.get("cohort") == "apt"]
    inapt = [r for r in rows if r.get("cohort") == "inapt"]

    scored_scores = [
        r["score"] for r in rows
        if r.get("status") == "scored" and r.get("score") is not None
    ]
    if threshold is None:
        threshold = statistics.median(scored_scores) if scored_scores else 0.0

    def _promoted(group: Sequence[dict]) -> int:
        return sum(
            1 for r in group
            if r.get("status") == "scored"
            and r.get("score") is not None
            and r["score"] > threshold
        )

    n_apt = len(apt)
    n_inapt = len(inapt)
    n_apt_p = _promoted(apt)
    n_inapt_p = _promoted(inapt)
    apt_rate = n_apt_p / n_apt if n_apt else 0.0
    inapt_rate = n_inapt_p / n_inapt if n_inapt else 0.0

    if inapt_rate == 0.0:
        ratio = float("inf") if apt_rate > 0.0 else 0.0
    else:
        ratio = apt_rate / inapt_rate

    return E2EResult(
        n_apt_total=n_apt,
        n_inapt_total=n_inapt,
        n_apt_promoted=n_apt_p,
        n_inapt_promoted=n_inapt_p,
        apt_promote_rate=apt_rate,
        inapt_promote_rate=inapt_rate,
        ratio=ratio,
        threshold=threshold,
    )


# ---------------------------------------------------------------------------
# Bootstrap resampling
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BootstrapResult:
    """Output of ``bootstrap_e2e_ratio``.

    The median ratio is the loop's commit-gate signal. p10 / p90 give
    the noise floor — if the spread is wider than a typical iteration
    improvement, the loop is in noise and improvements should be
    treated with suspicion.

    ``per_resample_ratio`` is the full list so callers can inspect
    the distribution if needed.
    """
    median_ratio: float
    p10_ratio: float
    p90_ratio: float
    per_resample_ratio: list[float]
    n_resamples: int
    sample_size_topics: int


def _group_by_topic(rows: Sequence[dict]) -> dict[str, list[dict]]:
    """Index rows by topic so a topic's vehicles can move together."""
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        topic = r.get("topic")
        if topic is None:
            continue
        out[topic].append(r)
    return dict(out)


def _percentile(values: Sequence[float], pct: float) -> float:
    """Linear-interpolated percentile. Identical contract to
    evaluate_aptness._percentile but copied here so this module has
    no inbound dependencies on the rest of the codebase that an
    iteration subagent might mutate."""
    if not values:
        return 0.0
    if pct <= 0:
        return min(values)
    if pct >= 100:
        return max(values)
    s = sorted(values)
    rank = (pct / 100.0) * (len(s) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(s) - 1)
    frac = rank - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def bootstrap_e2e_ratio(
    rows: Sequence[dict],
    n_resamples: int = 10,
    sample_fraction: float = 0.8,
    seed: int = 20260525,
    threshold: Optional[float] = None,
) -> BootstrapResult:
    """Resample topics with replacement and report ratio distribution.

    Sampling unit is **topic** (not vehicle) — all vehicles for a
    sampled topic move together. This prevents within-topic vehicle
    correlation from leaking into the bootstrap variance.

    Sampling is with replacement (standard bootstrap) so the same
    topic can appear multiple times in one resample. The sample size
    is ``ceil(n_topics * sample_fraction)``.

    Threshold: if None, each resample computes its own median over
    the scored vehicles in that resample. This is the right default
    when comparing two systems on the same cohort — both compute
    their own threshold from the same data. Passing a fixed threshold
    is for diagnostic use only.

    Determinism: ``seed`` fully determines the resample partitions
    given the same row ordering. This matters for the loop — if the
    metric flickers across iterations because the resamples shift,
    we can't tell signal from noise.
    """
    by_topic = _group_by_topic(rows)
    topics = sorted(by_topic.keys())
    if not topics:
        return BootstrapResult(
            median_ratio=0.0, p10_ratio=0.0, p90_ratio=0.0,
            per_resample_ratio=[], n_resamples=n_resamples,
            sample_size_topics=0,
        )

    rng = random.Random(seed)
    n_sample = max(1, round(len(topics) * sample_fraction))

    ratios: list[float] = []
    for _ in range(n_resamples):
        picked = [rng.choice(topics) for _ in range(n_sample)]
        resample_rows: list[dict] = []
        for t in picked:
            resample_rows.extend(by_topic[t])
        r = end_to_end_ratio(resample_rows, threshold=threshold)
        # +inf ratios would distort percentile math — clamp to a large
        # finite sentinel. The 1000.0 cap is well above any realistic
        # ratio we'd see in practice (~5x at production), so it
        # documents 'this resample saw zero inapt promotion' without
        # poisoning downstream stats.
        ratios.append(min(r.ratio, 1000.0))

    return BootstrapResult(
        median_ratio=statistics.median(ratios),
        p10_ratio=_percentile(ratios, 10.0),
        p90_ratio=_percentile(ratios, 90.0),
        per_resample_ratio=ratios,
        n_resamples=n_resamples,
        sample_size_topics=n_sample,
    )


# ---------------------------------------------------------------------------
# Commit-gate evaluator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CommitGateVerdict:
    """Output of ``compare_metrics``.

    ``passed`` is the binary commit/revert signal. The reasons list
    captures every check that ran so the iteration subagent's report
    explains the outcome.
    """
    passed: bool
    phase2_baseline_median: float
    phase2_current_median: float
    phase2_improved: bool
    lakoff_baseline_ratio: float
    lakoff_current_ratio: float
    lakoff_degraded: bool
    reasons: list[str] = field(default_factory=list)


def compare_metrics(
    baseline: dict,
    current: dict,
    lakoff_degrade_tolerance: float = 0.05,
) -> CommitGateVerdict:
    """Apply the commit gate to a baseline / current metric pair.

    Expected dict shape (both args)::

        {
          "phase2": {"median_ratio": float, ...},  # from bootstrap_e2e_ratio
          "lakoff": {"ratio": float, ...},         # from end_to_end_ratio
        }

    Gate rules (both must pass):
      1. Phase 2 median bootstrap ratio MUST strictly improve.
      2. Lakoff ratio MUST NOT degrade by more than
         ``lakoff_degrade_tolerance`` (default 5%) relative to baseline.

    ``lakoff_degrade_tolerance`` is a *relative* tolerance — a 5% drop
    from 2.0 → 1.9 is allowed; 2.0 → 1.85 fails.
    """
    reasons: list[str] = []

    b_p2 = baseline["phase2"]["median_ratio"]
    c_p2 = current["phase2"]["median_ratio"]
    p2_improved = c_p2 > b_p2
    reasons.append(
        f"phase2 median: {b_p2:.4f} -> {c_p2:.4f} "
        f"({'IMPROVED' if p2_improved else 'NOT improved'})"
    )

    b_lak = baseline["lakoff"]["ratio"]
    c_lak = current["lakoff"]["ratio"]
    # Tolerance applied multiplicatively from the baseline. If baseline
    # is 0.0 we can't form a ratio, so any current >= 0 passes.
    if b_lak == 0.0:
        lak_degraded = False
    else:
        relative_change = (c_lak - b_lak) / b_lak
        lak_degraded = relative_change < -lakoff_degrade_tolerance
    reasons.append(
        f"lakoff ratio: {b_lak:.4f} -> {c_lak:.4f} "
        f"({'OK' if not lak_degraded else 'DEGRADED beyond tolerance'})"
    )

    passed = p2_improved and not lak_degraded
    reasons.append(f"verdict: {'COMMIT' if passed else 'REVERT'}")

    return CommitGateVerdict(
        passed=passed,
        phase2_baseline_median=b_p2,
        phase2_current_median=c_p2,
        phase2_improved=p2_improved,
        lakoff_baseline_ratio=b_lak,
        lakoff_current_ratio=c_lak,
        lakoff_degraded=lak_degraded,
        reasons=reasons,
    )
