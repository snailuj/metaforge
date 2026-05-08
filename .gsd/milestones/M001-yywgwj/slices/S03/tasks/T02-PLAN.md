---
estimated_steps: 6
estimated_files: 5
skills_used: []
---

# T02: Author sensitivity_v2 sweep config and run end-to-end against V2 DB

Author `data-pipeline/sweeps/sensitivity_v2.yaml` exercising five variations against the live V2 lexicon: (a) jaccard_salience @ threshold_percentile 95 — the S02 baseline anchor, (b) jaccard_salience @ 50 — deliberately degraded threshold (more permissive, predicted to push aptness_rate up and separation_score toward 0), (c) jaccard_salience @ 99 — deliberately degraded threshold (more restrictive, predicted to push aptness_rate down toward 0), (d) jaccard_raw @ 95 — secondary scoring-formula control already in S02 baseline, (e) random_uniform @ 95 — the T01 null reference. Reuse the same db/pairs/controls/mrr_reference fields as baseline_v2.yaml so the sensitivity output is directly comparable to the baseline output.

Header comment must link back to the slice goal, name the baseline anchor (S02-T03 baseline_v2.yaml), and name the expected sensitivity signature: 'aptness_rate monotonic in threshold_percentile; random_uniform separation_score within ±0.01 of zero'.

Run the sweep end-to-end with `data-pipeline/.venv/bin/python data-pipeline/scripts/run_sweep.py --config data-pipeline/sweeps/sensitivity_v2.yaml --output data-pipeline/output/sweep_sensitivity_v2.json --report data-pipeline/output/sweep_sensitivity_v2.md`. The two output files are gitignored (covered by S02's existing `data-pipeline/output/sweep_*.{json,md}` patterns) — DO NOT add new gitignore entries. All 5 variations must complete with `status: ok` in the JSON.

Write a concise findings note as `data-pipeline/sweeps/SENSITIVITY-V2-FINDINGS.md` (committed) summarising: (i) which variations the harness produced distinguishable metrics for, (ii) the absolute separation_score for random_uniform vs baseline (proof the harness signal moves), (iii) the aptness_rate monotonicity check across the three percentile points, (iv) whether the harness's verdict matches the slice's a-priori predictions. Reference the regenerable artefact paths but do NOT inline the full numbers — the artefacts are the source of truth.

Update `data-pipeline/sweeps/README.md` to mention sensitivity_v2.yaml alongside baseline_v2.yaml under 'Available sweeps'.

Assumption (documented in the findings note): if random_uniform's |separation_score| exceeds 0.01 on a single run we treat that as within sampling noise on the V2 cohort sizes (~232 apt, ~317 inapt) — this slice is not the place to prove a tighter bound.

## Inputs

- ``data-pipeline/sweeps/baseline_v2.yaml` — shape and field set to mirror (db/pairs/controls/mrr_reference/variations); also the baseline anchor referenced from the new findings note`
- ``data-pipeline/sweeps/README.md` — existing 'Available sweeps' section to extend`
- ``data-pipeline/scripts/run_sweep.py` — harness CLI contract this task drives end-to-end (no code change here)`
- ``data-pipeline/scripts/evaluate_aptness.py` — SCORING_FNS registry that must contain `random_uniform` from T01`
- ``data-pipeline/output/lexicon_v2.db` — live V2 lexicon the sweep reads`
- ``data-pipeline/output/eval_baseline_v2.json` — MRR reference loaded by run_sweep`

## Expected Output

- ``data-pipeline/sweeps/sensitivity_v2.yaml` — committed 5-variation sensitivity sweep config (header comment + name/db/pairs/controls/mrr_reference/variations)`
- ``data-pipeline/sweeps/SENSITIVITY-V2-FINDINGS.md` — committed concise findings note summarising the harness verdict and a-priori predictions check`
- ``data-pipeline/sweeps/README.md` — updated 'Available sweeps' section listing sensitivity_v2.yaml`
- ``data-pipeline/output/sweep_sensitivity_v2.json` — gitignored regenerable artefact, schema_version=1, all 5 variations status=ok, distinguishable separation_score values, random_uniform within ±0.01 of zero`
- ``data-pipeline/output/sweep_sensitivity_v2.md` — gitignored regenerable artefact, ranked markdown comparison table`

## Verification

data-pipeline/.venv/bin/python data-pipeline/scripts/run_sweep.py --config data-pipeline/sweeps/sensitivity_v2.yaml --output data-pipeline/output/sweep_sensitivity_v2.json --report data-pipeline/output/sweep_sensitivity_v2.md && data-pipeline/.venv/bin/python -c "import json; d=json.load(open('data-pipeline/output/sweep_sensitivity_v2.json')); vs=d['variations']; assert len(vs)==5, f'expected 5 variations, got {len(vs)}'; assert all(v['status']=='ok' for v in vs), [(v['name'],v['status']) for v in vs]; seps={v['name']:v['separation_score'] for v in vs}; assert len({round(s,4) for s in seps.values()})>=3, f'harness did not distinguish variations: {seps}'; rnd=next(s for n,s in seps.items() if n.startswith('random_uniform')); assert abs(rnd)<=0.02, f'random_uniform separation_score outside null-noise band: {rnd}'; print('sensitivity validation OK', seps)" && test -s data-pipeline/sweeps/SENSITIVITY-V2-FINDINGS.md && test -s data-pipeline/output/sweep_sensitivity_v2.md

## Observability Impact

Sweep run emits S02's per-variation INFO logs (scoring, separation_score, aptness_rate, n_apt, n_inapt, duration_ms) for all 5 entries plus a sweep-level wall-clock + ok/failed summary. Provenance block in the JSON pins the run to a git_commit, config_path, db_path, mrr_reference_path, mrr_reference_value — a future agent can reproduce the sensitivity result by re-running the committed config against the same DB. The committed findings markdown gives a stable narrative entry point even after the gitignored artefacts are regenerated.
