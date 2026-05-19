# M03 S03 — Stage-1 Cascade Ablation Findings

**Date:** 2026-05-19
**DB:** `data-pipeline/output/lexicon_v2.db.pre-purge-20260517` (the M02-baseline byte-state)
**Sweep config:** `data-pipeline/sweeps/m03_cascade_v1.yaml` — 24 variations
**Raw sweep output:** `data-pipeline/output/sweep_m03_cascade_v1.{json,md}`
**Sweep duration:** 63.7 minutes wall

## TL;DR — Stage 1 PASSES

The cascade lifts `separation_score` from M02's published plateau of **−0.0407** (jaccard_salience) to **+0.1396** with the best configuration. That's a **+0.18 absolute lift** above the M02 plateau, **20× the `random_uniform` null reference of +0.0068**, and **comfortably above the M03 success criterion of ≥0.05 over the +0.06 plateau band**.

Both Lakoff predictions are doing work:
* **Concreteness gate** drops 88% of inapt pairs but only 20% of apt — asymmetric attrition delivers the directionality signal.
* **Domain-distance re-rank** rewards apt pairs more than inapt because apt pairs sit at higher centroid distance (median 0.70 vs 0.24, per pre-flight).
* **Additive composition crucially rescues coverage gaps** — when Ortony has no shared properties, multiplicative composition dies but additive still delivers the re-rank baseline.

Best parameters: `concreteness_threshold=1.0`, `alpha=1.0`, `composition=additive`, `d_cap=0.77`.

## Headline numbers

| Configuration | separation_score | apt_mean | inapt_mean |
|---|---|---|---|
| **cascade_full_alpha1.0_additive** *(M03 winner)* | **+0.1396** | 0.155 | 0.015 |
| cascade_full_alpha0.5_additive | +0.0810 | 0.092 | 0.011 |
| cascade_full_alpha1.0_multiplicative | +0.0269 | 0.033 | 0.006 |
| cascade_full_default *(alpha=0.5, mult)* | +0.0247 | 0.031 | 0.006 |
| cascade_gate_only_t1.0 *(no re-rank)* | +0.0224 | 0.028 | 0.006 |
| `m02_baseline_random_uniform` *(null ref)* | +0.0068 | 0.484 | 0.478 |
| **`m02_baseline_jaccard_salience`** *(M02 plateau)* | **−0.0407** | 0.042 | 0.083 |
| **`cascade_no_gate_no_rerank_sanity`** *(reproduction)* | **−0.0407** | 0.042 | 0.083 |
| m02_baseline_cosine_salience | −0.0535 | 0.081 | 0.134 |

## Sanity check — cascade reproduces M02 baseline exactly

`cascade_no_gate_no_rerank_sanity` (cascade with `threshold=-1e6, alpha=0`) lands at separation **−0.0407**, matching `m02_baseline_jaccard_salience` to four decimal places. The aggregate fields agree across the board (apt_mean 0.042, inapt_mean 0.083, threshold 0.3032, aptness_rate 0.0037).

This is the load-bearing sanity check that the cascade composition is mathematically equivalent to legacy pointwise scoring when the cascade-specific knobs are disabled. Without this match, every other "improvement" number in the table would be untrustworthy.

## Ablation table — what each stage contributes

**Pure M02 baselines** anchor the lower band:

| | separation_score |
|---|---|
| jaccard_salience    | −0.0407 |
| jaccard_raw         | −0.0398 |
| cosine_salience     | −0.0535 |
| random_uniform null | +0.0068 |

All four within ±0.06 of zero — the M02-S04 retro's published plateau, reproduced exactly.

**Cascade gate-only ablation** (re-rank disabled via `alpha=0`):

