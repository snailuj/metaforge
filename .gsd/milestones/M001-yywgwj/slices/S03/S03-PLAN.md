# S03: Baseline and Sensitivity Validation

**Goal:** Validate that the S02 sweep harness detects sensitivity to deliberately degraded parameters by running a sensitivity sweep that contrasts the baseline (jaccard_salience @ percentile 95) against degraded-threshold variants and a null-control scoring fn known by construction to destroy semantic signal — and confirming the harness output exhibits distinguishable separation_score / aptness_rate metrics across those variations.
**Demo:** Show baseline metrics for current algorithm alongside metrics from deliberately degraded parameters, confirming the harness detects the difference

## Must-Haves

- Slice goal/demo are true at the operational proof level: a committed sensitivity sweep config runs end-to-end against the live V2 DB and produces a ranked JSON+markdown report whose rows show distinguishable separation_score values for baseline vs degraded vs null-control variations, with the null control's |separation_score| ≤ 0.01 within sampling noise.

## Proof Level

- This slice proves: operational — real runtime required (yes), human/UAT (no). The harness exists; this slice proves it discriminates parameter changes against the live V2 lexicon.

## Integration Closure

Upstream: data-pipeline/scripts/evaluate_aptness.py SCORING_FNS registry contract from S02-T01; data-pipeline/scripts/run_sweep.py harness contract from S02-T02; data-pipeline/sweeps/baseline_v2.yaml shape from S02-T03; data-pipeline/output/lexicon_v2.db live DB; data-pipeline/output/eval_baseline_v2.json MRR reference. New wiring: data-pipeline/sweeps/sensitivity_v2.yaml composes existing pieces — no new code paths beyond the new scoring fn. After S03, M001 is one slice (S04) from milestone-complete.

## Verification

- Reuses S02's per-variation INFO logs (scoring name, separation_score, aptness_rate, n_apt/n_inapt, duration_ms) and provenance block (schema_version, git_commit, config_path, db_path, mrr_reference_*). Adds one new SCORING_FNS entry (random_uniform) which is logged like every other scoring fn — no new diagnostic surface needed. Inspection surface for the sensitivity result: data-pipeline/output/sweep_sensitivity_v2.{json,md} (gitignored, regenerable from the committed config).

## Tasks

- [x] **T01: Add random_uniform null-control scoring function and tests** `est:45m`
  Extend the SCORING_FNS registry in data-pipeline/scripts/evaluate_aptness.py with `random_uniform` — a deterministic pseudo-random scoring fn keyed on the sorted concatenation of cluster_ids in pa∪pb. By construction it carries no semantic signal: any apt/inapt structure in the V2 corpus must yield separation_score ≈ 0 under this scoring. This becomes the slice's null reference for sensitivity validation in T02.

