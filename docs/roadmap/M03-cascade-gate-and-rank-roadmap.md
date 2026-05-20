# M03 — Cascade Gate-and-Rank

**Status:** Planned (kicked off 2026-05-17).
**Branch:** TBD — cut from main once the M02 integration PR merges.
**Depends on:** M02 — Asymmetric Ortony Scoring **closed empirically negative** ([retro](../../data-pipeline/sweeps/M02-S04-CLOSING-findings.md)) + the M02 retro deliverables landed on main (eval harness on balanced cohort, sensorimotor prompt, Haiku enrichment).
**Eval target:** `separation_score > 0.05` (absolute) above the M02 plateau of `±0.06`, measured on the same `apt_pairs_v2` / `munch_inapt.jsonl` cohort the M02-S04 retro stabilised.

---

## Goal

Restructure the forge from a single pointwise scoring formula into a **three-stage cascade**:

```
candidate pair (A, B)
  ├── stage 1: concreteness gate           (filter — binary in/out)
  ├── stage 2: Ortony rank                 (continuous score from M02's registry)
  └── stage 3: domain-distance re-rank     (additive adjustment)
                ↓
              final aptness score
```

Move discriminative `separation_score` above the M02 plateau (every pointwise variant landed within ±0.06 of zero) by changing the *primitive* rather than the *formula*.

## Hypothesis

The Lakoff/Johnson family of conceptual-metaphor theory makes two structural claims that pointwise property-overlap cannot capture:

1. **Concreteness asymmetry.** Apt metaphors move from concrete source domains to more abstract target domains ("anger *is* fire", "ideas *are* containers"). A pair where both sides are equally concrete (or equally abstract) is structurally not metaphorical — it's analogy or paraphrase. A **concreteness gate** that drops same-tier pairs should remove a measurable chunk of inapt MUNCH paraphrase pairs while preserving apt pairs.

2. **Intermediate domain distance.** Apt metaphors cross domains but not arbitrarily far — too-close pairs are tautological ("anger is rage"), too-far pairs are nonsensical ("anger is bandwidth"). A **domain-distance re-rank** that rewards intermediate cross-domain pairings should lift apt and depress inapt within whatever ranking the Ortony stage produces.

If both predictions hold, the cascade should lift `separation_score` from ≈0 (M02 plateau) into the 0.05–0.30 range. If only one holds, we still have a publishable result on which structural primitive was load-bearing.

## Why this is the right next milestone

- **Closes M02's published plateau with a different mechanism class.** Every pointwise property-overlap variant (jaccard / cosine / asymmetric Ortony) landed within ±0.06 of zero on the balanced cohort. The retro's "genuinely unknown" list explicitly named structural primitives as the next available lever.
- **Uses substrate that already exists in the DB.** `synset_concreteness` is populated (73,927 rows: 52,154 Brysbaert ground-truth + 21,773 FastText regression predictions); `synset_centroids` is populated (300-d FastText averages per synset). No new schema, no new enrichment pass.
- **Bounded blast radius.** New cascade evaluator module composes existing primitives; the Ortony stage *reuses* M02's `SCORING_FNS` registry verbatim. The Go forge handler is the last step, not part of the algorithmic work.
- **First milestone with a non-trivial composition contract.** Implies the `ScoringFn` interface widens (it currently only sees `{cluster_id: salience_sum}` — no synset_id, no concreteness, no centroid). M03 establishes the wider contract that M04 (type-aligned matching) and M05 (novelty tracking) will also need.

## Background — what cascade gate-and-rank means concretely

### Stage 1 — Concreteness gate

For each candidate pair `(A, B)`, look up `synset_concreteness.score` for each synset (1–5 Brysbaert scale; FastText-regression-imputed scores carry `source='fasttext_regression'`). Define the gate:

```
abs(score_A - score_B) >= concreteness_threshold  → pass through to stage 2
abs(score_A - score_B) <  concreteness_threshold  → drop (score = 0)
```

The threshold is a hyperparameter to sweep. Initial range to test: **0.5–1.5** Brysbaert points. A threshold of 0.0 reduces to "no gate" (the M02 baseline). A threshold of ≥3.0 keeps only sharply-asymmetric pairs.

