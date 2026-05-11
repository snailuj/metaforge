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

- **Does the current pipeline produce per-side salience scores, or are they collapsed by the time scoring runs?** The post-M02-merge snap accumulator (rewritten in PR #17) carries `salience_sum` per (synset, cluster). Need to verify whether the forge endpoint hands the scoring fn enough info to compute `salience_B(p)` and `salience_A(p)` independently.
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
- **S03 — Wire winner into forge + integrate.** Update the API handler's default scoring fn. Update docs. Manual spot-check of `/forge` against the metaphor-pairs fixture.

Each slice is its own commit set on `m02/asymmetric-ortony-scoring`. A slice = one PR is fine if they end up substantial; otherwise bundle as a single PR at the end.

## Pre-flight checklist before starting S01

- [ ] PR #17 (code-review-loop) is merged to main, this branch rebased onto updated main
- [ ] `baseline_v2.yaml` re-run on the post-PR-#17 DB to confirm the symmetric reference numbers
- [ ] Read `evaluate_aptness.py:SCORING_FNS` to confirm the current registry signature and per-side data availability
- [ ] Read the M01 SENSITIVITY-V2-FINDINGS doc for the existing symmetric baseline numbers
