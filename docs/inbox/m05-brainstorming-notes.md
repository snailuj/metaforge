# M05 — Type-Aligned Structural Matching: Brainstorming Inputs

*Captured 2026-05-23 while the M04 v2 Lakoff sweep runs. Not yet a design — these are the inputs and open questions for the operator brainstorming session.*

> **Update 2026-05-24 — γ ratified at 1.0.** The γ-sweep notes below were written before the Phase 2 instrumentation landed. The authoritative verdict is now `data-pipeline/sweeps/m05_lakoff_gamma_verdict.md`, produced with `m05_cohort_diagnose.py` pre-flight diagnostics + `limit=10000` removing the ranking-cutoff confound. Headline: monotone separation lift from -0.25 at γ=0 to +0.27 at γ=2; γ=1.0 ratified (parity choice). The n=1 inapt caveat below remains valid for magnitude; the directional trend is now robust across 5 γ values. `aptness_rate=0` is also unchanged — γ moves ranks, not absolute scores.

## PIPELINE.md summary (one line)
> M05 — Type-Aligned Structural Matching *(renumbered from M04 on 2026-05-21)* — preserve property types during snap, type-diversity bonus in scoring. Lightweight approximation of SME isomorphic subgraph matching using data the pipeline already extracts.

## What "data the pipeline already extracts" means

The LLM enrichment (`enrich_properties.py`) extracts each property with a `type` field. Investigated against the live DB:

```
Property type frequencies (top 6, all >25k rows):
  sensorimotor: 147,183  (haiku-sm prompt biases toward this — 4+ required)
  behaviour:     83,113
  functional:    69,027
  effect:        44,844
  emotional:     40,769
  social:        25,962
Noise / legacy values (≤1k each): behavior, physical, behavioral, behavioural,
                                  temporal, spatial, intellectual, material, ...
```

Sample for `anger` (curated synset):
- `sensorimotor`: hot, burning, tense, intense, flushed
- `behaviour`: explosive, aggressive, reactive, surging
- `emotional`: hostile
- `effect`: consuming, destructive

So a single synset spans **3–4 distinct types**. The signal exists.

## Two-line system architecture

```
LLM extracts {text, type, salience, relation}
  → synset_properties (RAW: property_type column populated)
    → snap_properties.py (curation cascade: exact/morpho/embedding match)
      → synset_properties_curated (TYPE STRIPPED HERE — only synset_id, vocab_id, cluster_id, snap_method, snap_score, salience_sum)
        → vocab_clusters (TYPE-AGNOSTIC clustering)
          → cascade scorer (no type signal)
```

The cascade scorer only ever sees the curated tables. Property type information is dropped at the curation step.

## Design decisions (need operator input)

### Decision 1: Where to persist property type for the curated path

Options:
| Option | Where type lives | Pros | Cons |
|---|---|---|---|
| **A** | New column `dominant_type` on `vocab_clusters` | One row per cluster; cascade lookup unchanged in shape; clean separation | Loses per-synset type distribution; "dominant" is a mode/argmax that throws away the polyphony |
| **B** | New column `property_type` on `synset_properties_curated` | Per-row type, full fidelity | Mostly redundant with vocab_clusters → property_vocabulary join chain; widens hot-path table |
| **C** | Type-distribution JSON on `vocab_clusters` (e.g. `{"sensorimotor": 0.6, "behaviour": 0.4}`) | Polyphony preserved | JSON column awkward in Go; query-side aggregation needed |
| **D** | Compute at scoring time via join through `synset_properties` (raw table) | No schema change; uses existing data | Hot-path joins are expensive; cascade tests already complain about latency |

**Initial lean:** A (dominant_type on vocab_clusters) — simplest data model, fastest at scoring time, sufficient for a "type-diversity bonus" that counts distinct dominant types across shared clusters. C is the "more correct" option but adds JSON handling complexity that we can defer if A is enough.

**Recommendation to operator:** start with A, evaluate against the Lakoff cohort. If type-diversity bonus is too coarse to discriminate apt vs inapt, escalate to C.

### Decision 2: Type-diversity bonus shape

Once shared clusters between topic and vehicle have types, what's the bonus formula? Options:

| Option | Formula | Behaviour |
|---|---|---|
| **A** | `1{≥2 distinct types among shared}` | Gate: candidates must span ≥2 types to qualify for the bonus |
| **B** | `(distinct_types_count - 1) / (max_types - 1)` | Linear in distinct-types count, normalised to [0, 1] |
| **C** | Shannon entropy of shared type distribution | Rewards balanced spread; high when types are equally represented |
| **D** | `(distinct_types_count / total_shared_clusters)` | Per-cluster type density |

