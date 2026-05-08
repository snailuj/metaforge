# S02: Parameter Sweep Harness — UAT

**Milestone:** M001-yywgwj
**Written:** 2026-05-02T16:04:27.879Z

# S02 UAT — Parameter Sweep Harness

## Preconditions

- Worktree: `/home/agent/projects/metaforge/.gsd/worktrees/M001-yywgwj` (or any worktree with the V2 DB and S01 baseline materialised).
- `data-pipeline/output/lexicon_v2.db` present (S01 dependency).
- `data-pipeline/output/eval_baseline_v2.json` present (S01 joint baseline, used as MRR reference).
- `data-pipeline/.venv` activated with PyYAML installed (`source data-pipeline/.venv/bin/activate`). The worktree-root `.venv` is sufficient for pytest but NOT for running YAML sweeps — PyYAML is only in `data-pipeline/.venv`.
- Tests use `.venv` (worktree root); end-to-end sweep uses `data-pipeline/.venv`.

## Test Cases

### TC1 — Unit + integration tests pass

1. From repo root: `source .venv/bin/activate && python -m pytest data-pipeline/scripts/test_evaluate_aptness.py data-pipeline/scripts/test_run_sweep.py -v`.
2. Expect: exit 0, 54/54 passed (41 in test_evaluate_aptness, 13 in test_run_sweep).
3. Expect at minimum these named tests green: `test_score_pair_default_scoring_matches_jaccard_salience`, `test_score_pair_status_unchanged_across_scoring_formulas`, `test_evaluate_rejects_unknown_scoring_name`, `test_main_cli_rejects_unregistered_scoring`, `test_two_variation_sweep_ranks_by_separation_score`, `test_unknown_scoring_marks_variation_failed_without_aborting`, `test_mrr_reference_populates_report_column`, `test_per_variation_isolation_uses_fresh_connection`.

### TC2 — End-to-end 3-variation sweep against live V2 DB

1. `source data-pipeline/.venv/bin/activate`.
2. Run: `python data-pipeline/scripts/run_sweep.py --config data-pipeline/sweeps/baseline_v2.yaml --output /tmp/sweep_baseline_v2.json --report /tmp/sweep_baseline_v2.md`.
3. Expect exit 0 and per-variation INFO log lines (start/finish/separation_score) plus a final "sweep complete" line with total wall-clock and `ok=3 failed=0` counts.
4. Expect both `/tmp/sweep_baseline_v2.json` and `/tmp/sweep_baseline_v2.md` written.
5. Validate JSON: `python -c "import json; d=json.load(open('/tmp/sweep_baseline_v2.json')); assert d['schema_version']==1; assert d['git_commit']; assert len(d['variations'])==3; assert all(v['status']=='ok' for v in d['variations']); print('ok')"`.
6. Validate markdown: `grep -c '^| ' /tmp/sweep_baseline_v2.md` ≥ 4 (1 header + 1 separator + 3 data rows).
7. Wall-clock check: assert total duration < 30 minutes (observed: ~19.4 min on V2 DB; harness scales linearly per variation).

### TC3 — Variations sorted by separation_score DESC, MRR reference populated

1. After TC2, open `/tmp/sweep_baseline_v2.md`.
2. Expect column header: `name | scoring | threshold | aptness_rate | separation_score | mean_apt | mean_inapt | n_apt | n_inapt | mrr_ref | status`.
3. Expect 3 data rows ordered with `separation_score` non-increasing (highest first; on baseline V2 this is jaccard_salience > jaccard_raw > cosine_salience because all three are negative and least-negative wins).
4. Expect the `mrr_ref` column populated (0.0073 from `eval_baseline_v2.json`) on every row.
5. Expect `status` column = `ok` for all three rows.

### TC4 — Failure isolation (idempotency must-have)

