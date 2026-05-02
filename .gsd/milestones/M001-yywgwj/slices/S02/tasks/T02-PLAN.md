---
estimated_steps: 26
estimated_files: 3
skills_used: []
---

# T02: Build run_sweep.py harness over evaluate_aptness with structured results + comparison table

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

## Inputs

- ``data-pipeline/scripts/evaluate_aptness.py``
- ``data-pipeline/scripts/test_evaluate_aptness.py``
- ``data-pipeline/requirements.txt``
- ``data-pipeline/output/eval_baseline_v2.json``

## Expected Output

- ``data-pipeline/scripts/run_sweep.py` — sweep harness CLI with JSON + markdown outputs and per-variation isolation`
- ``data-pipeline/scripts/test_run_sweep.py` — integration tests for harness ranking, failure isolation, MRR reference column`

## Verification

source .venv/bin/activate && python -m pytest data-pipeline/scripts/test_run_sweep.py -v && source .venv/bin/activate && python -m pytest data-pipeline/scripts/ -v 2>&1 | tail -5

## Observability Impact

Adds INFO-level structured progress logs per variation (name, scoring, separation_score, duration_ms). Per-variation failures captured as status+error rather than fatal — preserves partial work for re-run idempotency. Output JSON's provenance block (schema_version, git_commit, timestamp) lets downstream tooling reproduce or trend a sweep across commits.
