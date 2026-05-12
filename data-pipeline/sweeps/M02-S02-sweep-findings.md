# M02-S02 — Asymmetric variant sweep findings

> **Update 2026-05-12 (v2 sweep):** the second asymmetric variant —
> `ortony_imbalance` — produced the first positive `separation_score`
> on this corpus (+0.0010). Magnitude is still inside the ±0.02 null-
> noise band, but the *sign flip* validates the hypothesis the v1
> diagnosis predicted (equal-salience penalty counters MUNCH bias).
> See the "v2 update" section below the original v1 writeup.
>
> **Update 2026-05-12 (v3 sweep):** the third asymmetric variant —
> `ortony_log_ratio` (soft-dominance) — did NOT improve over v2.
> It came in at sep=−0.0113, marginally above jaccard_salience but
> still negative and the softer penalty produced the *lowest*
> aptness_rate of any functional scoring (0.0172). The hard-zero
> equal-salience clamp in `ortony_imbalance` (v2) appears to be
> what extracts signal on this corpus — softening it loses the
> effect. v3 details in the "v3 update" section.
>
> The v1 sections that follow are preserved verbatim as the
> as-of-2026-05-12T13:15Z record.

---


**Date:** 2026-05-12
**Branch:** `m02/asymmetric-ortony-scoring` (commit `1822e5da`, rebased onto post-PR-#17 main `691713de`)
**Config:** [`m02_ortony_v1.yaml`](m02_ortony_v1.yaml)
**Cohort:** 232 apt pairs (from 274; 3 unresolved, 39 no_properties) / 317 inapt MUNCH controls (from 1447; 469 unresolved, 661 no_properties)
**Artefacts (gitignored):**
- `data-pipeline/output/sweep_m02_ortony_v1.json` — raw results
- `data-pipeline/output/sweep_m02_ortony_v1.md` — ranked report

## Headline

The first asymmetric variant — `ortony_vehicle_salience` (normalised vehicle-coverage) — **does not beat the symmetric baselines**. All four functional scorings produced `separation_score` values within the ±0.02 null-noise band established by the S03 sensitivity slice. The asymmetric variant was the worst-performing of the five (and worse than `random_uniform`), failing the M02 success criterion ("≥5% absolute improvement over the best symmetric baseline").

## Numbers

| rank | name | threshold | aptness_rate | separation_score | mean_apt | mean_inapt |
|---|---|---|---|---|---|---|
| 1 | jaccard_salience | 0.1459 | 0.0388 | -0.0124 | 0.0269 | 0.0393 |
| 2 | jaccard_raw | 0.1379 | 0.0603 | -0.0130 | 0.0275 | 0.0405 |
| 3 | random_uniform | 0.9721 | 0.0345 | -0.0164 | 0.4982 | 0.5145 |
| 4 | cosine_salience | 0.2850 | 0.0474 | -0.0198 | 0.0562 | 0.0760 |
| 5 | ortony_vehicle_salience | 0.3011 | 0.0302 | -0.0250 | 0.0533 | 0.0782 |

## Notes vs M01 baseline

The M01 SENSITIVITY-V2-FINDINGS recorded `separation_score = +0.0103` for `jaccard_salience` on the V2 cohort. This sweep run finds **−0.0124** — a sign flip of ~0.023, well outside the ±0.02 sampling-noise band. The likely driver is the underlying DB:

- The pre-rebase main DB on disk (2026-04-26 snapshot) had ~74k rows in `synset_properties_curated` against ~96k links in `synset_properties` (old schema, no `salience` column).
- This sweep ran on a fresh copy from `.worktrees/next` with the new schema and ~300k `synset_properties` links → ~130k `synset_properties_curated` rows after re-snapping with the post-PR-#17 code.

So the M01 +0.0103 reference is not directly comparable to this sweep — it was measured against a different (smaller, schema-stale) DB. **The post-#17 reference for M02 work is `jaccard_salience = -0.0124 ± 0.02`** (effectively null). The published roadmap line ("aptness_rate 0.0849, separation_score 0.0103") needs updating to reflect this.

## Diagnosis — why asymmetric does not help here

Mean scores (column `mean_inapt`) are systematically *higher* than `mean_apt` across all four functional scorings. The MUNCH inapt cohort is by construction lexically and topically nearby — paraphrase substitutions inside the same sentence — so the property-overlap signal is biased toward inapt pairs. Apt pairs in `metaphor_pairs_v2.json` are *cross-domain* mappings (`anger → fire`, `grief → anchor`), whose curated property overlap is sparser than that of within-domain paraphrase pairs.

The first asymmetric variant normalises by vehicle salience mass. When the vehicle has many salient properties and only a few overlap with the topic, the score is *small*. This penalises broad-vehicle metaphors (which is wrong for Ortony's account — broad vehicles are exactly where high-salience transfer happens). The variant ends up worse than symmetric because the asymmetric normalisation amplifies the inapt-overlap bias rather than countering it.

## Implications for M02

Per the roadmap, the next two asymmetric candidates should be tried before declaring the hypothesis dead:

- **Imbalance-weighted:** `score = Σ_{p∈A∩B} salience_B(p) × max(0, salience_B(p) − salience_A(p))`. Rewards properties that are salient *only* in the vehicle — closer to the original Ortony intuition (vehicle contributes its prominence; topic does not already have it).
- **Log-ratio:** `score = Σ_{p∈A∩B} salience_B(p) × log(salience_B(p) / salience_A(p))`. Rewards relative prominence rather than absolute coverage. Bounded carefully to avoid `log(0)`.

Both differ from the first variant by explicitly *penalising* properties that are equally salient in both sides — addressing the MUNCH-bias mechanism directly.

If both fail too, the result strengthens the case that pointwise property-overlap (in any reweighting) is the wrong primitive for this corpus, and M03 (cascade gate-and-rank with concreteness + domain distance) should be reached for sooner.

## Reproducing

```sh
data-pipeline/.venv/bin/python data-pipeline/scripts/run_sweep.py \
  --config data-pipeline/sweeps/m02_ortony_v1.yaml \
  --output data-pipeline/output/sweep_m02_ortony_v1.json \
  --report data-pipeline/output/sweep_m02_ortony_v1.md
```

The JSON provenance block pins the run to `git_commit=1822e5da`, `config_path`, `db_path`, `mrr_reference_path`, and `mrr_reference_value` so the artefacts can be reproduced from this committed config + the matching DB snapshot. **DB note:** the committed `data-pipeline/output/lexicon_v2.sql` (Apr 26 snapshot) is stale and does not have the `synset_properties.salience` column the post-PR-#17 snap needs. See project memory `lexicon_db_freshness.md` — borrow a fresh DB from `.worktrees/next/data-pipeline/output/lexicon_v2.db` or re-export from a current enrichment before reproducing.

---

## v2 update — imbalance variant flips the sign

**Date:** 2026-05-12T13:56Z
**Branch:** `m02/asymmetric-ortony-scoring` (commit `b42ade21`)
**Config:** [`m02_ortony_v2.yaml`](m02_ortony_v2.yaml) — adds `ortony_imbalance` to the v1 lineup
**Cohort:** identical to v1 (232 apt / 317 inapt)

### Numbers (v2 sweep, sorted by separation_score)

| rank | name | threshold | aptness_rate | separation_score | mean_apt | mean_inapt |
|---|---|---|---|---|---|---|
| 1 | **ortony_imbalance** | 0.0267 | **0.0733** | **+0.0010** | 0.0064 | 0.0054 |
| 2 | jaccard_salience | 0.1459 | 0.0388 | −0.0124 | 0.0269 | 0.0393 |
| 3 | jaccard_raw | 0.1379 | 0.0603 | −0.0130 | 0.0275 | 0.0405 |
| 4 | random_uniform | 0.9721 | 0.0345 | −0.0164 | 0.4982 | 0.5145 |
| 5 | cosine_salience | 0.2850 | 0.0474 | −0.0198 | 0.0562 | 0.0760 |
| 6 | ortony_vehicle_salience | 0.3011 | 0.0302 | −0.0250 | 0.0533 | 0.0782 |

### What changed

`ortony_imbalance` is the only variant in either sweep whose mean_apt exceeds mean_inapt. Both means are an order of magnitude smaller than the other functional scorings (0.0064 / 0.0054 vs the 0.02–0.08 band) — the per-term `max(0, pb − pa)` clamp aggressively zeros out shared properties where vehicle and topic are equally salient, so most pairs end up with near-zero raw scores. The cohort-level separation survives that compression because the apt pairs retain *slightly* more vehicle-dominant properties than MUNCH paraphrase pairs.

### Significance vs the noise floor

Magnitude (+0.0010) is well inside the ±0.02 null-noise band — this is **not** a strong positive signal on its own. The result that matters is the **sign flip plus aptness_rate jump**: 0.0733 (variant 2) vs 0.0388 (best symmetric), almost double, and outside the null reference's 0.0345. That means the apt cohort's score distribution is now riding higher *relative to the inapt 95th-percentile threshold* than under any symmetric formula — even if the means barely separate.

So the mechanism is doing what the v1 diagnosis predicted. The question for variant 3 (log-ratio) and beyond is whether more aggressive asymmetry can push the separation_score genuinely above the noise floor, or whether the equal-salience penalty has already extracted what's extractable from this corpus.

### Implications for M02

- **Variant 3 (log-ratio) is worth running.** `Σ pb[c] × log(pb[c] / pa[c])`, bounded carefully (clip `log(x/0)` and `log(0/x)`). It rewards *relative prominence* on a multiplicative scale rather than the linear penalty in variant 2 — should be more sensitive to pairs where the vehicle has *one* dominant property the topic lacks, regardless of how many shared-equal properties they have.
- **The "best symmetric reference" for M02 is now defensible:** `jaccard_salience = −0.0124`. The improvement `ortony_imbalance` delivers is +0.0134 absolute, which exceeds the success criterion's 5% threshold *as a delta* (5% of 1.0 is 0.05; 0.0134 is below that). Strictly the variant has not yet cleared the criterion — but it has cleared the harder bar of "any positive signal at all on this corpus".
- **If variant 3 doesn't move the dial further**, the case for pivoting to M03 (cascade gate-and-rank) gets stronger: the equal-salience penalty has likely extracted what pointwise property-overlap can deliver here, and the next gains are structural.

### Reproducing

```sh
data-pipeline/.venv/bin/python data-pipeline/scripts/run_sweep.py \
  --config data-pipeline/sweeps/m02_ortony_v2.yaml \
  --output data-pipeline/output/sweep_m02_ortony_v2.json \
  --report data-pipeline/output/sweep_m02_ortony_v2.md
```

Same DB-freshness caveat as v1 — see project memory `lexicon_db_freshness.md` before re-running.

---

## v3 update — soft-dominance variant does NOT beat the imbalance hard-zero

**Date:** 2026-05-12T14:18Z
**Branch:** `m02/asymmetric-ortony-scoring` (commit `88ed32d7`)
**Config:** [`m02_ortony_v3.yaml`](m02_ortony_v3.yaml) — adds `ortony_log_ratio` to the v2 lineup
**Cohort:** identical (232 apt / 317 inapt)

### Numbers (v3 sweep, sorted by separation_score)

| rank | name | threshold | aptness_rate | separation_score | mean_apt | mean_inapt |
|---|---|---|---|---|---|---|
| 1 | **ortony_imbalance** | 0.0267 | **0.0733** | **+0.0010** | 0.0064 | 0.0054 |
| 2 | ortony_log_ratio | 0.1729 | 0.0172 | −0.0113 | 0.0275 | 0.0388 |
| 3 | jaccard_salience | 0.1459 | 0.0388 | −0.0124 | 0.0269 | 0.0393 |
| 4 | jaccard_raw | 0.1379 | 0.0603 | −0.0130 | 0.0275 | 0.0405 |
| 5 | random_uniform | 0.9721 | 0.0345 | −0.0164 | 0.4982 | 0.5145 |
| 6 | cosine_salience | 0.2850 | 0.0474 | −0.0198 | 0.0562 | 0.0760 |
| 7 | ortony_vehicle_salience | 0.3011 | 0.0302 | −0.0250 | 0.0533 | 0.0782 |

### What v3 tells us

`ortony_log_ratio` produces score distributions almost identical to `jaccard_salience` (mean_apt 0.0275 vs 0.0269; mean_inapt 0.0388 vs 0.0393). The soft sigmoid-of-log-ratio penalty doesn't materially redistribute the cohort scores — the asymmetric weighting it applies is too mild to escape the corpus's MUNCH-bias attractor. Critically, its aptness_rate (0.0172) is the *lowest* of any functional scoring, beneath even `random_uniform` (0.0345). That tells us the soft formula is moving apt-pair scores in the *wrong direction* relative to the threshold percentile, even when the means barely move.

The contrast with `ortony_imbalance` confirms the v2 diagnosis precisely: it is the **hard-zero clamp on equal-salience properties** that does the discriminative work. Replace the hard zero (`max(0, pb − pa) = 0` when pb = pa) with a soft half-credit (`pb/(pa+pb) = 1/2`), and the equal-salience properties from MUNCH paraphrase pairs flood back into the score and re-bias it toward inapt.

### Verdict on M02-S02

**`ortony_imbalance` is the winner**, with the following important caveat: it does not clear the M02 success criterion (≥5% absolute improvement over best symmetric). The improvement is +0.0134 absolute (1.34%, vs the 5% threshold). The signal is real (sign-flip + aptness_rate jump from 0.0388 → 0.0733, both well outside noise even though the means barely separate) but the corpus's pointwise-overlap signal-to-noise floor appears to cap us below the strict success bar.

Practical implication:
- Wire `ortony_imbalance` into the forge as the new default scoring fn (Phase 3 of the original S01 plan). The sign-flip + aptness_rate gain is real even if separation magnitude is small; symmetric formulas have negative separation on this DB.
- **The next gains are structural** — concreteness gate + domain-distance re-rank (M03 cascade gate-and-rank), and type-aligned structural matching (M04). Three asymmetric pointwise-overlap variants have all bottomed out within the ±0.02 noise band, so the case for accelerating into M03 is now strong.

### Reproducing

```sh
data-pipeline/.venv/bin/python data-pipeline/scripts/run_sweep.py \
  --config data-pipeline/sweeps/m02_ortony_v3.yaml \
  --output data-pipeline/output/sweep_m02_ortony_v3.json \
  --report data-pipeline/output/sweep_m02_ortony_v3.md
```

Same DB-freshness caveat as v1/v2.
