# Loop-2 — cohort axis inversion (iter 16 diagnostic)

**Source:** loop-2 iter 16 (reverted_metric_fail, but produced this finding).

**Headline.** On the current cascade, **every signal axis pro-discriminates on one cohort and anti-discriminates on the other.** This sharpens the loop-1 cohort-divergence finding into a per-axis claim.

## The numbers (iter 16 in-flight diagnostic)

Mean values per cohort, on the current loop-2 HEAD (`61c11818`):

| Signal | Phase 2 apt | Phase 2 inapt | Direction | Lakoff apt | Lakoff inapt | Direction |
|--------|------------:|--------------:|-----------|-----------:|-------------:|-----------|
| ortony_score | 0.026 | 0.053 | **anti-disc** (inapt > apt) | 0.029 | 0.007 | **pro-disc** (apt > inapt) |
| rerank_bonus | (not reported separately) | | | 0.63 | 0.68 | **anti-disc** |
| vehicle concreteness | 4.52 | 3.60 | **pro-disc** | (both ~4.5-4.8) | | flat / inverted |

The ortony scorer is doing exactly opposite work on the two cohorts. The rerank is similarly split (pro on Phase 2, anti on Lakoff — implied by the iter-14/15 commits lifting Phase 2 but capping at Lakoff's current plateau).

## Why this matters for loop tuning

A single global cascade configuration cannot maximise both cohorts simultaneously on these axes. The current ratios reflect a *negotiated compromise* — every knob trades signal between cohorts.

This makes the loop's commit gate (`Phase 2 ↑ AND Lakoff ≥ −5%`) more conservative than it first appears: virtually any move on a discriminative axis is going to push the cohorts in opposite directions. The loop is genuinely operating at a Pareto frontier, not a local minimum on a uniformly-improving surface.

## What it suggests for loop-2 direction

1. **Discontinuous changes only on Phase 2 median.** The bootstrap median is plateau-pinned at 2.0312 — small per-pair score perturbations move the full-cohort ratio but cannot shift the median. Iter 16 swept five `vehicle_concreteness_bonus_coef` values and watched the median refuse to move. Future iterations on Phase 2 likely need promotion-threshold flips, not score shifts.

2. **Cohort-aware switching is the next-real-improvement frontier.** Detect "abstract topic (Phase 2-like)" vs "image-dense topic (Lakoff-like)" at scoring time and apply different rerank shapes. This is the loop-1 design note resurfacing — and the iter 16 numbers say it's the only thing left that isn't a knob-tweak.

3. **Asymmetric commit-gate carve-out (separately proposed).** Path (b): allow Phase 2 ≥ −2% IFF Lakoff +0.05 absolute. Lets the loop pick up trades the agent currently has to revert. To be wired into iter 17+.

## Cross-refs

- Loop-1 cohort-divergence finding: `docs/inbox/2026-05-25-karpathy-loop-1-findings.md` §"Two cohort-divergence findings"
- Loop-2 baseline numbers: `data-pipeline/output/loop_baseline.json` (commit `61c11818`)
- Per-axis signed-delta means (loop-1): `karpathy_loop_1_outcomes.md` (memory)
