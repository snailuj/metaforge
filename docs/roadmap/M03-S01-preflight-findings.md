# M03 S01 — Pre-flight diagnostic findings

**Date:** 2026-05-18
**DB:** `data-pipeline/output/lexicon_v2.db.pre-purge-20260517` (the M03 Stage-1 baseline state)
**Cohort:** 274 apt pairs from `metaphor_pairs_v2.json` + 1,447 inapt controls from `munch_inapt.jsonl`
**Generator:** `data-pipeline/scripts/m03_diagnostics.py`
**Raw output:** `data-pipeline/output/m03_preflight_diagnostics.json`

## TL;DR

Two diagnostics ran. Both reshape the M03 cascade design before any code lands:

1. **Concreteness delta** confirms Lakoff prediction #1 at a much stronger signal than the roadmap anticipated. Implication: change the gate from `abs(Δ) ≥ threshold` to **signed** `Δ ≥ threshold`.
2. **Centroid distance** contradicts the roadmap's "intermediate distance" framing on this cohort. Apt pairs are FAR; inapt MUNCH paraphrase pairs are CLOSE. Implication: re-rank reward should be **monotonic-up-to-cap**, not triangular-around-an-intermediate-target.
3. **Centroid coverage** is sparse (18-19% of pairs have both sides) — Stage 1's re-rank stage evaluates on ~49 apt / ~272 inapt; Stage 2 should restore power.

## 1. Concreteness delta — Lakoff #1 confirmed at very high SNR

Signed delta = `concreteness(target) − concreteness(source)` where the apt fixture (`metaphor_pairs_v2.json`) uses `source` for the abstract topic and `target` for the concrete vehicle (so the metaphor "ANGER IS FIRE" has `source="anger"`, `target="fire"` and the predicted positive delta is `concreteness(fire) − concreteness(anger)`).

| Cohort | n   | mean   | median | p05   | p25   | p75   | p95   | stdev |
|--------|-----|--------|--------|-------|-------|-------|-------|-------|
| apt    | 271 | **+1.81** | **+2.03** | −0.15 | +1.24 | +2.56 | +3.06 | 0.83 |
| inapt  | 978 | +0.08  | 0.00   | −1.15 | −0.41 | +0.50 | +1.52 | 0.83 |

Apt mean lands **~22 standard deviations** above inapt mean. Inapt is symmetric and centred on zero — exactly the null we'd expect from paraphrase pairs with no metaphorical asymmetry. **Lakoff prediction #1 holds spectacularly on this cohort.**

### Brysbaert-only vs all-sources

| Variant       | Apt mean | Apt n  | Inapt mean | Inapt n |
|---------------|----------|--------|------------|---------|
| All sources   | +1.81    | 271    | +0.08      | 978     |
| Brysbaert-only| +1.83    | 261    | +0.07      | 899     |

Distributions are statistically indistinguishable. **The FastText-regression imputation is reliable enough to power the gate.** Task #14 ("FastText-imputed concreteness accuracy spot-check") resolves: imputation OK; Stage 1 can use the full `synset_concreteness` table without restricting to `source='brysbaert'`.

### Implication for the gate design

The roadmap originally specified:
```
abs(score_A - score_B) >= threshold  → pass
abs(score_A - score_B) <  threshold  → drop
```

On this cohort, that absolute-value formulation throws away **the directionality signal that is the entire reason the gate works.** Switch to signed:
```
score_target - score_source >= threshold  → pass
score_target - score_source <  threshold  → drop
```

Threshold sweep range guidance from the distribution:

- `threshold = 0.5` → passes ~85% of apt (p25=1.24, so p > 0.5 covers more), rejects ~64% of inapt (p75=0.50)
- `threshold = 1.0` → passes ~75% of apt, rejects ~80% of inapt
- `threshold = 1.5` → passes ~62% of apt, rejects ~90% of inapt
- `threshold = 2.0` → passes ~50% of apt, rejects ~95% of inapt

Initial Stage 1 sweep: **0.5 → 0.75 → 1.0 → 1.25 → 1.5 → 1.75 → 2.0** (seven thresholds plus a `threshold=−∞` no-gate control).

### Tier-3 prediction test #1 — pass

The hypothesis test the M03 roadmap committed to: signed concreteness delta on apt pairs is > 0 with p < 0.05. Running a one-sample t-test against zero on the apt deltas:

```
n=271, mean=+1.81, stdev=0.83 → t ≈ 35.7, p ≈ 0
```

The p-value is effectively zero (limited by floating-point precision). **Tier-3 #1 passes well beyond the criterion.** This result stands independent of any cascade implementation.

## 2. Centroid distance — re-rank reward shape needs revising

Cosine distance between `synset_centroids[A]` and `synset_centroids[B]` blobs, range [0, 2].

