# Karpathy Loop — Pre-flight Prep

Drafted while Phase 2 runs. Once Phase 2 finishes, two pieces of
infrastructure must land before the first iteration. This doc captures
the design.

Cross-ref: `docs/inbox/2026-05-25-metaphor-spike-findings.md` (FU-1
metric correction).

## Philosophy

Each iteration is a **fresh subagent** with no handover from the
previous one. Identical prompt every time. The subagent reads the
codebase as-is, hypothesises an improvement, implements it, runs the
eval, and commits or reverts. No narrative threads. No ranked lever
list. The codebase itself is the only state.

The timer is the only scope constraint. Anything an iteration agent
can fit in 15 minutes is fair game: calibration knobs, formula swaps,
new pipeline stages, ANN library integration, new tables, schema
changes. Karpathy-style: agent attempts, succeeds or fails, loop
moves on.

## The loop

```
while operator_allows:
    spawn iteration subagent with the standard prompt:
        - codebase HEAD as it currently is
        - paths to: Phase 2 cohort JSONL, Lakoff cohort, eval harness
        - 15-min hard wall clock
        - commit-or-revert rule (below)
    record outcome (committed / reverted / timed-out)
```

The loop driver does not feed prior attempts into the next iteration.
The subagent can `git log` recent commits if it wants signal on what's
been tried, but the prompt doesn't hand it any.

Termination: operator stops. No automatic halt on consecutive failures
— the user-corrected version is explicitly "go until told to stop".

## Iteration subagent contract

Prompt skeleton (verbatim every iteration):

> You are one iteration of an open-ended cascade-improvement loop.
>
> Repository: <path>. Eval harness: <command>. Phase 2 cohort:
> <path>. Lakoff cohort: <path>.
>
> Your job: identify a modest improvement to the cascade or its
> supporting pipeline that you can implement, test, and evaluate in
> ≤ 15 minutes. Anything is fair game — config knobs, scoring
> formulas, new stages, new tables, library swaps. The only
> constraint is the timer.
>
> Workflow:
> 1. Read the codebase enough to form a hypothesis.
> 2. Implement on a fresh local branch from HEAD.
> 3. Run the eval harness (see below) on the Phase 2 cohort with
>    10-bootstrap resampling, and also on the Lakoff cohort.
> 4. Commit gate (see below). If pass, fast-forward main and report.
>    If fail, revert and report.
>
> Commit gate:
>   - Phase 2 median bootstrap ratio MUST improve vs current HEAD.
>   - Lakoff ratio MUST NOT degrade by more than 5% vs current HEAD.
>   - Both checks pass → commit. Either fails → revert.
>   - Timer expires → revert whatever you have, no exception.
>
> Report on exit: hypothesis, change summary, Phase 2 ratio
> (before/after), Lakoff ratio (before/after), outcome
> (committed / reverted / timed-out), elapsed time.

The agent has no list of "things to try" and no memory of prior
iterations. Selection is entirely up to its read of the codebase.

## Condition 1: FU-1 end-to-end metric

**What.** Replace separation_score (scored-pair mean delta) with the
end-to-end discrimination ratio as the loop's truth-metric.

**Why.** Phase 1b showed separation_score = +0.0061 against a system
with 2.5× end-to-end discrimination. Modest cascade tweaks move
separation_score by ≤0.005 — below noise floor.

**Where.** New function in `evaluate_aptness.py` (or a new
`evaluate_e2e.py` module if separation is preferred)::

    def end_to_end_ratio(apt_scored, inapt_scored, threshold) -> dict:
        """
        apt_promote   = (n_apt_above_threshold) / n_apt_total
        inapt_promote = (n_inapt_above_threshold) / n_inapt_total
        ratio         = apt_promote / inapt_promote
        """

Denominator is the FULL cohort. Gate-dropped + missing-concreteness +
no-properties + unresolved all count as 'not promoted'.

**Effort.** ~30 lines + 3 unit tests. ~30 min.

## Condition 2: Bootstrap-resampling harness

**What.** Instead of a fixed train/val split, each iteration scores
the cohort across N=10 bootstrap resamples (each ~80% of topics,
sampled with replacement at topic level). The loop's truth signal
is the **median ratio across resamples**, not a single number.

**Why.** A fixed val set becomes a second training set under repeated
checking. Bootstrap mutates the partition every iteration — no fixed
subset can accumulate overfit. Plus the resample spread gives us
free uncertainty bands; if the 10th-percentile ratio is below 1.0
while the median is 2.0, the metric is unstable and the agent should
treat improvements with suspicion.

**Where.** New harness function::

    def bootstrap_e2e_ratio(
        apt_scored, inapt_scored, threshold,
        n_resamples: int = 10, seed: int = 20260525,
    ) -> dict:
        """
        Returns:
            median_ratio: float
            p10_ratio:    float   # 10th percentile across resamples
            p90_ratio:    float   # 90th percentile
            per_resample: list[float]
        Each resample picks 80% of topics with replacement. All vehicles
        for a sampled topic move together so within-topic correlation
        doesn't leak.
        """

Topics (not vehicles) are the resampling unit so within-topic vehicle
correlation doesn't bias the spread.

**Effort.** ~40 lines + 2 tests. ~30 min.

## Condition 2b: Parallel Lakoff signal

**What.** Every iteration ALSO scores the original M01 Lakoff cohort
end-to-end (no bootstrap — Lakoff is small enough to score
deterministically). Report alongside Phase 2.

**Why.** Phase 2's cohort encodes Haiku-via-Sonnet biases. Lakoff is
an independent hand-curated cohort with different biases. A tweak
that lifts Phase 2 but drops Lakoff is fitting LLM artefacts, not
improving the cascade. Different from a single held-out: Lakoff is
known-different, not random-different.

**Commit gate uses both.** Phase 2 median ratio must improve;
Lakoff ratio must not drop by >5%. Both checks bind.

**Effort.** ~10 lines (Lakoff harness already exists in
evaluate_aptness.py — just wire it into the iteration's eval call).

## Bail criterion

If Phase 2 end-to-end ratio < 1.5× at the post-Phase-2 baseline, the
cascade is too noisy for the loop to converge. In that case, do FU-2
lemmatisation first (one-shot, outside the loop) and recompute the
baseline before starting iterations. Log the decision in the findings
doc either way.

## Open question

Whether the iteration subagent should be allowed to MODIFY the eval
harness itself. Strict reading: no — that lets the agent change the
metric to fit its change. Permissive reading: yes — sometimes a better
metric IS the improvement. Resolution: prohibit modifying the
end-to-end ratio definition or the commit gate; allow modifying
anything else (including adding NEW metrics alongside, for the report).

Pre-commit this as a fixed file list in the prompt:

> The following files are off-limits in this iteration:
>   - definition of `end_to_end_ratio` and `bootstrap_e2e_ratio`
>   - the commit-gate code
> All other files in the repo are fair game.