**Initial lean:** B (normalised linear) — simple, interpretable, monotone in distinct-types. Hyperparameter `gamma` controls weight. C (entropy) is more principled but harder to communicate.

### Decision 3: Composition with existing cascade

Current M03/M04 cascade (after sweep verdicts):
```
gate (concreteness threshold)
  → ortony score = jaccard_salience(topic_props, vehicle_props)
    → final_additive = ortony + alpha · cosine_rerank_bonus
       or
       final_multiplicative = ortony × (1 + alpha · cosine_rerank_bonus)
```

How does type-diversity (`τ`) compose? Options:

| Option | Formula | Behaviour |
|---|---|---|
| **A — additive** | `final = ortony + alpha·cos + gamma·τ` | Each term independently contributes |
| **B — multiplicative** | `final = ortony × (1 + alpha·cos) × (1 + gamma·τ)` | Type-diversity scales the whole match |
| **C — type-weighted ortony** | `ortony_typed = Σ_t jaccard_salience(props_topic[t], props_vehicle[t]) / num_types_shared` | Replaces ortony with per-type-aggregated jaccard |
| **D — gate** | If `τ ≥ threshold`, apply existing ortony+cos. Else return 0. | Type-diversity as an additional gate |

**Initial lean:** A (additive) — composable with existing additive M03 winner. Requires a new hyperparameter `gamma` and a calibration sweep.

### Decision 4: Eval strategy

The Lakoff cohort I just built is the natural test bed. But M05's hypothesis is specifically that **type-diverse matches are MORE apt than mono-type matches**. To test this, we need to know whether classical Lakoff pairs DO share more types than random cross-domain pairs.

Quick hypothesis: anger ↔ fire share both **sensorimotor** (hot, burning) and **effect** (consuming, destructive). vs anger ↔ umbrella shares neither. The type-diversity bonus should boost the former and not the latter.

**Eval plan:**
- S01-snap-types-preserved → sweep with `γ ∈ {0, 0.25, 0.5, 1.0}` × type-diversity-bonus options A/B → pick the γ that maximises Lakoff separation_score
- If best γ > 0 with positive separation lift → M05 hypothesis validated
- If γ = 0 wins → M05 hypothesis doesn't hold on current data; revisit

### Decision 5: Type-cleanup before scoring

The DB has noise types (`behavior`, `behavioural`, `behavioral` — all variants of `behaviour`). The curation step could normalise these. But:
- The raw enrichment is what the LLM produced; rewriting is risky
- A view / aggregation table that maps noise → canonical is cleaner

**Quick fix:** during snap, normalise variant types to the canonical 6 (sensorimotor, behaviour, functional, effect, emotional, social). Anything else → `"other"`.

## Slice breakdown candidates