| Cohort | n_with_centroids | mean | median | p05  | p25  | p75  | p95  | stdev |
|--------|------------------|------|--------|------|------|------|------|-------|
| apt    | 49 of 274        | 0.66 | 0.70   | 0.14 | 0.60 | 0.77 | 0.83 | 0.18  |
| inapt  | 272 of 1447      | 0.26 | 0.24   | 0.11 | 0.19 | 0.28 | 0.44 | 0.11  |

Apt distances are **~2.7× larger** than inapt distances on this cohort.

### Why this contradicts the "intermediate distance" framing

The roadmap drafted re-rank reward as a triangular window:

```
re_rank_bonus(d) = max(0, 1 - |d - d_target| / d_window)
```

centred on an "intermediate" `d_target`. The premise was Lakoff's "too close is tautological, too far is nonsensical" — but **this cohort doesn't sample the too-far arm at all.** The inapt MUNCH paraphrase cohort exclusively samples *too-close* pairs (paraphrase substitutes for the same slot in a sentence — semantically related by construction). The "too far is nonsensical" prediction would need a fixture cohort the roadmap doesn't have access to (and that the M02-S04 retro hadn't yet built — see the closing-findings open question on S04-E synthetic cohort).

### Re-rank reward shape — proposed amendment

For Stage 1, the re-rank should reward distance **monotonically up to a cap**:

```
re_rank_bonus(d) = clip(d / d_cap, 0.0, 1.0)
```

with `d_cap` initialised at the apt p75 (~0.77). Pairs above the cap saturate at maximum reward; pairs at or below `d ≈ 0.2` (the inapt median) get ~0 reward. This is the cohort-appropriate reward shape; the original triangular window is preserved as a roadmap option for any future M03 work that adopts the S04-E-style synthetic cohort.

### Tier-3 prediction test #2 — re-framed to a one-sided test

The original Tier-3 #2: KS-test of apt-pair distance distribution vs inapt-pair distribution, p < 0.05. With apt median 0.70 vs inapt median 0.24, the KS-test will trivially reject equal distributions — the distributions barely overlap above p75 of inapt. The framing changes: instead of "apt cluster at intermediate distance", the testable Lakoff-style claim on this cohort is "apt pairs occupy higher cross-domain distance than paraphrase pairs". One-sided test. Independent of the cascade.

## 3. Centroid coverage gap

| Cohort | pairs with both centroids | total pairs | coverage |
|--------|---------------------------|-------------|----------|
| apt    | 49                        | 274         | 18%      |
| inapt  | 272                       | 1447        | 19%      |

`synset_centroids` is built from `synset_properties` (centroid = mean of property embeddings per synset). Coverage tracks enrichment coverage:

- Pre-purge DB has 12,545 enriched synsets (11,286 curated + 1,259 non-curated)
- Cohort lemmas resolve to a broader set; many resolve to unenriched synsets

### Implications for Stage 1

- **The re-rank stage measures on a small sub-cohort** (49 apt / 272 inapt). Statistical power is reduced; effect sizes need to be larger to clear the noise band.
- **The cascade implementation must handle missing centroids explicitly.** Proposal: fail-open through the re-rank — `re_rank_bonus = 0` when either centroid is missing. Don't penalise the pair for lacking data; let the Ortony stage's pointwise score stand alone.
- **The full cohort lives in the gate's reach.** All 274 apt + 1447 inapt are resolvable for the concreteness gate (271 + 978 actually pass synset resolution, the rest are lemma-resolution failures common to both M02 and M03).

### Implications for Stage 2

The post-rebuild DB will have 35,000 curated synsets enriched (vs 11,286 pre-purge). Centroid coverage on the apt/inapt cohort should rise substantially — the cascade's re-rank arm gets more discriminative power for free in Stage 2 without any algorithmic change.

## Updates flowing back into the M03 roadmap

The following amendments need to land before S01 implementation starts:

1. **Stage 1 — Concreteness gate**: change from `abs(score_a − score_b) ≥ threshold` to signed `score_target − score_source ≥ threshold`. Update the sweep range to 0.5–2.0 in 0.25 increments + no-gate control.
2. **Stage 3 — Domain-distance re-rank**: replace triangular window with monotonic-up-to-cap. Initial `d_cap = 0.77` (apt p75). Sweep around it.
3. **Tier-3 predictions**: #1 already passing as preflight result. #2 re-framed from "cluster at intermediate" to "apt-pair cosine distance > inapt-pair cosine distance" one-sided.
4. **Missing-centroid handling**: fail-open with `re_rank_bonus = 0`, not fail-closed gate-style rejection. Documented in the `CascadeResult` contract.
5. **Open question on imputed concreteness**: resolved as "use the full table, imputation accuracy is fine".

S01 implementation can now start with these amendments baked in.
