---
estimated_steps: 15
estimated_files: 3
skills_used: []
---

# T03: Define + run baseline 3-variation sweep, commit sweep config + result artifact

Demo the harness by running the slice's stated 3-scoring-variation sweep against the live V2 DB and committing the reproducible artifacts.

Create `data-pipeline/sweeps/baseline_v2.yaml` with three variations: `jaccard_salience` (current S01 baseline), `jaccard_raw` (control — does salience weighting help?), `cosine_salience` (alternative formula motivated by S01 follow-up note). All use `threshold_percentile: 95`. Set `mrr_reference: data-pipeline/output/eval_baseline_v2.json` so the reference MRR appears in the comparison table.

Create the sweeps/ directory if it does not exist. Add a one-paragraph header comment in baseline_v2.yaml linking back to the slice goal and S01's separation_score (0.0103) so future readers understand the comparison anchor.

Run:
```
source .venv/bin/activate
python data-pipeline/scripts/run_sweep.py \
  --config data-pipeline/sweeps/baseline_v2.yaml \
  --output data-pipeline/output/sweep_baseline_v2.json \
  --report data-pipeline/output/sweep_baseline_v2.md
```

Verify the JSON contains 3 variations all with `status: ok`, the markdown table has 3 ranked data rows ordered by separation_score DESC, the wall-clock time is well under 30 min (expected: under 30 seconds — aptness eval is DB-direct, ~5s per run), and the provenance block has a non-empty `git_commit`.

Commit `data-pipeline/sweeps/baseline_v2.yaml`. The output JSON + markdown live under `data-pipeline/output/` which is gitignored except for the small SQL dumps; do NOT commit `sweep_baseline_v2.json` or `sweep_baseline_v2.md` — they are reproducible artifacts (matches S01's pattern of not committing eval_baseline_v2.json's raw JSON, only the schema and the sweep config).

Add a brief `data-pipeline/sweeps/README.md` (~20 lines) describing: how to add a sweep, how to run a sweep, where artifacts go, and that artifacts are not committed.

If any variation produces unexpectedly low separation_score (< 0 or NaN), do NOT block — the slice is about the harness contract, not finding the winning formula. Note observed numbers in the commit message and let S03/M2 follow-up address tuning.

## Inputs

- ``data-pipeline/scripts/run_sweep.py``
- ``data-pipeline/scripts/evaluate_aptness.py``
- ``data-pipeline/output/lexicon_v2.db``
- ``data-pipeline/output/eval_baseline_v2.json``
- ``data-pipeline/fixtures/metaphor_pairs_v2.json``
- ``data-pipeline/fixtures/munch_inapt.jsonl``

## Expected Output

- ``data-pipeline/sweeps/baseline_v2.yaml` — committed sweep config defining the 3-variation baseline`
- ``data-pipeline/sweeps/README.md` — committed how-to for sweeps directory`
- ``.gitignore` — ensures data-pipeline/output/sweep_*.json + .md are gitignored (only updated if not already covered)`

## Verification

source .venv/bin/activate && python data-pipeline/scripts/run_sweep.py --config data-pipeline/sweeps/baseline_v2.yaml --output /tmp/sweep_baseline_v2.json --report /tmp/sweep_baseline_v2.md && python -c "import json; d=json.load(open('/tmp/sweep_baseline_v2.json')); assert len(d['variations'])==3, d; assert all(v.get('status')=='ok' for v in d['variations']), d; print('ok')" && grep -c '^| ' /tmp/sweep_baseline_v2.md

## Observability Impact

Generates the first concrete sweep artifact pair (sweep_baseline_v2.json + .md). The markdown table is the human diagnostic surface; the JSON's provenance block (timestamp, git_commit, db_path) lets future agents re-run or trend across commits. Per-variation timing in logs reveals whether any scoring formula is unexpectedly slow on real data.
