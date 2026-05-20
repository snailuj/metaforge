# M02-S04-C — Threshold-percentile sensitivity sweep — design

**Status:** config staged ([`m02_s04_threshold_sensitivity.yaml`](m02_s04_threshold_sensitivity.yaml)), **not yet run**.

## Why this sweep exists

Every M02 sweep so far (v1, v2, v3) has fixed `threshold_percentile = 95`. The p95 of the inapt cohort (n≈317) lands on the 16th-highest inapt score — a thin slice whose value is sensitive to a handful of outlier inapt pairs. The verdict "ortony_imbalance is the only variant whose separation_score flipped positive" rests entirely on this single threshold choice. If the verdict reverses (or strengthens) at p90 or p99, our v1/v2/v3 reasoning is fragile.

The sensitivity slice that landed alongside M01 — Automated Eval Harness ([`SENSITIVITY-V2-FINDINGS.md`](SENSITIVITY-V2-FINDINGS.md)) — exercised `threshold_percentile` at 50/95/99 for `jaccard_salience` only. It established that aptness_rate is monotonic in `threshold_percentile` (good — confirms the threshold isn't broken), but didn't sweep this across the 6 scoring formulas that exist now.

S04-C fills that gap.

## Design

- **7 scoring fns × 5 threshold percentiles = 35 variations.**
  - Scoring fns: `jaccard_salience`, `jaccard_raw`, `cosine_salience`, `ortony_vehicle_salience`, `ortony_imbalance`, `ortony_log_ratio`, `random_uniform`.
  - Threshold percentiles: 50, 75, 90, 95, 99.
- Same cohort, same DB, same MRR reference as v1/v2/v3 — only the threshold percentile varies within each scoring formula's row.

## What the sweep should tell us

Three diagnostic questions, in order of importance.

### Q1 — Is the v2 sweep winner (ortony_imbalance, +0.0010 at p95) stable across thresholds?

If `ortony_imbalance` produces positive separation_scores at multiple thresholds (p90, p95, p99) and stays above the null reference (`random_uniform`) at all of them, the v2 verdict survives sensitivity analysis. If it only beats null at p95, the v2 verdict is an artefact and the variant is not actually superior.

### Q2 — Does any non-winning scoring fn become the winner at a different threshold?

The v1/v2/v3 sweeps tested only p95. It's possible (though unlikely given the M01 sensitivity findings) that, say, `cosine_salience` produces a positive separation_score at p75 even though it was last-place at p95. If so, the ranking we have established is threshold-dependent rather than algorithm-dependent — different finding entirely.

### Q3 — Does the random_uniform null drift (−0.0164 at p95) close at lower percentiles?

The S04-B audit showed apt unions are ~30% smaller than inapt unions, which biases random_uniform negative at p95 (apt scores tend to land below the threshold computed from a wider-union inapt distribution). At p50 the threshold is the median rather than the tail — should be less sensitive to union-size mismatch. If random_uniform stays near zero at p50 and only drifts away from zero at p95+, that's direct quantitative confirmation of the union-shape mechanism. If it drifts negative at every percentile, the mechanism is something else (e.g. systematic cluster_id frequency differences).

## What to write up after running

A new doc `data-pipeline/sweeps/M02-S04-C-threshold-sensitivity-findings.md`, structured around Q1/Q2/Q3 above. The 35-variation report is already produced by `run_sweep.py --report`; the findings doc just needs the verdicts and any commentary.

## Pre-flight — do NOT run yet

S04-A and S04-B established that the current resolved cohort is biased (apt drops 25.9pp by domain; apt unions are 30% smaller than inapt unions). Running C on the *current* cohort tells us how the threshold interacts with that biased cohort — useful, but secondary to fixing the cohort itself. Running C *after* enrichment scope expands (the in-flight 8k top-up) and any cohort-attrition remedies have landed will give a much more interpretable result.

The config is staged so the run is one command when we're ready.
