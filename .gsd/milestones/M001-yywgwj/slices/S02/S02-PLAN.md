# S02: Parameter Sweep Harness

**Goal:** Build a parameter sweep harness that runs the aptness evaluator across a configurable set of scoring variations and produces a ranked comparison artifact (JSON + markdown table) carrying aptness_rate, separation_score, and the joint MRR baseline reference for each variation. Demo the harness end-to-end with 3 scoring formula variations.
**Demo:** Run sweep with 3 scoring parameter variations, show ranked comparison table with aptness rate + MRR + separation score for each

## Must-Haves

- After this: `python data-pipeline/scripts/run_sweep.py --config data-pipeline/sweeps/baseline_v2.yaml --output data-pipeline/output/sweep_baseline_v2.json` runs in well under 30 minutes, produces a ranked comparison table with 3 scoring variations each carrying aptness_rate + separation_score + threshold + n_apt/n_inapt, and the joint baseline MRR (from eval_baseline_v2.json) is shown as reference. The harness scales to a 10-point grid without code change.

## Proof Level

- This slice proves: contract — slice proves the harness contract works end-to-end on real data; M001 final assembly happens in S03/S04.

## Integration Closure

Upstream: evaluate_aptness.py (S01 contract — JSON in, JSON out), data-pipeline/output/lexicon_v2.db (S01 V2 DB), data-pipeline/output/eval_baseline_v2.json (S01 joint baseline). New wiring: run_sweep.py orchestrates evaluate_aptness.py invocations across a config list. Remaining for milestone: S03 baseline + sensitivity validation re-uses this harness to confirm degraded parameters produce visibly worse metrics.

## Verification

- Harness emits per-variation INFO logs (start/finish, timing, score counts) and a structured results JSON with provenance (git_commit, timestamp, db_path, config_path). Failure of any variation is reported per-variation with status="failed" + error message rather than aborting the whole sweep — preserves work on partial failure for idempotent recovery. Markdown report rendered alongside JSON gives at-a-glance diagnostic.

## Tasks

- [ ] **T01: Make evaluate_aptness.py scoring formula pluggable via a registry** `est:2h`
  Refactor `evaluate_aptness.py` so the scoring function is selected via a named registry rather than being hard-coded as salience-weighted Jaccard. This is the prerequisite for the sweep harness — without a pluggable scoring interface there is nothing meaningful to sweep over.

Add a `SCORING_FNS` dict mapping a string name → a callable with signature `(pa: dict[int,float], pb: dict[int,float]) -> float` where `pa`/`pb` are `{cluster_id: salience_sum}` mappings (the existing internal shape). Register at minimum:
- `jaccard_salience` (current behaviour — salience-weighted Jaccard, becomes the default)
- `jaccard_raw` (unweighted set-Jaccard over shared cluster_ids — control for whether salience weighting helps)
- `cosine_salience` (cosine similarity over the salience vectors aligned by cluster_id)

Thread the chosen scoring function through `score_pair()` and `evaluate()`. Add a `--scoring NAME` CLI flag (default `jaccard_salience`) and record the chosen name + threshold_percentile in the output's `config` block. The PairScore status semantics (`scored`/`unresolved`/`no_properties`) MUST be preserved unchanged — a scoring formula that returns 0.0 is still `scored`, distinct from a coverage gap.

Add unit tests: at least one focused test per registered scoring function exercising a known-overlap case + a no-overlap case + a salience-asymmetric case. Use the existing in-memory SQLite fixture pattern from `test_evaluate_aptness.py`. Verify CLI dispatch by invoking `main()` with a controlled sys.argv via `monkeypatch`.

Note (autonomous-mode assumption): registry keys live in lowercase snake_case; cosine over salience vectors uses zero-padding for cluster_ids missing from one side (standard sparse-cosine convention). Document both in the module docstring.
  - Files: `data-pipeline/scripts/evaluate_aptness.py`, `data-pipeline/scripts/test_evaluate_aptness.py`
  - Verify: source .venv/bin/activate && python -m pytest data-pipeline/scripts/test_evaluate_aptness.py -v && python data-pipeline/scripts/evaluate_aptness.py --scoring jaccard_raw --db data-pipeline/output/lexicon_v2.db --output /tmp/aptness_jaccard_raw.json && grep -q '"scoring":' /tmp/aptness_jaccard_raw.json