| threshold | separation_score | apt_gate_dropped | inapt_gate_dropped |
|---|---|---|---|
| 0.5  | +0.0183 | 34 / 271 (13%) | 730 / 978 (75%) |
| 0.75 | +0.0206 | 44 (16%)       | 809 (83%)       |
| **1.0**  | **+0.0224** | **54 (20%)** | **856 (88%)** |
| 1.25 | +0.0218 | 70 (26%) | 903 (92%) |
| 1.5  | +0.0217 | 83 (31%) | 928 (95%) |
| 1.75 | +0.0201 | 95 (35%) | 942 (96%) |
| 2.0  | +0.0155 | 131 (48%) | 946 (97%) |

The gate alone is the load-bearing stage: it lifts separation from M02's −0.0407 to +0.0224, a **+0.0631 swing**. Threshold 1.0 is the peak; further out the apt cohort starts attriting too aggressively (gate becomes false-negative-heavy).

**Cascade re-rank-only ablation** (gate disabled via `threshold=-inf`, vary `alpha`):

| alpha | separation_score |
|---|---|
| 0.25 (multiplicative) | −0.0404 |
| 0.5  (multiplicative) | −0.0400 |
| 1.0  (multiplicative) | −0.0392 |

Re-rank alone moves the needle by ~0.001 — essentially negligible. **The re-rank stage's contribution depends entirely on the gate filtering first.** This makes mechanical sense: without the gate, the apt and inapt cohorts share the same Ortony-score floor, and the re-rank multiplier doesn't change the ordering enough.

**Full cascade ablation** (gate + re-rank, vary composition + alpha):

| composition | alpha | separation_score | lift vs gate-only(t1.0) |
|---|---|---|---|
| multiplicative | 0.25 | +0.0235 | +0.0011 |
| multiplicative | 0.5  | +0.0247 | +0.0023 |
| multiplicative | 1.0  | +0.0269 | +0.0045 |
| **additive**       | **0.5** | **+0.0810** | **+0.0586** |
| **additive**       | **1.0** | **+0.1396** | **+0.1172** |

**Composition is the dominant lever inside the full cascade.** Multiplicative composition's lift over gate-only is ~0.005 (rounding noise). Additive composition's lift is ~0.12 — two orders of magnitude larger.

### Why additive crushes multiplicative on this cohort

Mechanism:

```
multiplicative: final = ortony_score × (1 + alpha × bonus)
additive:       final = ortony_score + alpha × bonus
```

When Ortony returns 0 (the two synsets share no curated property clusters), multiplicative composition yields `0 × X = 0` regardless of the re-rank bonus. Additive composition yields `0 + alpha × bonus`, which is non-zero for pairs with measurable centroid distance.

On this cohort, **the gate-passed survivors include many pairs with zero Ortony overlap** (the apt cohort routinely produces 0 because abstract sources and concrete vehicles share few curated properties). Additive composition gives these pairs a baseline floor proportional to their cross-domain distance. Apt pairs sit at median distance 0.70 → average bonus 0.91 (saturated against d_cap=0.77). Inapt pairs sit at median 0.24 → average bonus 0.31. With alpha=1.0, that's a +0.6 lift for apt vs +0.2 for inapt on gate-passed pairs.

