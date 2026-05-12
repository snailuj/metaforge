# M02-S02 — First asymmetric variant sweep findings

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
