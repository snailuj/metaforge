# M02 — Asymmetric Ortony Scoring

**Status:** Active
**Branch:** `m02/asymmetric-ortony-scoring` (cut from review tip; rebases onto main once PR #17 lands)
**Depends on:** M01 Eval Harness + code-review-loop (PR #17)
**Eval target:** discriminative aptness on `apt_pairs_v2` vs `inapt_controls_v2`, measured via `run_sweep.py` against `baseline_v2.yaml`

---

## Goal

Replace the symmetric scoring formula in the forge with an asymmetric one that weights properties by **vehicle-side salience**. Move the discriminative aptness metric (separation_score on `baseline_v2`) above the symmetric baseline by a measurable margin.

## Hypothesis

Ortony (1979) argued that metaphorical aptness is governed by an asymmetry: in *"A is B"*, the vehicle (B) contributes its high-salience properties to the topic (A), regardless of how salient those properties are in A. The current scoring formulas (`jaccard_raw`, `jaccard_salience`, `cosine_salience`) treat the two sides symmetrically — overlap is overlap. That symmetry is the formula's biggest theoretical flaw and the source of false-positive aptness scores for shared but-not-metaphorical properties.

Asymmetric scoring should reward properties that are *prominent in the vehicle* and *less prominent in the topic*, which is what metaphor actually does.

## Why this is the right next milestone

- **Smallest algorithm change** that uses existing V2 data — no schema migration, no new enrichment pass, no new vocab.
- **Direct attack on the scoring formula's known flaw** — the M01 sensitivity sweep documented that all four current scoring functions are symmetric variants.
- **First real test of the eval harness** — M01 built the infrastructure (`evaluate_aptness`, `run_sweep`, scoring-fn registry); M02 exercises it by adding new scoring functions and measuring whether they move the needle.
- **Bounded blast radius** — implementation is one or two new entries in `SCORING_FNS` plus sweep configs. No structural pipeline changes (those come in M03).

## Background — what "asymmetric Ortony scoring" means concretely

Given two synsets A (topic) and B (vehicle), each with a set of curated properties, each property carrying a salience score:

- **Current (symmetric):** score is a function of the *intersection* of A's and B's properties — order-invariant, salience-weighted by both sides equally.
- **Asymmetric Ortony:** for each property `p` shared by A and B, weight by `salience_B(p) × (1 - salience_A(p))` (or similar) so that properties highly salient in the vehicle but only weakly salient in the topic dominate the score. This captures the "B contributes its prominence to A" intuition.

Variants to consider:
- Pure vehicle salience: `score = Σ_p∈A∩B salience_B(p)` (ignore topic salience)
- Imbalance-weighted: `score = Σ_p∈A∩B salience_B(p) × max(0, salience_B(p) - salience_A(p))`
- Log-ratio: `score = Σ_p∈A∩B salience_B(p) × log(salience_B(p) / salience_A(p))` (rewards relative prominence)

The eval harness tells us which one performs.

## Approach

### Phase 1 — Plumb asymmetric scoring through the eval harness *(small, mechanical)*

The current registry sits in `evaluate_aptness.py`'s `SCORING_FNS`. Each entry maps a name to a callable with signature `(score_pair_data) -> float`. The data already includes both sides; the scoring fn just has to choose to use it asymmetrically.

- Confirm `score_pair_data` (or whatever the call shape is — check current registry signature) exposes both synsets' properties separately, not just the intersection. If it doesn't, widen the contract first.
- Add `ortony_vehicle_salience` to the registry as the simplest asymmetric variant.
- Add a sweep variation in `baseline_v2.yaml` (or a sibling config) that exercises it alongside the four symmetric baselines.

### Phase 2 — Sweep + measure

- Run `python data-pipeline/scripts/run_sweep.py --config <config>` with the new variation.
- Compare `separation_score`, mean apt/inapt scores, and the existing M01 SENSITIVITY-V2-FINDINGS deltas.
- If asymmetric beats symmetric — great, lock in. If it doesn't, the variants above are next candidates.

### Phase 3 — Pick a winner + integrate into the forge

- Make the winning asymmetric scoring fn the default in the Go API's `/forge/*` handler (or whatever the current wiring is — check `api/internal/handler/`).
- Update the operator-facing docs.

## Success criteria

- **Quantitative:** `separation_score` on `baseline_v2` improves by ≥ 5% (absolute) over the best symmetric baseline. Specific number TBD once we know the current best symmetric value post-snap-rebuild.
- **Qualitative:** spot-check 10 metaphor pairs from `metaphor_pairs_v2.json` — asymmetric scoring should rank the canonical metaphorical target higher than symmetric did, OR the swap is small enough that the operator can sign off.
- **No regression:** all 535+ tests still pass; the new scoring fn has unit tests covering at least the three variants above.

## Open questions

- ~~**Does the current pipeline produce per-side salience scores, or are they collapsed by the time scoring runs?**~~ **Resolved 2026-05-12.** The eval-harness scoring registry already takes both sides separately: `ScoringFn = Callable[[Mapping[int, float], Mapping[int, float]], float]` (`evaluate_aptness.py:110-119`), and `_get_properties(conn, synset_id)` returns a per-synset `{cluster_id: salience_sum}` dict (`evaluate_aptness.py:98-105`). Asymmetric variants drop straight in as new entries in `SCORING_FNS` — no contract widening required. The Go forge handler is a separate question for Phase 3 wiring.
- **Which baseline to compare against — pre-PR-#17 main, or post-PR-#17 (the new snap behaviour)?** The PR-#17 review loop changed snap accumulator semantics (higher-quality method wins on collision). A small number of `synset_properties_curated` rows will differ. Strongly recommend re-running `baseline_v2.yaml` on the post-PR-#17 DB *before* M02 lands its first asymmetric variant — that re-establishes the symmetric baseline against the new snap state.
- **Should we ship a "Substack post" with the M02 results?** PIPELINE.md backlog notes 2-3 Substack posts as MVP-required. An "asymmetric scoring beats symmetric by X%" narrative is exactly the kind of post that wants to exist alongside this milestone.

## Non-goals for M02

- Concreteness gate / domain-distance re-rank — that's M03 (cascade gate-and-rank).
- Structural matching with type preservation — that's M04.
- Novelty tracking / creative yield curve — M05.
- Any pipeline architecture restructuring — M02 stays inside `evaluate_aptness.py` + sweep configs + the forge handler's scoring-fn selection.

## Slice plan (rough — refine as we go)

- **S01 — Plumb per-side salience through to scoring fn.** Verify or extend `score_pair_data`. Add `ortony_vehicle_salience` to registry with TDD. Targeted tests only; no sweep yet.
- **S02 — Re-baseline + sweep asymmetric variants.** Re-run `baseline_v2.yaml` on the post-PR-#17 DB to get the current symmetric reference. Add 2-3 asymmetric variations. Compare. Write a `M02-S02-sweep-findings.md` doc next to this one.
- **S03 — Wire winner into forge + integrate.** Update the API handler's default scoring fn. Update docs. Manual spot-check of `/forge` against the metaphor-pairs fixture. **Status: PARKED pending S04 retro conclusions.** S02 v1/v2/v3 all came in inside the ±0.02 null-noise band (see `data-pipeline/sweeps/M02-S02-sweep-findings.md`), so wiring an asymmetric variant into the Go forge would be locking in a winner whose discriminative gain is not yet credibly above noise. S03 stays parked until S04 confirms the eval harness is itself trustworthy on this cohort.

## S04 — Eval-Harness Retro

Gating step before any further M02 — Asymmetric Ortony Scoring algorithm work. Motivation: the S02 v1/v2/v3 sweep results were disappointing in absolute terms — three asymmetric variants all landed inside the ±0.02 noise band, with `ortony_imbalance` producing only a +0.0010 separation_score (sign-flip but tiny magnitude) and the M02 success criterion (≥5% absolute improvement) unmet. Before chasing more algorithm variants — or wiring the current best (`ortony_imbalance`) into the forge as S03 — we need to confirm the eval harness is actually performing as intended on this cohort. If the harness has a structural issue (e.g. unrepresentative surviving sample, distribution-skew driving the null drift, or instability at `threshold_percentile = 95`), then comparisons between scoring formulas are not measuring what we think they are measuring, and S03 would lock in a winner picked on noise.

### S04-A — Cohort-attrition audit ✅ *Done 2026-05-15*

Stratified why each apt and each inapt pair drops. Two smoking guns:

- **Apt cohort retention varies by 25.9pp across domains** — `emotion` retains 69% vs `cognition` 95%. The lost apt tail is dominated by abstract-emotion source words (sorrow, anxiety, contentment, shame, elation, nostalgia, ecstasy, wrath, frustration, humiliation, yearning, delight, longing, gratitude, awe, disgust, etc.). The most metaphor-relevant domain is the most under-represented.
- **Inapt cohort retains <25% across all three MUNCH genres** (NEWS 22%, ACPROSE 24%, FICTION 16%). The cohort is a 22% slice of the source data; most drops are paraphrase substitutes (onsets, onrushes, broomed, clutched) that don't resolve to any synset.
- Tier retention is uniform (weak/medium/strong all ~83-87%) — the bias is purely domain coverage, not metaphor strength.

Full report: [`M02-S04-A-attrition-audit.md`](../../data-pipeline/sweeps/M02-S04-A-attrition-audit.md). Generator: `data-pipeline/scripts/m02_s04_a_attrition_audit.py`.

### S04-B — Union-size distribution check ✅ *Done 2026-05-15*

Verdict: **cohort-shape mismatch confirmed.** Apt and inapt cohorts live in materially different property-count spaces:

| metric | apt median | inapt median | Δ% |
|---|---|---|---|
| `|pa|` | 10 | 15 | −33% |
| `|pa ∩ pb|` p95 | 2 | 4 | −39% |
| `|pa ∪ pb|` | 19 | 27 | −30% |

This mechanically explains the `random_uniform` null reference drifting to −0.0164 — the apt cohort's smaller unions land below thresholds computed from the inapt distribution. Independent of any scoring formula. Full report: [`M02-S04-B-union-sizes.md`](../../data-pipeline/sweeps/M02-S04-B-union-sizes.md). Generator: `data-pipeline/scripts/m02_s04_b_union_sizes.py`.

### Apt-gap classification ✅ *Done 2026-05-15*

Before doing a "surgical enrichment" of the 38 missing emotion-domain apt words, classified each by what would actually fix it:

| status | count | what fixes it |
|---|---|---|
| **unenriched** | **1** | surgical enrichment (just `comedy` / synset 70072) |
| **snap-dropped** | **37** | **snap retuning (S04-D below)** |
| unresolved | 3 | lexicon scope expansion (not M02) |

37 of the 38 missing apt synsets have LLM properties in `synset_properties` — every property dropped at snap at the current 0.7 cosine threshold. The lever is **snap retuning**, not enrichment. Full breakdown: [`M02-S04-apt-gap-classification.md`](../../data-pipeline/sweeps/M02-S04-apt-gap-classification.md). Generator: `data-pipeline/scripts/m02_s04_build_apt_gap_synsets.py`.

### S04-D — Snap threshold retuning 🟡 *In progress 2026-05-15*

Project memory `project_metaforge_snap_threshold_curve` records: *"Threshold default change 0.70 → 0.48 (validated, +30.4% aptness; pending qualitative API check)"*. The validation was on a prior harness (pre-M01) — needs re-verification under the M02-S04 cohort and the M02 scoring formulas.

Steps:
1. Back up DB. ✅
2. Re-snap at threshold 0.48 (`snap_properties.py --threshold 0.48`).
3. Re-run S04-A audit on the new snap state — verify the 37 snap-dropped synsets actually move to `has-properties`.
4. Re-run `m02_ortony_v3.yaml` sweep on the new snap state. Compare against the pre-0.48 S02 v3 results.
5. If S04-D lifts apt separation cleanly out of the noise band → S03 unblocks (with `ortony_imbalance` as the winner).
6. If partial → escalate to S04-G (curated-vocab expansion).

Output (when done): `data-pipeline/sweeps/M02-S04-D-snap-threshold-findings.md`.

### S04-C — Threshold-percentile sensitivity ⏸ *Deferred until S04-D resolves*

Config staged ([`m02_s04_threshold_sensitivity.yaml`](../../data-pipeline/sweeps/m02_s04_threshold_sensitivity.yaml)), 35 variations (7 scoring fns × 5 threshold percentiles), design doc at [`M02-S04-C-threshold-sensitivity-design.md`](../../data-pipeline/sweeps/M02-S04-C-threshold-sensitivity-design.md). Deferred so we don't measure threshold-of-threshold on a moving cohort — runs after D's new snap state stabilises.

### S04-G — Curated vocab expansion ⏸ *Queued, runs only if S04-D partial*

If lowering the snap threshold to 0.48 leaves residual snap drops in the apt cohort, the next lever is targeting which curated vocabulary entries are missing. Mine `data-pipeline/output/snap_dropped.jsonl` for high-frequency dropped property texts and promote them into `property_vocab_curated` (memory flags `resonant`, `earthy`, `angular` etc. as known sensorimotor losses). Then re-snap and re-evaluate.

### S04-E — Synthetic matched inapt cohort ⏸ *Last-resort escalation*

S04-A's 78% MUNCH attrition + the apt-vs-MUNCH cross-task asymmetry (cross-domain metaphor vs in-context paraphrase) may not be fixable inside the current cohort design. The clean alternative: generate a synthetic inapt cohort as random pairings of apt-side topics × wrong-domain vehicles drawn from the same domain distribution. Removes the attrition entirely and matches cohort structure. Biggest design change in the retro — only worth doing if D+G don't yield a clear winner.

### S04-F — Re-run sweeps after enrichment top-up ⏸ *Blocked on in-flight*

The 8k enrichment top-up is running concurrently with S04-D (`data-pipeline/output/enrichment_8k-topup_sonnet_v2_20260514.json`, ~52h ETA at batch-size 10). On completion, `enrich.sh --from-json` will import it into the DB. Then `m02_ortony_v3.yaml` re-runs on the enriched DB → measures whether broader coverage on its own moves the dial, independent of D/G/E.

### Sequence

The current execution sequence: **D-resnap → A-redux + ortony-sweep → assess → (C if D succeeds | G then re-sweep if D partial | E if both stall)**. F runs on its own track behind the in-flight enrichment.

**S03 stays parked until S04 reports a winner.** Once it does: M02 reassessment goes harness clean → revisit S03 wiring (or design variant 4); harness compromised → fix the harness first, then re-run S02 v3 sweep against the fixed harness before resuming algorithm work.

Each slice is its own commit set on `m02/asymmetric-ortony-scoring`. A slice = one PR is fine if they end up substantial; otherwise bundle as a single PR at the end.

## Pre-flight checklist before starting S01

- [x] PR #17 (code-review-loop) is merged to main, this branch rebased onto updated main *(merged 2026-05-12)*
- [x] `baseline_v2.yaml` re-run on the post-PR-#17 DB to confirm the symmetric reference numbers *(2026-05-12 — recorded in `M02-S02-sweep-findings.md`: jaccard_salience separation = −0.0124 on the post-#17 DB, replacing the +0.0103 M01 reference)*
- [x] Read `evaluate_aptness.py:SCORING_FNS` to confirm the current registry signature and per-side data availability *(2026-05-12 — confirmed asymmetric-ready, see Open Questions)*
- [x] Read the M01 SENSITIVITY-V2-FINDINGS doc for the existing symmetric baseline numbers *(2026-05-12 — noise band ±0.02 on current cohort sizes; baseline aptness_rate 0.0849, separation_score 0.0103 per CLAUDE.md)*