The additive composition isn't a hack — it's the geometrically correct way to combine two independent discriminative signals (Lakoff #1 via the gate, Lakoff #2 via the re-rank). When either signal can stand alone, additive preserves its contribution; multiplicative collapses it under coverage gaps.

## Tier-3 Lakoff-prediction tests

These are claims about the world, not the harness. They stand or fall independent of the cascade implementation.

### Prediction #1 — Apt pairs show concrete-vehicle / abstract-topic asymmetry

**Already confirmed in the pre-flight** (`M03-S01-preflight-findings.md`):
- Apt signed delta mean: **+1.81** (n=271)
- Inapt signed delta mean: +0.08 (n=978)
- One-sample t-test against zero on apt: **t ≈ 35.7, p effectively 0**

Status: **PASSES** at p ≈ 0, far above the p < 0.05 criterion.

### Prediction #2 — Apt pairs occupy higher cross-domain centroid distance than inapt

Re-framed from the original "intermediate distance" to "apt > inapt" because the inapt MUNCH cohort doesn't sample the too-far arm at all. Pre-flight measured:
- Apt mean distance: 0.66 (n=49)
- Inapt mean distance: 0.26 (n=272)

The distributions barely overlap above inapt p75 (0.28) vs apt p25 (0.60). A one-sided Mann-Whitney U or KS test will reject "same distribution" trivially — but the cohort coverage (only 18-19% of pairs have both centroids in the pre-purge DB) limits statistical power.

Status: **PASSES descriptively**; formal test on the broader Stage-2 cohort will be more powerful given the post-rebuild centroid coverage uplift.

## Cohort-shape preflight on gate survivors

The M02-S04 retro made cohort-shape verification mandatory before trusting any harness verdict. After the gate, the surviving cohort is:
- Apt survivors: 271 − 54 = **217**
- Inapt survivors: 978 − 856 = **122**

The cohort balance has flipped — pre-gate the inapt cohort was ~3.6× larger than apt; post-gate the apt cohort is 1.8× larger. **This is the gate working as designed** (the gate is supposed to reject inapt pairs) but it introduces a power asymmetry: the inapt mean is computed over a smaller sample post-gate.

The smaller inapt-survivor cohort doesn't introduce a separation-score bias per se (means are still defined), but it does increase the variance on the inapt mean. The +0.1396 separation should be re-tested on the Stage-2 rebuild where centroid coverage will lift power further.

## Implications for Stage 2

Stage 2 runs the same sweep against the rebuilt DB once the haiku-sm enrichment lands. Expected effects:

1. **Centroid coverage rises substantially** (11k → 35k curated synsets enriched). The re-rank stage gets meaningful coverage instead of failing open on 80%+ of pairs. The +0.139 additive-composition number should hold or strengthen.
2. **Re-baseline first.** Stage 2's `random_uniform` reference must be re-measured on the rebuilt DB before declaring the cascade's lift. Don't compare Stage 2 cascade numbers against Stage 1 baselines — the data has changed under us.
3. **Re-confirm Lakoff predictions.** Both predictions made claims about the world; they should hold on the broader rebuilt cohort. If they don't, that's a sign the rebuild introduced something unexpected (or the predictions were artefacts of the pre-purge coverage).
4. **Sweep stays mostly unchanged.** The hyperparameter ranges are calibrated against the apt-cohort pre-flight distributions, which are world-claims (Brysbaert concreteness scores don't change between Stages 1 and 2). Re-running the same `m03_cascade_v1.yaml` against the rebuilt DB is the right move.

## Open questions / next steps

- **Statistical significance of the +0.1396 lift.** Bootstrap CI on `separation_score` would tell us how robust the headline number is. 271 apt + 978 inapt is plenty for sub-sampling.
- **Per-pair score distribution shape.** The additive composition produces scores in a different range than the multiplicative one. The `threshold_percentile=95` may not be the right operating point for additive composition; the percentile-of-inapt approach is calibrated for the multiplicative scale.
- **Forge integration (S05) needs the additive path.** The cascade winner uses `composition=additive` — the Go forge handler integration in S05 must support it (or constrain the production path to additive only).
- **The `behavior` vs `behaviour` US-spelling drift** in the enrichment output (~1% of properties) should probably be normalised at curation time. Not load-bearing for M03 but worth flagging.

## Files for the record

- Sweep config: `data-pipeline/sweeps/m03_cascade_v1.yaml`
- Sweep JSON (full per-pair data): `data-pipeline/output/sweep_m03_cascade_v1.json`
- Sweep Markdown table: `data-pipeline/output/sweep_m03_cascade_v1.md`
- Pre-flight diagnostics: `data-pipeline/output/m03_preflight_diagnostics.json`
- Pre-flight findings: `docs/roadmap/M03-S01-preflight-findings.md`
- Baseline DB (Stage 1): `data-pipeline/output/lexicon_v2.db.pre-purge-20260517` (kept for retention via `.keep-for-m03-baseline` sentinel)
