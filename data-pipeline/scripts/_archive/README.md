# Archive — Historical Pipeline Scripts

Scripts moved here are **no longer in active use** but kept for reference
(linked from review logs, useful as patterns for similar future work).

If you find yourself wanting to run something from this directory, stop
and check whether a newer formal version exists in `data-pipeline/scripts/`
proper — the archive is the older path, not the canonical one.

## Pre-M01 prompt-evolution era

Built during the early evolutionary prompt-search exploration. Superseded
by direct prompt iteration in subsequent milestones (M02 retro and beyond).

- `evolve_prompts.py`, `test_evolve_prompts.py`, `EVOLVE_README.md` —
  evolutionary prompt-search driver.
- `prompt_templates.py`, `test_prompt_templates.py` — prompt template
  registry consumed by `evolve_prompts.py`.
- `bradley_terry.py`, `test_bradley_terry.py` — pairwise-preference scoring
  for prompt comparison.
- `rotation.py`, `test_rotation.py` — rotation policy for evolutionary
  candidate selection.
- `seed_exploration.py`, `test_seed_exploration.py` — seed-set exploration
  for the evolutionary loop.
- `generate_evolution_report.py`, `test_generate_evolution_report.py` —
  report writer for evolution-run output.
- `ab_test_purpose_prompt.py` — A/B harness for purpose-prompt variants.

## M02-S04 retro one-offs

Eleven ad-hoc scripts written during the M02 — Asymmetric Ortony Scoring
retrospective (closed empirically negative 2026-05-16). Each documents a
specific diagnostic or rebuild step from that retro. Kept verbatim
because the review log (`docs/superpowers/review-logs/2026-05-16-m02-
asymmetric-ortony-and-s04-retro-review.md`) and roadmap doc reference
them by name.

- `m02_s04_a_attrition_audit.py` — S04-A attrition diagnostic.
- `m02_s04_b_union_sizes.py` — S04-B union-size analysis.
- `m02_s04_g_vocab_audit.py` — S04-G vocab-audit diagnostic.
- `m02_s04_prompt_audit.py` — apt-pair prompt audit on emotion cohort.
- `m02_s04_test_sensorimotor_prompt.py` — pre-prod sensorimotor prompt
  smoke test (the canonical version eventually merged into
  `enrich_properties.py:BATCH_PROMPT_V2_SM`).
- `m02_s04_compare_sonnet_vs_haiku.py` — model A/B for the SM prompt.
- `m02_s04_clear_and_import.py`, `test_m02_s04_clear_and_import.py` —
  clear-and-import rebuild driver (the canonical version is now an open
  backlog item: `--clear-existing` flag on the production import path).
- `m02_s04_import_only.py` — import-only variant of the same driver.
- `m02_s04_patch_and_repipeline.py` — surgical patch + pipeline re-run.
- `m02_s04_reenrich_emotion_cohort.py` — emotion-cohort re-enrichment
  pass used during the retro.
- `m02_s04_finalise_eval_rebuild.py` — final-state rebuild finaliser
  for the post-retro eval baseline.
- `m02_s04_build_apt_gap_synsets.py` — apt-gap synset builder for
  cohort-shape diagnostic.

The "Pipeline Tooling Consolidation & Relevance Audit" backlog entry in
`docs/roadmap/PIPELINE.md` describes the longer-term plan for these
scripts (formalise the reusable patterns; archive or delete the rest).
This move resolves the second half of that plan — formalisation of the
reusable patterns remains open.