Pairs missing concreteness on either side fail closed (no score). The M02 retro's cohort-shape diagnostic must run on whatever cohort survives the gate — gate-induced cohort skew is the first thing to verify.

### Stage 2 — Ortony rank

Reuse M02's `SCORING_FNS` registry. Default: `jaccard_salience` (the symmetric reference) until M03 decides whether any asymmetric variant earns its place again post-cascade. The Ortony stage produces a continuous `[0.0, 1.0]` score for surviving pairs.

### Stage 3 — Domain-distance re-rank

For each pair surviving the gate, compute the cosine distance between the synset centroids:

```
d(A, B) = 1 - cosine(synset_centroids[A], synset_centroids[B])  ∈ [0, 2]
```

Apply a triangular reward window centred on an intermediate distance:

```
re_rank_bonus(d) = max(0, 1 - |d - d_target| / d_window)
final_score = ortony_score * (1 + alpha * re_rank_bonus(d))
```

Hyperparameters to sweep:
- `d_target` — the centre of the "ideal" cross-domain distance. Initial guess: median apt-pair distance from the M02 balanced cohort. Compute first, sweep around it.
- `d_window` — width of the reward window.
- `alpha` — re-rank strength (0.0 reduces to no re-rank; 1.0 doubles the score at peak distance).

### Composition contract

The existing `ScoringFn = (pa, pb) -> float` signature does not give the cascade what it needs (no synset_id, no concreteness, no centroid). M03 introduces a wider evaluator that consumes synset_ids and the DB connection, and reuses the existing `ScoringFn` registry internally for the Ortony stage. Concretely:

```python
CascadeFn = Callable[[sqlite3.Connection, str, str, CascadeConfig], CascadeResult]
```

`CascadeResult` carries the final score, whether the pair passed the gate, the raw Ortony score, the re-rank bonus, and the cosine distance — enough for the harness to surface ablation slices in one sweep run.

## The two-stage eval (load-bearing)

The DB state has shifted under us between M02's published numbers and M03's first run:

| Aspect                | M02 published state                                 | M03's eventual production state                          |
|-----------------------|-----------------------------------------------------|----------------------------------------------------------|
| Enriched synsets      | ~12,545                                             | ~36,259 after the 2026-05-17 curated-vocab rebuild       |
| Prompt vocabulary     | mixed (sonnet/gemini pre-rename + haiku-sm M02-S04) | uniform haiku-sm                                          |
| Pre-purge curated     | 11,286 (8,523 pre-rename + 2,763 post)              | 35,000 (all post-rename, uniform haiku-sm)               |

Running M03 against the rebuilt DB and comparing to the M02 published numbers would entangle **algorithm + prompt + model + coverage** in a single delta. Useless for the algorithmic question we actually want to answer.

M03 therefore runs in two stages:

### Stage 1 — M03 vs M02 algorithmic baseline *(clean ablation, M02-state DB)*

- **DB:** `data-pipeline/output/lexicon_v2.db.pre-purge-20260517` (336 MB). This is the exact byte-state on which the published M02 plateau numbers were measured.
- **Baseline numbers:** `data-pipeline/output/sweep_m02_ortony_v3_post_haiku_rebuild.json` — published `random_uniform = +0.0068`, `ortony_imbalance = −0.0005`, every formula within ±0.06.
- **What it answers:** does the cascade lift `separation_score` on the *same data state* where every pointwise formula plateaued? If yes, the algorithm is the lift, unambiguously.
- **Retention requirement:** the pre-purge backup must survive the "purge old DB backups" backlog item. Tagging it with `.keep-for-m03-baseline` companion file makes the protection explicit and machine-readable.

### Stage 2 — M03 on the production data state *(forward validation, rebuilt DB)*

- **DB:** the rebuilt `data-pipeline/output/lexicon_v2.db` after the running `enrichment_curated-props_haiku-sm_v2_20260517.json` lands and gets imported (`m02_s04_clear_and_import.py` or equivalent). 35k curated synsets, all post-rename, uniform haiku-sm.
- **Baseline numbers:** re-establish on the rebuilt DB *before* declaring the M03 delta. Re-run `random_uniform` + the legacy `jaccard_salience` + `ortony_imbalance` from `m02_ortony_v3.yaml` against the new DB. These become the *Stage 2 baseline JSON* (suggested path: `data-pipeline/output/sweep_m02_baseline_post_curated_rebuild.json`).
- **What it answers:** does the M03 algorithm still lift in the production data state, where the substrate has changed underneath it? Required for the "ship it" decision; not required for the "algorithm works" decision.