1. Create `/tmp/bad_sweep.yaml` with one valid variation (`scoring: jaccard_raw`) and one invalid (`scoring: nonexistent_formula`).
2. Run the harness against it.
3. Expect exit 0 (sweep does NOT abort).
4. Expect markdown shows two rows; the `nonexistent_formula` row has `status: failed` and is pinned at the bottom.
5. Expect JSON: the failed variation has `status='failed'` and a non-empty `error` string; the valid one has `status='ok'` with normal metrics.

### TC5 — Backwards-compatible default behaviour

1. Run: `python data-pipeline/scripts/evaluate_aptness.py --db data-pipeline/output/lexicon_v2.db --output /tmp/eval_default.json` (no `--scoring`).
2. Expect exit 0 and `/tmp/eval_default.json` produced.
3. Validate: `python -c "import json; d=json.load(open('/tmp/eval_default.json')); assert d['config']['scoring']=='jaccard_salience'; print('default scoring locked')"`.
4. Confirms the default was not changed by the registry refactor.

### TC6 — Argparse rejects unregistered scoring before any DB work

1. Run: `python data-pipeline/scripts/evaluate_aptness.py --scoring nope --db data-pipeline/output/lexicon_v2.db --output /tmp/should_not_exist.json`.
2. Expect exit code != 0 and stderr message naming valid choices (`jaccard_salience`, `jaccard_raw`, `cosine_salience`).
3. Expect `/tmp/should_not_exist.json` NOT created.

### TC7 — Provenance block recorded in JSON output

1. After TC2, run: `python -c "import json; d=json.load(open('/tmp/sweep_baseline_v2.json')); [print(k, '=', d.get(k)) for k in ['schema_version','timestamp','git_commit','config_path','db_path','mrr_reference_path','mrr_reference_value']]"`.
2. Expect every field non-empty: schema_version=1, ISO timestamp, non-empty git_commit, config_path pointing at the input YAML, db_path pointing at lexicon_v2.db, mrr_reference_path + mrr_reference_value=0.0073.

### TC8 — Artefact-policy boundary

1. `git status data-pipeline/sweeps/` — expect `baseline_v2.yaml` and `README.md` tracked.
2. `git check-ignore data-pipeline/output/sweep_baseline_v2.json data-pipeline/output/sweep_baseline_v2.md` — expect both ignored.
3. Confirms reproducible artefacts are not committed; config + schema are.

## Edge Cases Covered by Automation

- YAML config with no `variations` key → fail-fast `ValueError` (TC: `test_load_sweep_config_rejects_missing_variations`).
- Config file with unsupported extension → fail-fast (`test_load_sweep_config_rejects_unknown_extension`).
- MRR reference path absent from config → `mrr_ref` column shows `n/a` (`test_load_mrr_reference_returns_none_when_path_missing`).
- MRR reference shape: nested `{mrr: {value: ...}}` and flat `{mrr: float}` both supported (`test_load_mrr_reference_reads_nested_baseline_shape`, `test_load_mrr_reference_reads_flat_shape`).
- PairScore `unresolved` and `no_properties` statuses unchanged across all 3 scoring formulas (`test_score_pair_status_unchanged_across_scoring_formulas`) — registry refactor does not alter coverage-gap semantics.

## Known Limitations / Open Items (not blockers — flagged for S03/M2)

- All 3 baseline scoring formulas produce NEGATIVE separation_score on V2 (mean apt < mean inapt). The harness contract works; the data signal does not discriminate apt from inapt MUNCH controls. S03/M2 will tune.
- PyYAML is only installed in `data-pipeline/.venv`, not in the worktree-root `.venv`. JSON sweep configs work in either; YAML configs require activating `data-pipeline/.venv` or installing `pyyaml` into `.venv`. Captured as MEM034.
- Wall-clock for the 3-variation baseline run was ~19.4 min on the live V2 DB (well under 30 min budget but longer than the task estimate of ~5s/run). A 10-point grid would be ~65 min on identical inputs — still acceptable for the milestone scaling claim, but a candidate for caching `(synset_id → properties)` across variations if budgets tighten.
