# S03: Baseline and Sensitivity Validation — UAT

**Milestone:** M001-yywgwj
**Written:** 2026-05-03T00:35:16.169Z

## UAT Type

- UAT mode: artifact-driven + live-runtime
- Why this mode is sufficient: this slice produces no human-facing UI; its proof is the regenerable JSON/markdown sweep artefacts, the unit-test result, and the harness-output assertions. The committed config + findings note + scoring-fn registry entry are the durable evidence.

## Preconditions

- `data-pipeline/output/lexicon_v2.db` restored (`data-pipeline/scripts/restore_db.sh` if missing).
- `data-pipeline/.venv/` exists with requirements installed.
- `data-pipeline/output/eval_baseline_v2.json` present (S01 artefact, referenced by `mrr_reference` field in both sweep configs).

## Smoke Test

Run the unit test suite — 92 tests should pass in under 2 seconds:

```
data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_evaluate_aptness.py data-pipeline/scripts/test_run_sweep.py -q
```

Expected: `92 passed`.

## Test Cases

### 1. random_uniform null-control is deterministic and order-symmetric

1. Run: `data-pipeline/.venv/bin/python -m pytest data-pipeline/scripts/test_evaluate_aptness.py -v -k random_uniform`
2. **Expected:** 10 tests selected, 10 passed. Tests cover registry membership, determinism (same inputs twice → same output), order symmetry (score(pa,pb) == score(pb,pa)), salience invariance, distinctness across different cluster-id unions, score_pair status='scored' for non-empty inputs, evaluate() dispatch, CLI `--scoring random_uniform` dispatch.

### 2. Sensitivity sweep config exists and is committed

1. Run: `git ls-files data-pipeline/sweeps/sensitivity_v2.yaml data-pipeline/sweeps/SENSITIVITY-V2-FINDINGS.md data-pipeline/sweeps/README.md`
2. **Expected:** all three paths printed (file is tracked).
3. Confirm the YAML lists 5 variations whose `name` fields end with `_p95`, `_p50`, `_p99`, `_p95`, `_p95` respectively.

### 3. Harness end-to-end run produces distinguishable metrics

1. Run (takes ~15 minutes against the live V2 DB):
   ```
   data-pipeline/.venv/bin/python data-pipeline/scripts/run_sweep.py \
     --config data-pipeline/sweeps/sensitivity_v2.yaml \
     --output data-pipeline/output/sweep_sensitivity_v2.json \
     --report data-pipeline/output/sweep_sensitivity_v2.md
   ```
2. Then run the inline assertion block:
   ```
   data-pipeline/.venv/bin/python -c "import json; d=json.load(open('data-pipeline/output/sweep_sensitivity_v2.json')); vs=d['variations']; assert len(vs)==5 and all(v['status']=='ok' for v in vs); seps={v['name']:v['separation_score'] for v in vs}; assert len({round(s,4) for s in seps.values()})>=3; rnd=next(s for n,s in seps.items() if n.startswith('random_uniform')); assert abs(rnd)<=0.02; print('OK', seps)"
   ```
3. **Expected:** Exit 0 with `OK {...separation_scores...}` printed. 5 variations all `status: ok`, ≥3 distinct rounded separation_scores, |random_uniform sep|≤0.02.

### 4. Aptness-rate monotonicity in threshold_percentile

1. From the JSON, read `aptness_rate` for `jaccard_salience_p99`, `jaccard_salience_p95`, `jaccard_salience_p50`.
2. **Expected:** strictly monotonic ascending (more permissive thresholds yield higher aptness_rates). Observed: 0.000 < 0.039 < 0.332.

### 5. Findings note covers the four required points

1. Open `data-pipeline/sweeps/SENSITIVITY-V2-FINDINGS.md`.
2. **Expected:** the note explicitly covers (i) which variations the harness produced distinguishable metrics for, (ii) the absolute separation_score for random_uniform vs baseline, (iii) the aptness_rate monotonicity check across the three percentile points, and (iv) whether the harness verdict matches the slice's a-priori predictions.

## Edge Cases

### Sweep run interrupted mid-variation

1. Run the sweep, kill it after the first variation completes.
2. Re-run with the same `--output` path.
3. **Expected:** the run starts from scratch (no resume semantics in S02 harness) and overwrites the output file. This is by design — the sweep harness is currently not idempotent across partial runs; this is a known limitation, not a regression introduced by S03.

### random_uniform with two pa/pb that differ only in salience values

1. From a Python REPL with the venv active:
   ```python
   from data_pipeline.scripts.evaluate_aptness import SCORING_FNS
   pa1 = [{"cluster_id": "A", "salience": 0.1}]
   pa2 = [{"cluster_id": "A", "salience": 0.9}]
   pb  = [{"cluster_id": "B", "salience": 0.5}]
   assert SCORING_FNS["random_uniform"](pa1, pb) == SCORING_FNS["random_uniform"](pa2, pb)
   ```
2. **Expected:** assertion holds — score is salience-invariant by construction.

## Failure Signals

- Any of the 92 unit tests fail.
- The sweep run produces fewer than 5 variations or any with `status != "ok"`.
- Rounded separation_scores collapse to <3 distinct buckets (harness no longer discriminates).
- `|random_uniform separation_score|` exceeds 0.02 (null-noise band breached — investigate cohort size or determinism).
- aptness_rate non-monotonic across p99/p95/p50 (threshold-degradation prediction broken — points to a bug in the salience-weighted Jaccard logic, not in S03).
- `SENSITIVITY-V2-FINDINGS.md` missing or empty.

## Not Proven By This UAT

- This UAT does not statistically prove `random_uniform` is uniformly distributed — only that it is deterministic, order-symmetric, and yields |separation_score| inside ±0.02 on the V2 cohort. Tighter uniformity claims would require thousands of samples and are out of scope.
- This UAT does not prove the harness is sensitive to changes in scoring formulas other than the four currently registered. Adding new scoring fns (M2+) will need their own sensitivity validation.
- This UAT does not prove the absolute correctness of separation_score values — only that the harness produces distinguishable values across deliberately-degraded parameters.

## Notes for Tester

- The end-to-end sweep takes ~15 minutes against the V2 DB. The committed `sweep_sensitivity_v2.json/.md` artefacts in this branch were produced by the T02 run on 2026-05-03 and are sufficient evidence for the slice goal — re-running is only needed for regression checks.
- Variation IDs are suffixed with their threshold_percentile (e.g. `jaccard_salience_p95`); this is intentional — without the suffix two p95-vs-p50 runs of the same scoring fn would collide on the `name` field.
- The verification gate runs under `sh` (no `source` builtin); always use the direct `data-pipeline/.venv/bin/python` path in plan-embedded verification commands.