The scoring fn must:
- Be deterministic — same (pa, pb) inputs yield the same float across runs (use hashlib.blake2b on the canonical-sorted cluster_id string, mapped to [0,1]).
- Be order-insensitive across pa/pb so that score(pa,pb) == score(pb,pa) (sort the union, don't concatenate side-by-side).
- Return a float in [0,1] consistent with the existing scoring contract.
- NOT use random.random() / numpy.random — those are non-deterministic across processes without explicit seeding and would silently break reproducibility.

Add unit tests covering: registry membership, determinism (same inputs → same output, twice), order symmetry (pa,pb == pb,pa), distinctness (two clearly different (pa,pb) pairs yield different scores with overwhelming probability), evaluate() dispatch via scoring='random_uniform', and CLI dispatch via --scoring random_uniform (monkeypatch sys.argv pattern from S02 tests). Maintain the PairScore status invariant: random_uniform with non-empty pa & pb returns status='scored' (never accidentally 'no_properties').

Assumption (documented inline): the determinism+order-symmetry properties are sufficient for a null reference; we are NOT proving uniformity statistically — that would require thousands of samples and is out of scope.
  - Files: `data-pipeline/scripts/evaluate_aptness.py`, `data-pipeline/scripts/test_evaluate_aptness.py`
  - Verify: source data-pipeline/.venv/bin/activate && python -m pytest data-pipeline/scripts/test_evaluate_aptness.py -v -k random_uniform && python -m pytest data-pipeline/scripts/test_evaluate_aptness.py data-pipeline/scripts/test_run_sweep.py -v

- [x] **T02: Author sensitivity_v2 sweep config and run end-to-end against V2 DB** `est:1h`
  Author `data-pipeline/sweeps/sensitivity_v2.yaml` exercising five variations against the live V2 lexicon: (a) jaccard_salience @ threshold_percentile 95 — the S02 baseline anchor, (b) jaccard_salience @ 50 — deliberately degraded threshold (more permissive, predicted to push aptness_rate up and separation_score toward 0), (c) jaccard_salience @ 99 — deliberately degraded threshold (more restrictive, predicted to push aptness_rate down toward 0), (d) jaccard_raw @ 95 — secondary scoring-formula control already in S02 baseline, (e) random_uniform @ 95 — the T01 null reference. Reuse the same db/pairs/controls/mrr_reference fields as baseline_v2.yaml so the sensitivity output is directly comparable to the baseline output.

Header comment must link back to the slice goal, name the baseline anchor (S02-T03 baseline_v2.yaml), and name the expected sensitivity signature: 'aptness_rate monotonic in threshold_percentile; random_uniform separation_score within ±0.01 of zero'.

Run the sweep end-to-end with `data-pipeline/.venv/bin/python data-pipeline/scripts/run_sweep.py --config data-pipeline/sweeps/sensitivity_v2.yaml --output data-pipeline/output/sweep_sensitivity_v2.json --report data-pipeline/output/sweep_sensitivity_v2.md`. The two output files are gitignored (covered by S02's existing `data-pipeline/output/sweep_*.{json,md}` patterns) — DO NOT add new gitignore entries. All 5 variations must complete with `status: ok` in the JSON.

Write a concise findings note as `data-pipeline/sweeps/SENSITIVITY-V2-FINDINGS.md` (committed) summarising: (i) which variations the harness produced distinguishable metrics for, (ii) the absolute separation_score for random_uniform vs baseline (proof the harness signal moves), (iii) the aptness_rate monotonicity check across the three percentile points, (iv) whether the harness's verdict matches the slice's a-priori predictions. Reference the regenerable artefact paths but do NOT inline the full numbers — the artefacts are the source of truth.

Update `data-pipeline/sweeps/README.md` to mention sensitivity_v2.yaml alongside baseline_v2.yaml under 'Available sweeps'.

Assumption (documented in the findings note): if random_uniform's |separation_score| exceeds 0.01 on a single run we treat that as within sampling noise on the V2 cohort sizes (~232 apt, ~317 inapt) — this slice is not the place to prove a tighter bound.
  - Files: `data-pipeline/sweeps/sensitivity_v2.yaml`, `data-pipeline/sweeps/SENSITIVITY-V2-FINDINGS.md`, `data-pipeline/sweeps/README.md`, `data-pipeline/output/sweep_sensitivity_v2.json`, `data-pipeline/output/sweep_sensitivity_v2.md`
  - Verify: source data-pipeline/.venv/bin/activate && python data-pipeline/scripts/run_sweep.py --config data-pipeline/sweeps/sensitivity_v2.yaml --output data-pipeline/output/sweep_sensitivity_v2.json --report data-pipeline/output/sweep_sensitivity_v2.md && python -c "import json; d=json.load(open('data-pipeline/output/sweep_sensitivity_v2.json')); vs=d['variations']; assert len(vs)==5, f'expected 5 variations, got {len(vs)}'; assert all(v['status']=='ok' for v in vs), [(v['name'],v['status']) for v in vs]; seps={v['name']:v['separation_score'] for v in vs}; assert len({round(s,4) for s in seps.values()})>=3, f'harness did not distinguish variations: {seps}'; rnd=seps['random_uniform']; assert abs(rnd)<=0.01, f'random_uniform separation_score outside null-noise band: {rnd}'; print('sensitivity validation OK', seps)" && test -s data-pipeline/sweeps/SENSITIVITY-V2-FINDINGS.md && test -s data-pipeline/output/sweep_sensitivity_v2.md

## Files Likely Touched

- data-pipeline/scripts/evaluate_aptness.py
- data-pipeline/scripts/test_evaluate_aptness.py
- data-pipeline/sweeps/sensitivity_v2.yaml
- data-pipeline/sweeps/SENSITIVITY-V2-FINDINGS.md
- data-pipeline/sweeps/README.md
- data-pipeline/output/sweep_sensitivity_v2.json
- data-pipeline/output/sweep_sensitivity_v2.md
