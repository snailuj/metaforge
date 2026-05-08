# M01: Automated Eval Harness — roadmap

**Status:** ✅ Done (merged 2026-05-03)

**Vision:** Replace MRR as the primary forge algorithm KPI with a discriminative aptness evaluator and automated parameter sweep, enabling algorithm research at the speed of hypothesis → sweep → evidence → commit. Once this milestone is complete, every subsequent algorithm change (M02–M05) can be validated in minutes, not hours.

## Success Criteria

- Discriminative aptness evaluator separates gold-standard pairs from inapt controls with >0.3 separation score
- Parameter sweep completes a 10-point grid in under 30 minutes
- Baseline metrics recorded for current algorithm (MRR + aptness rate + separation score)
- MRR retained as secondary regression metric alongside new primary KPIs
- V2 enrichment data (10,530 synsets) imported and accessible via forge API

**Caveat on the separation-score target:** the recorded baseline `separation_score = 0.0103` is below the 0.3 target. Closing that gap is downstream tuning work for M02+ — the harness itself is operational and detecting differences correctly (validated in S03 sensitivity sweep), so the bar of "harness is the right instrument" is met even if the underlying algorithm hasn't yet produced separation in the target range.

## Slices

- ✅ **S01: V2 Foundation + Aptness Evaluator** — V2 enrichment imported, MUNCH preprocessed, aptness evaluator + combined baseline shipped, V2 DB live on staging-next. ([detail](M01-eval-harness-S01-aptness-evaluator.md))
- ✅ **S02: Parameter Sweep Harness** — `run_sweep.py` shipped with YAML/JSON config support, scoring-fn registry, ranked markdown reports, isolated per-variation failure handling. ([detail](M01-eval-harness-S02-sweep-harness.md))
- ✅ **S03: Baseline and Sensitivity Validation** — five-variation sensitivity sweep validated against a-priori predictions; all five predictions passed. Findings doc at `data-pipeline/sweeps/SENSITIVITY-V2-FINDINGS.md`. ([detail](M01-eval-harness-S03-sensitivity-validation.md))

**Note on a phantom S04:** the GSD-generated ROADMAP at one point carried an S04 slice with a description identical to S03's. This was a harness-instability artefact (slice generator misfire), not a real piece of work. S03 is the true sensitivity-validation slice and is complete; no S04 ever existed substantively.

## Boundary Map

The milestone owned: aptness evaluator script, MUNCH preprocessor, sweep harness, baseline + sensitivity sweep configs, fixtures, tests, and the combined eval baseline JSON.

The milestone did NOT own: any forge scoring formula change (that's M02), any concreteness handling (M03), any property-type diversity logic (M04). M01 was instrumentation only.

## Substantive deliverables (paths after merge)

- `data-pipeline/scripts/evaluate_aptness.py` — aptness evaluator
- `data-pipeline/scripts/run_sweep.py` — generic sweep harness
- `data-pipeline/scripts/preprocess_munch.py` — MUNCH preprocessor
- `data-pipeline/scripts/test_evaluate_aptness.py` — evaluator tests
- `data-pipeline/scripts/test_run_sweep.py` — sweep harness tests
- `data-pipeline/scripts/test_preprocess_munch.py` — preprocessor tests
- `data-pipeline/sweeps/baseline_v2.yaml` — baseline sweep config
- `data-pipeline/sweeps/sensitivity_v2.yaml` — sensitivity sweep config
- `data-pipeline/sweeps/SENSITIVITY-V2-FINDINGS.md` — S03 deliverable
- `data-pipeline/sweeps/README.md` — sweep harness usage doc
- `data-pipeline/fixtures/munch_apt.jsonl` — apt fixtures (CC BY 4.0)
- `data-pipeline/fixtures/munch_inapt.jsonl` — inapt controls (CC BY 4.0)
- `data-pipeline/output/eval_baseline_v2.json` — combined baseline summary
- `data-pipeline/output/aptness_eval_baseline.json` — per-pair aptness scores
- `data-pipeline/output/eval_mrr_v2_baseline.json` — MRR run
- `docs/superpowers/review-logs/2026-05-02-milestone-M001-yywgwj-review.md`
- `docs/superpowers/review-logs/2026-05-03-milestone-M001-yywgwj-review.md`

## What comes next

See [PIPELINE.md](PIPELINE.md). M02 (Asymmetric Ortony Scoring) is the natural next slot — first real algorithm change to validate against the harness M01 just shipped.

The `review/m01-and-snap-memopt` branch is preserved as a frozen ref at the post-M01-merge HEAD for a future full-coverage code-review-loop pass (S03 had a code-review-loop, but the user has flagged that the broader milestone deliverable + the snap memory-opt refactor brought in alongside have not yet had a holistic review).
