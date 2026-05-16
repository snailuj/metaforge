# Code Review Loop — M02 Asymmetric Ortony Scoring + S04 Retro

**PR:** [#18](https://github.com/snailuj/metaforge/pull/18)
**Branch:** `m02/asymmetric-ortony-scoring`
**Base:** `main` @ `7ae65ade`
**Started:** 2026-05-16T11:11:55Z
**Loop config:** reviewers = [pr-review-toolkit, superpowers, standards, ux-designer]; max_iterations = 15
**Logfile convention:** This file is the canonical handover artifact between rounds. Reviewers read it as context (no editorialising).

## Scope

`git diff main..HEAD` excluding raw data files (`*.json` enrichment outputs, `snap_dropped.jsonl`). Files in scope (43):

**Library / pipeline code:**
- `lib/claude_client.py` (5 reliability fixes: parser dict/list, timeout, fence-strip, prose-tolerant JSON extraction, raw-response diagnostic)
- `lib/test_claude_client.py`
- `data-pipeline/scripts/evaluate_aptness.py` (3 new asymmetric Ortony scoring fns in `SCORING_FNS` registry)
- `data-pipeline/scripts/test_evaluate_aptness.py` (+23 tests for the new variants)
- `data-pipeline/scripts/enrich_properties.py` (preflight check, `--skip-preflight` and `--skip-enriched-required` flags)
- `data-pipeline/scripts/test_enrich_properties.py`
- `data-pipeline/scripts/run_sweep.py`, `test_run_sweep.py`
- `data-pipeline/scripts/snap_properties.py`, `test_snap_properties.py`
- `data-pipeline/SCHEMA.sql`, `data-pipeline/CLAUDE.md`

**S04 retro scripts** (acknowledged ad-hoc; future formalisation captured in Backlog `Pipeline Tooling Consolidation`):
- `data-pipeline/scripts/m02_s04_a_attrition_audit.py`
- `data-pipeline/scripts/m02_s04_b_union_sizes.py`
- `data-pipeline/scripts/m02_s04_build_apt_gap_synsets.py`
- `data-pipeline/scripts/m02_s04_clear_and_import.py`
- `data-pipeline/scripts/m02_s04_compare_sonnet_vs_haiku.py`
- `data-pipeline/scripts/m02_s04_finalise_eval_rebuild.py`
- `data-pipeline/scripts/m02_s04_g_vocab_audit.py`
- `data-pipeline/scripts/m02_s04_import_only.py`
- `data-pipeline/scripts/m02_s04_patch_and_repipeline.py`
- `data-pipeline/scripts/m02_s04_prompt_audit.py`
- `data-pipeline/scripts/m02_s04_reenrich_emotion_cohort.py`
- `data-pipeline/scripts/m02_s04_test_sensorimotor_prompt.py` (contains `BATCH_PROMPT_V2_SM`)

**Configs:**
- `data-pipeline/sweeps/m02_ortony_v1.yaml`, `m02_ortony_v2.yaml`, `m02_ortony_v3.yaml`, `m02_s04_threshold_sensitivity.yaml`

**Docs:**
- `data-pipeline/sweeps/M02-S02-sweep-findings.md`
- `data-pipeline/sweeps/M02-S04-A-attrition-audit.md`
- `data-pipeline/sweeps/M02-S04-apt-gap-classification.md`
- `data-pipeline/sweeps/M02-S04-B-union-sizes.md`
- `data-pipeline/sweeps/M02-S04-CLOSING-findings.md`
- `data-pipeline/sweeps/M02-S04-C-threshold-sensitivity-design.md`
- `data-pipeline/sweeps/M02-S04-G-vocab-audit.md`
- `data-pipeline/sweeps/M02-S04-prompt-audit-emotion.md`
- `data-pipeline/sweeps/M02-S04-prompt-rename-multidomain.md`
- `data-pipeline/sweeps/M02-S04-prompt-rename-test.md`
- `data-pipeline/sweeps/M02-S04-sonnet-vs-haiku.md`
- `docs/roadmap/M02-ortony-scoring-roadmap.md`
- `docs/roadmap/PIPELINE.md`
- `.claude/skills/metaforge-pipeline-management/SKILL.md`
- `.gitignore`

**Out-of-scope (raw data):** 5 `enrichment_*.json` files, 4 `m02_s04_*_synset_ids.json` files, `snap_dropped.jsonl`. These are diagnostic / training data artifacts, not source code.

---

## Deferrals Ledger

*(empty — first round)*

---
