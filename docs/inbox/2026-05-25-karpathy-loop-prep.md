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
can fit in 15 minutes of *implementation* time is fair game:
calibration knobs, formula swaps, new pipeline stages, ANN library
integration, new tables, schema changes. Karpathy-style: agent
attempts, succeeds or fails, loop moves on.

**The 15-min wall clock excludes the eval harness run.** Harness time
is not the agent's work, and varies with cohort + cascade complexity;
counting it would penalise iterations that add legitimate new compute.
The driver records harness wall-clock separately for cost tracking.

**The eval harness itself is immutable per iteration.** No subagent
may modify the harness code (the end-to-end metric, bootstrap
resampling, commit-gate evaluation, or any file under the harness
module). If an iteration concludes that the harness has a flaw that
absolutely requires changing it, the subagent escalates to the
operator with a written justification — this **halts the loop** and
becomes an operator decision. Use the escape hatch only for genuine
urgency; the cost of a halt is high and the cost of an unfair eval
in one iteration is low (next iteration runs against a fresh codebase
anyway).

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
> 2. Implement on a fresh local branch from HEAD. The 15-min wall
>    clock covers steps 1 + 2 only; it stops when you invoke the
>    harness in step 3.
> 3. Run the eval harness on the Phase 2 cohort (with 10-bootstrap
>    resampling) AND on the Lakoff cohort. Harness run-time is NOT
>    counted against your 15-min budget.
> 4. Commit gate:
>      - Harness ran to completion → enter the metric gate below.
>      - Harness failed to run (crash, exception, infinite loop) →
>        revert, report, exit. No exceptions.
> 5. Metric gate (only reached if harness completed):
>      - Phase 2 median bootstrap ratio MUST improve vs current HEAD.
>      - Lakoff ratio MUST NOT degrade by more than 5% vs current HEAD.
>      - Both checks pass → commit, fast-forward main, report.
>      - Either fails → revert, report.
> 6. 15-min implementation timer expires before you reach step 3 →
>    revert whatever you have, report timed-out. No exception.
>
> Eval harness immutability:
>   - You MUST NOT modify any file in the harness module (the
>     end-to-end metric, bootstrap resampling, the commit-gate
>     evaluator). The exact file list is provided in the loop driver's
>     prompt at iteration spawn.
>   - If you believe a harness change is absolutely required, do NOT
>     edit it. Instead, report `OUTCOME=escalate_harness_flaw` with a
>     written justification. This halts the loop and surfaces to the
>     operator. Use this hatch only when the harness flaw genuinely
>     blocks all further work — its cost is high.
>
> Report on exit: hypothesis, change summary, Phase 2 ratio
> (before/after), Lakoff ratio (before/after), outcome
> (committed / reverted / timed-out / escalate_harness_flaw),
> implementation elapsed time, harness elapsed time (reported
> separately).

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

## Eval harness immutability — concrete file list

The harness module is defined as a fixed set of files committed before
the loop starts. The loop driver injects this list into every
iteration prompt. The subagent reads the list at spawn and treats
those files as read-only. Current planned scope::

    data-pipeline/scripts/evaluate_loop_harness.py   # main entry
    data-pipeline/scripts/evaluate_loop_metric.py    # end_to_end_ratio,
                                                     # bootstrap_e2e_ratio,
                                                     # commit gate evaluator
    data-pipeline/scripts/test_evaluate_loop_*.py    # harness tests

(Names provisional — finalised when the harness lands as Condition 1+2
infrastructure post-Phase-2.)

Subagents may add NEW metric functions alongside (in their own files)
and report them in their exit message, but the commit gate continues
to read only the immutable harness functions. Adding-alongside is a
useful pattern for proposing a future metric without changing the
current one.
>   - the commit-gate code
> All other files in the repo are fair game.