Stages can run in parallel — Stage 1 starts now against the pre-purge backup (the running enrichment doesn't block it); Stage 2 runs once the enrichment + import completes.

Both stages publish:
- A cascade sweep config (`m03_cascade_v1.yaml`) covering: pure-Ortony baseline, gate-only, rank-only, re-rank-only, full cascade.
- A `findings.md` doc with the M02-S04-A/B cohort-shape preflight, ablation table, and Lakoff-prediction test results.

## Success criteria

### Stage 1 (algorithmic — required to declare M02 plateau broken)

- **Tier 1 (composed harness):** `separation_score` on the full cascade ≥ 0.05 (absolute) above the M02 plateau ceiling of +0.06. Operationally: `cascade_separation - random_uniform_separation ≥ 0.05`.
- **Tier 2 (ablation cleanliness):** running each stage independently (pipeline-only, +gate, +rank, +re-rank) shows monotonic lift OR identifies which stage carries the signal. A cascade where the lift is entirely in one stage is a publishable narrative on its own.
- **Tier 3 (Lakoff predictions, harness-independent):**
  1. Apt MUNCH pairs show target-more-concrete-than-source asymmetry under Brysbaert ground truth (signed concreteness delta > 0 with p < 0.05).
  2. Apt pairs cluster at intermediate centroid distance — a Kolmogorov-Smirnov test against the inapt-pair distance distribution rejects the null at p < 0.05.

### Stage 2 (production — required to ship)

- Re-established baseline on rebuilt DB lands within ±0.05 of M02's published `random_uniform` (sanity check that the rebuilt DB hasn't broken the harness).
- Cascade `separation_score` on rebuilt DB ≥ Stage 1's number minus a 0.02 noise allowance.
- All Stage 1 Tier-3 predictions still hold on the rebuilt cohort (the predictions are about the world, not the data).

### Non-regression

- 588+ data-pipeline tests still pass. 658+ data-pipeline + API tests still pass. M03 adds tests for: cascade composition, concreteness-gate behaviour at threshold boundaries, re-rank bonus calculation, missing-concreteness fail-closed behaviour, `CascadeResult` shape contract.

## Open questions

- **Where does the cascade evaluator live?** Options: (a) extend `evaluate_aptness.py` with a parallel evaluator that the existing CLI routes to via a flag; (b) new `evaluate_cascade.py` that imports `evaluate_aptness`'s primitives; (c) widen `ScoringFn` contract so the cascade fits into `SCORING_FNS` as a single callable. **Leaning toward (a)** — keeps the eval surface unified, avoids two CLIs, and the contract widening is anyway the M04/M05 substrate.
- **Concreteness threshold sweep range.** Initial 0.5–1.5 Brysbaert points is a guess from inspecting a handful of apt pairs. Refine by computing the apt-pair concreteness-delta distribution on the M02 balanced cohort *before* designing the sweep.
- **What `d_target` initialises to.** Same answer: compute the apt-pair centroid-distance distribution first, centre the initial sweep on its median.
- **Should the gate use Brysbaert-only scores, or include the FastText-regression imputed scores?** Brysbaert-only halves the cohort coverage (52k / 73k synsets). FastText-imputed scores extend coverage but may carry model error correlated with the property substrate (the same FastText vectors built the centroids). **Pre-flight investigation needed:** sample 100 imputed scores, manually rate, measure imputation accuracy. Hold the decision until then.
- **Does the cascade compose multiplicatively or additively?** The Stage-3 formula above is multiplicative-on-Ortony. Additive (`final = ortony + alpha * bonus`) is a credible alternative. Both should appear in the Stage-1 sweep.

## Non-goals for M03