- [ ] **T02: Build run_sweep.py harness over evaluate_aptness with structured results + comparison table** `est:3h`
  Add `data-pipeline/scripts/run_sweep.py` — a CLI harness that reads a YAML or JSON sweep config (list of variation dicts) and runs `evaluate_aptness.evaluate()` once per variation, collecting results into a structured ranked artifact.

Sweep config shape (YAML preferred, parsed via `yaml.safe_load`; YAML is already a transitive dep via existing pipeline scripts — verify by grepping requirements.txt before adding a new import):
```yaml
name: baseline_v2
db: data-pipeline/output/lexicon_v2.db
pairs: data-pipeline/fixtures/metaphor_pairs_v2.json
controls: data-pipeline/fixtures/munch_inapt.jsonl
mrr_reference: data-pipeline/output/eval_baseline_v2.json   # optional — if set, MRR pulled from this file as a reference column
variations:
  - name: baseline
    scoring: jaccard_salience
    threshold_percentile: 95
  - name: raw
    scoring: jaccard_raw
    threshold_percentile: 95
```

For each variation: open the DB, invoke `evaluate()` with the overrides, capture `aptness_rate`, `separation_score`, `false_positive_rate`, mean scores, n_apt/n_inapt, threshold. On per-variation failure (e.g. unknown scoring name, DB read error), record `status='failed'` + `error` string and continue — do NOT abort the whole sweep (idempotency requirement, must-have).

Write TWO outputs:
1. JSON: `--output PATH` — full structured result with provenance block (`schema_version=1`, `timestamp` ISO, `git_commit`, `config_path`, `db_path`, `mrr_reference_path` if used) and a `variations: [...]` list of per-variation results.
2. Markdown: `--report PATH` (default: same dir as JSON, `.md` extension) — comparison table with columns `name | scoring | threshold | aptness_rate | separation_score | mean_apt | mean_inapt | n_apt | n_inapt | mrr_ref | status`, rows sorted by `separation_score DESC` (failed rows pinned to bottom).

Logging: per variation log start time, scoring name, end time, separation_score at INFO. Total sweep wall-clock at end.

Tests in `data-pipeline/scripts/test_run_sweep.py`:
- 2-variation sweep over the in-memory SQLite fixture pattern reused from test_evaluate_aptness.py — assert ranked ordering by separation_score, report markdown contains a header row + 2 data rows, JSON has variations[0]['name'] etc.
- 1 failure injection: variation with scoring='nonexistent' → status='failed' in results, sweep does not raise, other variations still complete.
- Optional MRR reference: when `mrr_reference` config key points at a file with the eval_baseline_v2.json shape, the report's `mrr_ref` column is populated; when omitted, the column shows `n/a`.

Must handle worktree-relative paths consistently (resolve relative to cwd, fail-fast on missing inputs — mirror evaluate_aptness.py's --db existence check). Do NOT commit any output files in this task — those happen in T03.
  - Files: `data-pipeline/scripts/run_sweep.py`, `data-pipeline/scripts/test_run_sweep.py`, `data-pipeline/requirements.txt`
  - Verify: source .venv/bin/activate && python -m pytest data-pipeline/scripts/test_run_sweep.py -v && source .venv/bin/activate && python -m pytest data-pipeline/scripts/ -v 2>&1 | tail -5

- [ ] **T03: Define + run baseline 3-variation sweep, commit sweep config + result artifact** `est:1h`
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
  - Files: `data-pipeline/sweeps/baseline_v2.yaml`, `data-pipeline/sweeps/README.md`, `.gitignore`
  - Verify: source .venv/bin/activate && python data-pipeline/scripts/run_sweep.py --config data-pipeline/sweeps/baseline_v2.yaml --output /tmp/sweep_baseline_v2.json --report /tmp/sweep_baseline_v2.md && python -c "import json; d=json.load(open('/tmp/sweep_baseline_v2.json')); assert len(d['variations'])==3, d; assert all(v.get('status')=='ok' for v in d['variations']), d; print('ok')" && grep -c '^| ' /tmp/sweep_baseline_v2.md

## Files Likely Touched

- data-pipeline/scripts/evaluate_aptness.py
- data-pipeline/scripts/test_evaluate_aptness.py
- data-pipeline/scripts/run_sweep.py
- data-pipeline/scripts/test_run_sweep.py
- data-pipeline/requirements.txt
- data-pipeline/sweeps/baseline_v2.yaml
- data-pipeline/sweeps/README.md
- .gitignore
