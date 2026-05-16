# M02-S04-B — Union-size distribution check

**DB:** `data-pipeline/output/lexicon_v2.db`  
**Apt resolved:** 232 pairs  
**Inapt resolved:** 317 pairs  

Sizes are in **distinct curated cluster_ids**.

## Apt cohort (source = topic, target = vehicle)

| metric | n | min | p25 | median | p75 | p95 |
|---|---|---|---|---|---|---|
| |pa| (topic side) | 232 | 1 | 8 | 10 | 11 | 15 |
| |pb| (vehicle side) | 232 | 1 | 9 | 10 | 12 | 16 |
| |pa ∩ pb| | 232 | 0 | 0 | 0 | 1 | 2 |
| |pa ∪ pb| | 232 | 7 | 18 | 19 | 22 | 28 |

## Inapt cohort (target side, paraphrase side)

| metric | n | min | p25 | median | p75 | p95 |
|---|---|---|---|---|---|---|
| |pa| (target side) | 317 | 1 | 12 | 15 | 17 | 20 |
| |pb| (paraphrase side) | 317 | 1 | 11 | 13 | 16 | 20 |
| |pa ∩ pb| | 317 | 0 | 0 | 0 | 1 | 4 |
| |pa ∪ pb| | 317 | 2 | 22 | 27 | 30 | 34 |

## Cross-cohort delta

Flag triggers at |Δ%| > 30 on either median or p95 — that's the rough threshold where cohort-shape mismatch starts driving the random_uniform null off zero noticeably given the ~270-pair cohort size noise floor.

| metric | apt median | inapt median | median Δ% | apt p95 | inapt p95 | p95 Δ% | flag |
|---|---|---|---|---|---|---|---|
| |pa| | 10 | 15 | -33.3% | 15 | 20 | -22.8% | ⚠️ |
| |pb| | 10 | 13 | -23.1% | 16 | 20 | -20.0% | ✓ |
| |pa ∩ pb| | 0 | 0 | +0.0% | 2 | 4 | -38.8% | ⚠️ |
| |pa ∪ pb| | 19 | 27 | -29.6% | 28 | 34 | -17.6% | ✓ |

## Verdict

🟡 **Borderline.** Median |pa ∪ pb| differs by -29.6% between cohorts — meaningful but not overwhelming. The null-drift is partially explained by cohort shape; some residual algorithm signal may survive.

## Why this matters

From `evaluate_aptness._random_uniform` docstring: *"the cohort-level expected separation_score is unbiased ONLY when the apt and inapt cohorts share similar union-size distributions; if apt unions are systematically larger or smaller than inapt unions the null reference becomes biased."*

The v1/v2/v3 sweeps showed random_uniform separation = −0.0164. Combined with this audit, that drift is now mechanically explained (or refuted) by the union-size distribution comparison above.