- **Type-aligned property matching** — that's M04. The cascade in M03 uses Ortony scoring as-is; it does not require properties to match by type (sensorimotor-to-sensorimotor, behaviour-to-behaviour, etc.).
- **Novelty / creative-yield tracking** — that's M05. M03 measures discriminative aptness only.
- **The Bridge** (graph-search-based explanation generator) — independent feature, can slot in any time per PIPELINE.md.
- **Substack post drafting** — gated on whether the result is publishable (Stage-1 verdict). If positive, an explanatory post sits naturally in the queue; if negative, the retro is the deliverable.
- **Property-vocab expansion / snap retuning** — already deferred from M02-S04 (S04-G remains backlog). Out of scope here.

## Slice plan

- **S01 — Cascade scaffolding + concreteness gate.** Widen evaluator contract (new `evaluate_cascade.py` module that takes synset_ids + DB conn + `CascadeConfig`). TDD the gate: threshold-boundary behaviour, missing-concreteness fail-closed, FastText-imputed handling. **Output:** the cascade module with the gate stage implemented, but no rank/re-rank yet. The pure-gate "pipeline" through the harness measures whether the gate alone moves anything. Pre-flight: compute apt-pair concreteness-delta distribution and centroid-distance distribution; use them to set the Stage-1 sweep ranges.
- **S02 — Domain-distance re-rank.** Implement the cosine-distance computation against `synset_centroids`. TDD the re-rank bonus shape (triangular window). Sweep config covering both multiplicative and additive composition. **Output:** full cascade compositions exercised in unit tests; sweep config `m03_cascade_v1.yaml` staged but not yet run.
- **S03 — Stage-1 eval on pre-purge backup.** Run `m03_cascade_v1.yaml` against `lexicon_v2.db.pre-purge-20260517`. Run S04-A/B cohort-shape preflight on the gate-survivor cohort. Run Tier-3 Lakoff-prediction tests as standalone scripts (independent of the harness — they're claims about the world). **Output:** `M03-S03-stage1-findings.md` with the ablation table, cohort-shape verification, and Tier-3 results. This is the go/no-go gate for the algorithmic premise.
- **S04 — Stage-2 eval on rebuilt DB.** Once the curated-vocab haiku-sm enrichment completes and lands: re-establish the baseline on the rebuilt DB; re-run the cascade; cross-check Stage-1 numbers. **Output:** `M03-S04-stage2-findings.md`. Conditional on Stage-1 passing.
- **S05 — Forge integration.** Wire the cascade into the Go API's `/forge/*` handler with feature-flagged enablement (so we can canary the cascade alongside the legacy scoring fn). Update operator-facing docs. Manual spot-check against `metaphor_pairs_v2.json`. **Output:** the cascade in production, controllable per-request. Conditional on Stage-2 passing.

Each slice is its own commit set. Slices ≥ S03 are findings-doc-bearing — keep the per-slice findings docs as flat siblings of this roadmap.

## Pre-flight checklist before starting S01

- [ ] **Pre-purge backup tagged for retention.** Create `lexicon_v2.db.pre-purge-20260517.keep-for-m03-baseline` next to the DB so the backlog cleanup script (when written) skips it.
- [ ] **M02 retro merged to main.** M03's eval-harness assumptions inherit from the retro's cohort-shape diagnostics and sensorimotor prompt — don't fork off until those are first-class on main.
- [ ] **Concreteness-delta + centroid-distance distributions characterised.** Run two one-shot diagnostic scripts on the M02 balanced cohort. These set the initial sweep ranges so we're not guessing.
- [ ] **FastText-imputed concreteness accuracy spot-checked.** 100-sample manual rating; if accuracy is poor, M03 starts with the Brysbaert-only-gate variant first and adds FastText-imputed as a later sweep.
- [ ] **Read M01 S03 sensitivity findings.** The `±0.02` noise band on this cohort is the floor below which differences are noise; M03's success criteria reference numbers above that floor.
- [ ] **Confirm `synset_centroids` coverage.** Spot-check: every synset that appears in apt or inapt pairs has a centroid. If coverage is partial, design the missing-centroid fail-closed behaviour up front.

## Strategic note — what M03's failure mode looks like

If Stage 1 returns `separation_score < 0.05`, M03 has not falsified the pointwise plateau. The retro from that result is itself valuable: it tells us the *structural* hypothesis class is also exhausted, and the next lever has to be something else entirely (M04's type-aligned matching, M05's novelty tracking, or a completely different substrate like graph search à la The Bridge). M03 publishes either way — there is no quiet "we tried and it didn't work" outcome.