| Slice | Description | Effort | Depends on |
|---|---|---|---|
| **S01** | Add `dominant_type TEXT` to `vocab_clusters` schema. Update `snap_properties.py` to compute dominant_type per cluster (mode of all snapped-into properties' types). Backfill. | ~1 day | None (pipeline-side) |
| **S02** | Plumb type into cascade DB read. Extend `db.GetForgeCascadeCandidatesByLemma` and `GetForgeCascadeCandidatesByEmbedding` to surface cluster types alongside cluster_ids in the shared_props payload. | ~1 day | S01 |
| **S03** | Extend `forge.EvaluateCascadePair` with type-diversity bonus. Add `Gamma` field to `CascadeConfig`. Decide composition (A/B/C/D from Decision 3). | ~1 day | S02 |
| **S04** | Lakoff sweep with γ grid. Verdict ratifies hyperparameters. | ~half day | S03 + Lakoff cohort (already shipped on `m04v2/lakoff-cohort` branch) |
| **S05** | (Optional) Frontend hook to display the dominant type of each shared property in the forge UI. | ~half day | S03 |

## Items to escalate to operator before starting S01

1. **Decision 1 + 2 + 3 + 4** above — pick options to lock in design.
2. **Snap algorithm specifics** — for clusters with mixed types (e.g. property "hot" snaps into a cluster whose members are 60% sensorimotor + 40% effect), what's the dominant_type? Operator may want to weight by salience, ignore low-frequency types, or store the distribution.
3. **Backfill strategy** — re-running snap from scratch to populate dominant_type means re-running the full snap step (~30 min). Or a one-off backfill SQL? Operator's call on which is more auditable.
4. **Branch naming** — `m05/type-aligned` follows the M04 convention. Confirm.

## Out-of-scope (explicit)

- Full SME isomorphic subgraph matching (out of scope per PIPELINE — "lightweight approximation")
- Per-relation-type weights (the LLM also extracts `relation` strings; these aren't typed but could become a future M07)
- Type-aware re-ranking on the embedding path (the embedding path doesn't have shared cluster signal anyway; types are a property-overlap thing)
- Multi-sense type aggregation (M04 v2 backlog has multi-sense ANN; types on a per-sense basis is its own can of worms)

## Open question for me to investigate while waiting on operator

Is the noise-type proportion (≤1k rows for 15+ value variants) a problem? If `behavior` and `behaviour` are both used for the same conceptual type, snap normalisation should fold them. Quick win.

---

## Appendix — Property-type coverage audit (run 2026-05-23)

Counts from the live `lexicon_v2.db` after the M04 v2 close:

### Curated synsets with property-type data: 34,880

**Distribution of distinct property types per synset:**
| Distinct types | Synsets | % |
|---|---:|---:|
| 1 | 84 | 0.2% |
| 2 | 1,791 | 5.1% |
| 3 | 7,735 | 22.2% |
| 4 | 13,216 | 37.9% |
| 5 | 9,615 | 27.6% |
| 6 | 2,438 | 7.0% |
| 7 | 1 | 0.0% (noise variant slipped through) |

**Implication:** 99.8% of curated synsets span ≥2 types; 92.7% span ≥3 types. Type signal is well-populated across the curated vocabulary.

**Type-frequency across 4.3M curated property-rows:**
| Type | Rows | % |
|---|---:|---:|
| sensorimotor | 1,542,345 | 35.8% (haiku-sm prompt biases here) |
| behaviour | 879,284 | 20.4% |
| functional | 714,240 | 16.6% |
| effect | 466,449 | 10.8% |
| emotional | 431,741 | 10.0% |
| social | 273,582 | 6.3% |
| **other** (noise variants) | **1,676** | **0.04%** |

**Implication for Decision 5 (type-noise cleanup):** the noise bucket is 0.04% of rows. Variant-canonicalisation is a 1-line `CASE WHEN` during snap with negligible payoff. **Recommend folding into S01 as a 5-line tweak, not a separate slice.**

### Lakoff pair audit — type signatures

```
anger:   sensorimotor 331  behaviour 216  effect 125  emotional 87  social 25  functional 9
fire:    sensorimotor 1312 behaviour 966  effect 462  emotional 289 functional 245 social 87
doormat: sensorimotor 81   emotional 36   functional 27 behaviour 27  effect 18  social 9
```

**Surprising finding (operator should consider):** ALL THREE concepts span ALL SIX types. Lakoff's apt vehicle (fire) and the inapt control (doormat) both have full type coverage. **A naive "shared-types count" bonus won't discriminate anger↔fire from anger↔doormat — the discrimination has to live at the OVERLAP level, not the per-concept level.**

### What this implies for Decision 2 (bonus formula)

The audit reverses one of my early hypotheses. Type-diversity must be measured over **shared properties** (jaccard intersection), not over each concept's full property set. Concretely:

- For each cluster_id in `shared = topic.clusters ∩ vehicle.clusters`, look up `cluster.dominant_type`
- Bonus = `f(distinct(dominant_type[c] for c in shared))`
- M05 hypothesis: anger↔fire share clusters spanning `{sensorimotor, behaviour, effect}` (3 types), while anger↔doormat share clusters spanning `{sensorimotor}` (1 type — they both have generic "hot"-like or "textured"-like properties but no structural pattern).

**This makes Decision 1/A (dominant_type per cluster) load-bearing**: the bonus formula iterates shared clusters and reads `cluster.dominant_type`. The other Decision 1 options (B/C/D) make the bonus harder to compute on the hot path.

### Recommendation summary (still awaiting operator approval)

| Decision | Recommendation | Confidence |
|---|---|---|
| 1. Where to persist type | **A — dominant_type on vocab_clusters** | High (consistent with bonus formula) |
| 2. Bonus formula | **B — normalised distinct-type count over shared overlap** | Medium (audit clarified; reasonable starting point for sweep) |
| 3. Composition | **A — additive with γ weight** | High (composable with M03 additive winner) |
| 4. Eval | **Lakoff cohort + γ sweep grid {0, 0.25, 0.5, 1.0}** | High (cohort already shipped) |
| 5. Type-noise cleanup | **Fold into S01 (5-line CASE WHEN during snap)** | High (audit shows 0.04% noise) |

The single most consequential operator decision is **whether the M05 hypothesis is right at all** — i.e. whether the discrimination between apt and inapt cross-domain metaphors actually lives in the "distinct types in shared overlap" dimension. The audit suggests it might, but only running the sweep will tell. I'd recommend a short prototype: implement S01+S02+S03 with the lean recommendations, run a γ sweep against Lakoff, and only escalate if the verdict shows no separation lift.

---

## Progress

### S01 — snap preserves property type per cluster (landed 2026-05-23)

Schema + snap change only; no behaviour shift in cascade scorer yet.

- Added `dominant_type TEXT` column to `vocab_clusters` (SCHEMA.sql + `cluster_vocab.py` CREATE TABLE block). NULL until a snap run with type-tracking populates it; backward compatible with pre-M05 DBs.
- `snap_properties.py` now threads `synset_properties.property_type` through Pass 1 (exact + morphological) and Pass 2 (embedding), accumulating per-cluster type counts via `collections.Counter`.
- Added `_canonical_type()` helper that folds variant spellings (`behavior`, `behavioural`, `behavoural`, `behavour` → `behaviour`; `physical` → `sensorimotor`) into the 6 LLM-prompt-declared canonical types plus a catch-all `other` bucket for low-frequency residue (~0.04% of rows per the M04 v2 audit).
- After Pass 2 completes, snap writes the per-cluster mode (with deterministic tie-break by canonical-type ordering — sensorimotor wins first, other wins last) into `vocab_clusters.dominant_type` via a single `executemany` UPDATE. Missing-table case is handled with the same narrow `OperationalError` guard used for the existing vocab_clusters SELECT.
- Tests: `test_snap_populates_dominant_type_per_cluster` covers the happy path (2 sensorimotor + 1 behaviour → dominant=sensorimotor); `test_snap_normalises_variant_type_spellings` covers `_canonical_type` cases (variants, unknowns, NULL, empty). Existing snap tests updated to add `dominant_type TEXT` column + `NULL` value to inline fixtures. Full data-pipeline suite (664 tests) green.

S02 will plumb dominant_type into the cascade DB reads alongside shared cluster_ids. S03 will use it in `EvaluateCascadePair` for the type-diversity bonus.

---

## S02 progress — 2026-05-23

Landed on `m05/type-aligned`. `db.CascadeCache` gains a `ClusterTypes map[int64]string` field loaded via `loadClusterTypes` at startup. Pre-M05 DBs (with `dominant_type IS NULL` across all rows) trigger a `slog.Warn` at cache-load time: "vocab_clusters loaded but dominant_type is NULL for every row — pipeline needs snap_properties.py re-run for M05 type-aware scoring". Startup does NOT block on this — the cascade remains serviceable without type signal; M03/M04 scoring math is unchanged this slice.

Wire-up only — `cascadePipeline.score()` doesn't read `p.cache.ClusterTypes` yet. That's S03.

Tests: positive load test in `cascade_cache_test.go`, two synthetic-schema handler tests updated to include the new column. Full Go suite PASS.

---

## S03 progress — 2026-05-23

Landed on `m05/type-aligned`. The cascade scorer now computes a type-diversity bonus over shared clusters when `Gamma > 0` AND `ClusterTypes` is provided.

Key shapes:
- `CascadeConfig.Gamma float64` — weight; default 0.0 (M03/M04 behaviour preserved).
- `CascadeInputs.ClusterTypes map[int64]string` — optional; nil disables M05 even with Gamma>0.
- `CascadeResult.TypeDiversityBonus *float64` + `SharedTypesCount int` — diagnostics, set only when bonus fires.
- Helper `TypeDiversityBonus(shared, types) (bonus, distinct)` — `max(0, distinct-1) / (TypeDiversityMaxDistinct-1)` where `TypeDiversityMaxDistinct = 6`. `"other"` and `""` types are excluded from distinct count (not discriminating signal per the M04 v2 audit).

Composition: additive `final = ortony + Alpha·cosBonus + Gamma·typeBonus`. Decision 3/A.

Pipeline plumbing: `cascadePipeline.score()` now passes `p.cache.ClusterTypes` into `CascadeInputs`. No change to the JSON wire shape since `TypeDiversityBonus` and `SharedTypesCount` are not (yet) plumbed onto `forge.Match`. Adding them is straightforward when the UI lands — current omission keeps the wire contract identical for legacy/cascade consumers.

Tests added: TypeDiversityBonus 5-case unit coverage (empty/single/two-types/all-six/other-excluded), EvaluateCascadePair 3-case (Gamma=0 short-circuit / Gamma=1 lift / nil-ClusterTypes-with-Gamma>0 no-op), Validate gamma guards (negative/NaN/Inf).

Outstanding for S04:
- Live DB has `dominant_type = NULL` — must re-run snap before the γ-sweep can produce signal. ~5-30min on the test DB. Will run as part of S04 setup.

## S04 progress — 2026-05-23 (γ-sweep complete)

Lakoff cohort: 80 apt cross-domain pairs, 90 inapt within-domain pairs.

| γ | d_min | d_max | separation | apt_rate |
|---|------:|------:|-----------:|---------:|
| 0.00 | 0.4 | 0.85 | **-0.2695** (baseline, type bonus off) | 0.0 |
| 0.25 | 0.4 | 0.85 | -0.2046 | 0.0 |
| 0.50 | 0.4 | 0.85 | -0.1154 | 0.0 |
| 1.00 | 0.4 | 0.85 | **+0.0384** (first positive separation) | 0.0 |
| 2.00 | 0.4 | 0.85 | **+0.3193** (best cell) | 0.0 |
| 1.00 | 0.5 | 0.75 | 0.0000 (M04 v2 best band) | 0.0 |

**Monotone improvement in separation as γ rises.** Apt/inapt gap goes from -0.27 at γ=0 to +0.32 at γ=2. The trend is directionally consistent with M05's hypothesis (type-diversity carries cross-domain metaphor signal), but the underlying sample is thin — *the inapt distribution per cell collapsed to n=1 in the committed results* (most inapt vehicles failed to resolve via the API in this run; `apt_missing=64-67`, `inapt_missing=89-90` of 90). With n=1 on the inapt side, the separation metric is sensitive to which one inapt vehicle survived the API rather than to a real distributional difference. **The result is suggestive, not confirmatory.** Re-run with a broader resolving cohort (or relax the matcher so more inapt vehicles produce scores) before treating this as evidence sufficient to ratify a production γ value.

Caveat: `aptness_rate=0` everywhere. Apt pairs do not yet clear the absolute aptness threshold (apt_score > inapt mean + σ). Bonus alone is insufficient to push apt pairs over the apt-classification line. Expected — Lakoff cohort is deliberately harder than the V2 baseline, and the bonus is correctly placed at the *ranking* level rather than the *absolute-score* level.

Caveat #2: `embedding` and `both` columns are 0 across all cells. The M04 cosine-band path generates zero Lakoff cross-domain candidates — all hits in the sweep come from cluster overlap. The type bonus is therefore lifting cluster-overlap matches, not the cosine-band ones. M04 v2's β-bonus motivation (two-path agreement) gets no signal from this cohort either. Implication: future work should investigate why the cosine band does not surface Lakoff pairs even though it surfaces Forge candidates in the V2 baseline — likely the synset_centroids quality or the d_min floor.

Caveat #3: The matcher / API resolution path drops most Lakoff vehicles (apt_missing 64-67 of 80; inapt_missing 89-90 of 90). Before the next γ-sweep, audit why so many cohort vehicles fail to score — likely concreteness-gate misses or no_properties short-circuits — and either fix the cohort (use vehicles that pass the gates) or fix the gates (if they're too strict for cross-domain mode).

### Default Gamma — escalate to operator

Three defensible choices:
1. **γ=0.0 (status quo)** — M05 ships dormant. Operators flip via `METAFORGE_FORGE_GAMMA` env after ratifying this verdict. *Safest: no production default flip without operator sign-off.*
2. **γ=1.0 (conservative)** — first cell with positive separation. Matches Alpha=1.0 convention. Mild separation lift, no absolute aptness gain.
3. **γ=2.0 (aggressive)** — strongest separation, but type bonus weight exceeds Ortony weight (which sits in [0, 1]); risks over-rewarding type diversity at expense of property-overlap quality.

**Default chosen (this branch): γ=0.0** — code lands dormant. Production deployment can flip via env. The choice between option 2 and option 3 is a brainstorming-grade design decision that should be operator-ratified before becoming a code default.

Verdict file: `data-pipeline/sweeps/m05_lakoff_gamma_verdict.md`
Results: `data-pipeline/output/m05_lakoff_gamma_results.json`
