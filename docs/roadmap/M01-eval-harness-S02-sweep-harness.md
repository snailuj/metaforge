# M01 / S02 — sweep harness

_Consolidated from the original GSD slice artefacts (PLAN, SUMMARY, UAT, REVIEW). Process metadata files (ALIGNMENT-INTAKE, REVIEW-LOG, CONTINUE) are omitted as GSD-internal bookkeeping with no forward-going value._

## Plan


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

- [x] **T01: Make evaluate_aptness.py scoring formula pluggable via a registry** `est:2h`
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

- [x] **T02: Build run_sweep.py harness over evaluate_aptness with structured results + comparison table** `est:3h`
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

- [x] **T03: Define + run baseline 3-variation sweep, commit sweep config + result artifact** `est:1h`
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

## Summary

---
id: S02
parent: M001-yywgwj
milestone: M001-yywgwj
provides:
  - ["data-pipeline/scripts/run_sweep.py CLI harness", "data-pipeline/scripts/evaluate_aptness.py SCORING_FNS registry contract (lowercase snake_case keys; jaccard_salience/jaccard_raw/cosine_salience)", "data-pipeline/sweeps/baseline_v2.yaml — committed reproducible 3-variation baseline sweep config", "Sweep output JSON schema (schema_version=1) with provenance block + variations[] list", "Markdown comparison table format with MRR reference column", "Per-variation failure isolation idempotency guarantee for any batch over evaluate_aptness"]
requires:
  - slice: S01
    provides: evaluate_aptness.py contract (JSON in, JSON out), data-pipeline/output/lexicon_v2.db, data-pipeline/output/eval_baseline_v2.json
affects:
  []
key_files:
  - ["data-pipeline/scripts/evaluate_aptness.py", "data-pipeline/scripts/test_evaluate_aptness.py", "data-pipeline/scripts/run_sweep.py", "data-pipeline/scripts/test_run_sweep.py", "data-pipeline/sweeps/baseline_v2.yaml", "data-pipeline/sweeps/README.md", ".gitignore"]
key_decisions:
  - ["Pluggable scoring via SCORING_FNS registry (lowercase snake_case keys; (pa,pb)->float signature over {cluster_id: salience_sum})", "Defence-in-depth on unknown scoring names: ValueError in evaluate() AND argparse choices=sorted(SCORING_FNS) at the CLI", "Cosine_salience zero-pads cluster_ids missing from one side (standard sparse-cosine convention)", "Per-variation fresh sqlite3 connection in run_sweep — failure isolation + no transaction-state leakage", "Per-variation failures captured as status='failed'+error and sweep continues — idempotency must-have", "PyYAML kept as optional dep, lazy-imported with install hint; JSON config works without it", "MRR reference loader accepts both nested {mrr:{value:..}} and flat {mrr:float} shapes for forward compat", "Output JSON schema: schema_version=1 + provenance block (timestamp, git_commit, config_path, db_path, mrr_reference_*) + variations[] list", "Markdown report sorted by separation_score DESC with failed rows pinned to bottom via tuple sort key", "data-pipeline/output/sweep_*.json and sweep_*.md gitignored (reproducible); data-pipeline/sweeps/*.yaml committed (config+schema)", "Did not block on negative separation_score across all 3 formulas — slice plan explicitly de-scoped formula tuning to S03/M2"]
patterns_established:
  - ["String-keyed scoring registry is the stable contract that future M001/M2 algorithm sweeps extend", "Sweep config shape: name + db + pairs + controls + optional mrr_reference + variations[{name, scoring, threshold_percentile}] — extensible to additional per-variation overrides without breaking existing configs", "Sweep output JSON shape: provenance block + variations[] is the reusable artefact format for any future sweep type (threshold sweeps, sensitivity, etc.)", "Markdown comparison table column set + sort-by-separation-DESC with failed-pinned-to-bottom is the at-a-glance diagnostic format for all sweeps", "Per-variation failure isolation (own DB connection + status/error capture, do not abort) is the idempotency baseline for any batch over evaluate_aptness", "Test fixture pattern: monkeypatch sqlite3.connect to in-memory DB + monkeypatch sys.argv for CLI tests — keeps the suite under 1s and decoupled from the real V2 DB"]
observability_surfaces:
  - ["run_sweep.py per-variation INFO logs: scoring name, separation_score, aptness_rate, n_apt/n_inapt, duration_ms", "run_sweep.py sweep-level INFO logs: total wall-clock, ok/failed counts", "run_sweep.py per-variation WARNING log on failure with the captured error string", "Output JSON provenance block: schema_version, timestamp, git_commit, config_path, db_path, mrr_reference_path, mrr_reference_value", "Markdown report's status column surfaces failed variations at-a-glance, pinned to bottom of the table"]
drill_down_paths:
  - [".gsd/milestones/M001-yywgwj/slices/S02/tasks/T01-SUMMARY.md", ".gsd/milestones/M001-yywgwj/slices/S02/tasks/T02-SUMMARY.md", ".gsd/milestones/M001-yywgwj/slices/S02/tasks/T03-SUMMARY.md", "data-pipeline/scripts/run_sweep.py", "data-pipeline/sweeps/baseline_v2.yaml", "data-pipeline/sweeps/README.md"]
duration: ""
verification_result: passed
completed_at: 2026-05-02T16:04:27.878Z
blocker_discovered: false
---

# S02: Parameter Sweep Harness

**Built a YAML/JSON-driven parameter sweep harness over evaluate_aptness with ranked JSON+markdown outputs, per-variation failure isolation, and a committed 3-variation baseline config that runs end-to-end against the live V2 DB.**

## What Happened

S02 turned the S01 single-shot aptness evaluator into a sweep-able algorithm research surface. Three tasks composed cleanly:

**T01 — pluggable scoring registry.** Refactored `evaluate_aptness.py` so the scoring function is selected via a `SCORING_FNS` dict keyed by lowercase snake_case names, with three registered formulas: `jaccard_salience` (the historic salience-weighted Jaccard, lifted byte-identical from the previous inline body and kept as default), `jaccard_raw` (unweighted set-Jaccard control over shared cluster_ids), and `cosine_salience` (sparse cosine over salience vectors with zero-padding for missing cluster_ids). The `(pa, pb) -> float` signature is the registry contract. Threaded a `scoring_fn` parameter through `score_pair()` and `_score_cohort()` (default callable, not the registry string, to keep call sites that bypass `evaluate()` backwards-compatible) and a `scoring: str` kwarg through `evaluate()` itself. Added `--scoring NAME` CLI flag with `choices=sorted(SCORING_FNS)` so argparse rejects unknown names before any DB work runs; `evaluate()` separately raises `ValueError` listing registered options for library callers — defence in depth so a sweep-config typo cannot silently fall back to the default. The chosen scoring name is now recorded in `result["config"]["scoring"]` alongside the existing threshold/percentile fields. The `PairScore` status semantics (`scored`/`unresolved`/`no_properties`) are unchanged: `score_pair` resolves synsets then checks for properties before invoking the scoring function, so a formula returning 0.0 (no overlap, orthogonal vectors) yields `status="scored", score=0.0`, distinct from a coverage gap. A regression test asserts this invariant across all three formulas. Test count grew 21 → 41.

**T02 — sweep harness.** Added `data-pipeline/scripts/run_sweep.py` — a CLI that loads a YAML or JSON sweep config (extension-detected; YAML lazy-imports `yaml` because PyYAML is not currently a pipeline runtime dep, falling back with a clear pip-install hint) and runs `evaluate_aptness.evaluate()` once per variation. **Per-variation isolation** is structural: each variation opens its own `sqlite3.connect`, and per-variation failures (unknown scoring name, DB read error, missing inputs) are captured as `status='failed'` + `error` string rather than aborting — satisfies the slice's idempotency must-have. Two outputs: a structured JSON via `--output` carrying a provenance block (`schema_version=1`, ISO timestamp, `git_commit`, `config_path`, `db_path`, optional `mrr_reference_path`/`mrr_reference_value`) and a `variations: [...]` list with `aptness_rate`, `separation_score`, `false_positive_rate`, mean apt/inapt scores, n_apt/n_inapt, threshold, and per-variation `duration_ms`; plus a markdown comparison report via `--report` (defaults to `<output>.md`) with the contracted columns and rows sorted by `separation_score` DESC, failed rows pinned to the bottom via tuple sort key. MRR reference loading accepts both the nested `eval_baseline_v2.json` shape (`{"mrr": {"value": ...}}`) and a flat `{"mrr": float}` shape for forward compatibility; missing reference paths fail fast. Per-variation INFO logs include scoring name, separation_score, aptness_rate, n_apt/n_inapt, duration_ms; sweep-level logs include total wall-clock and ok/failed counts. 13 new tests cover ranked ordering + markdown shape, failure isolation (failed row pinned to bottom), MRR reference column with and without a reference, fail-fast on missing inputs, per-variation isolation, and config-loading edge cases. Full pipeline suite: 469/469 green.

**T03 — baseline 3-variation sweep config + run.** Created `data-pipeline/sweeps/baseline_v2.yaml` with the three formulas at `threshold_percentile: 95` and `mrr_reference: data-pipeline/output/eval_baseline_v2.json`, plus a one-paragraph header comment linking back to the slice goal and S01's separation_score (0.0103) anchor. Added `data-pipeline/sweeps/README.md` documenting how to add/run sweeps and the artefact-policy boundary. Added `data-pipeline/output/sweep_*.json` and `sweep_*.md` to `.gitignore` (intentionally narrow — existing tracked eval JSONs stay tracked). The harness ran end-to-end against the live V2 DB and produced a 3-row ranked markdown table with the joint MRR baseline (0.0073) carried as a reference column. All 3 variations completed with `status: ok`.

**Patterns established for downstream slices.** The string-keyed scoring registry is now the contract that S03/M2 algorithm work will sweep over. The `(provenance + variations[])` JSON shape and the markdown comparison-table format are reusable for any future M001 sweep (sensitivity, threshold sweeps, future feature toggles). Per-variation failure isolation is the idempotency baseline — any future per-variation work (concurrent sweeps, longer grids) inherits this guarantee.

**Open observation, not a blocker.** All three formulas produced NEGATIVE separation_score on the V2 baseline (mean apt < mean inapt: jaccard_salience -0.0124, jaccard_raw -0.0130, cosine_salience -0.0198). The slice plan explicitly de-scoped formula tuning ("If any variation produces unexpectedly low separation_score (< 0 or NaN), do NOT block — the slice is about the harness contract"). The signal — that the current property/salience extraction does not discriminate apt from inapt MUNCH controls — is the open problem S03/M2 will address. Captured as MEM037 for downstream agents.

## Verification

All slice-level verification gates pass.

**Tests.** `python -m pytest data-pipeline/scripts/test_evaluate_aptness.py data-pipeline/scripts/test_run_sweep.py -v` → 54 passed in 1.05s. Full pipeline suite (per T02 verification) → 469/469.

**End-to-end demo against live V2 DB.** `source data-pipeline/.venv/bin/activate && python data-pipeline/scripts/run_sweep.py --config data-pipeline/sweeps/baseline_v2.yaml --output /tmp/sweep_baseline_v2.json --report /tmp/sweep_baseline_v2.md` produced both artefacts. JSON has `schema_version=1`, non-empty `git_commit=ac180f95`, 3 variations all with `status: ok`. Markdown has the contracted column header + 3 ranked data rows + the MRR reference (0.0073) populated for each row. Wall-clock 1164.5s ≈ 19.4 min — well under the 30 min must-have budget. (Longer than the task estimate of ~5s/run because aptness eval against the real V2 DB processes 232 apt + 317 inapt pairs per variation — the contract is "well under 30 min" and that holds.)

**Failure isolation contract.** Verified by `test_unknown_scoring_marks_variation_failed_without_aborting`: a sweep with a deliberately bad scoring name produces a `failed` row pinned to the bottom and other variations complete normally. Idempotency must-have proven.

**Provenance.** Verified by JSON inspection: `schema_version=1`, `git_commit=ac180f95`, `config_path=data-pipeline/sweeps/baseline_v2.yaml`, `db_path=data-pipeline/output/lexicon_v2.db`, `mrr_reference_path=data-pipeline/output/eval_baseline_v2.json`, `mrr_reference_value=0.0073`.

**Scaling claim ("scales to 10-point grid without code change").** Structural — config is a list, sweep is a `for` loop, no per-variation special-casing. Validated indirectly by the failure-isolation test (mixed ok+failed handled in one run) and by the 3-variation live run; no code change required to add 7 more entries.

## Requirements Advanced

None.

## Requirements Validated

None.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

None.

## Known Limitations

All 3 registered scoring formulas produce NEGATIVE separation_score on V2 baseline (mean apt < mean inapt). Slice plan explicitly de-scoped formula tuning — the harness contract works; the data signal is the open problem for S03/M2 follow-up. Captured as MEM037.

PyYAML is only installed in data-pipeline/.venv, not in the worktree-root .venv. JSON sweep configs work in both venvs; YAML configs require either activating data-pipeline/.venv or `pip install pyyaml` into .venv. Documented in MEM034 and data-pipeline/sweeps/README.md.

Live 3-variation sweep wall-clock is ~19.4 min (well under the 30-min budget but longer than the task-plan estimate of ~5s/run). A 10-point grid is ~65 min on identical inputs. If future grids tighten the budget, candidate optimisation is caching (synset_id → properties) once per sweep instead of per variation.

## Follow-ups

S03 will reuse this harness against deliberately degraded parameters to confirm sensitivity (the harness detects the difference). Negative-separation observation across all formulas is a follow-up signal for M2 (algorithm research) — possibly a curated-properties coverage problem rather than a scoring-formula problem; investigate property coverage on the MUNCH inapt cohort before tuning formulas. If sweep budgets tighten with larger grids, factor out a `(synset_id, source) -> properties` cache shared across variations.

## Files Created/Modified

- `data-pipeline/scripts/evaluate_aptness.py` — Added SCORING_FNS registry (jaccard_salience/jaccard_raw/cosine_salience), --scoring CLI flag with argparse choices, threaded scoring through score_pair/_score_cohort/evaluate, recorded scoring name in result.config block; preserved PairScore status semantics
- `data-pipeline/scripts/test_evaluate_aptness.py` — Added 20 tests covering each formula's known-overlap/no-overlap/asymmetric cases, registry membership, evaluate() default+override+unknown-name behaviour, CLI dispatch via monkeypatch (21 -> 41 tests)
- `data-pipeline/scripts/run_sweep.py` — New: CLI harness loading YAML/JSON sweep configs, running evaluate_aptness.evaluate() per variation with fresh sqlite3 connection, capturing per-variation failures into status/error, writing structured JSON with provenance + ranked markdown comparison table with MRR reference
- `data-pipeline/scripts/test_run_sweep.py` — New: 13 tests covering ranked ordering, markdown shape, failure isolation, MRR reference (nested+flat shapes, present+absent), fail-fast on missing inputs, per-variation connection isolation, config loading edge cases
- `data-pipeline/sweeps/baseline_v2.yaml` — New: committed 3-variation baseline sweep config (jaccard_salience, jaccard_raw, cosine_salience at threshold_percentile=95) with header comment linking to slice goal and S01 separation_score anchor
- `data-pipeline/sweeps/README.md` — New: how to add/run sweeps; artefact-policy boundary (config committed, output gitignored)
- `.gitignore` — Narrowly added data-pipeline/output/sweep_*.json and sweep_*.md (existing tracked eval JSONs unaffected)

## UAT


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

## Code review

---
slice: S02
parent: M001-yywgwj
verdict: APPROVE
reviewed_at: 2026-05-03T00:35:00Z
review_loop: code-review-loop (round-robin)
reviewers: [superpowers, pr-review-toolkit, ux-designer]
iterations: 11
final_sha: 76b7c4d8
range_under_review: d8433635..HEAD
---

# S02 Code Review — APPROVE

## Slice scope

**S02 — Pluggable scoring + sweep harness over `evaluate_aptness`.**

The slice introduces:
- A pluggable scoring registry (`SCORING_FNS`) on `evaluate_aptness.py`, exposed via `--scoring` CLI flag (`choices=sorted(SCORING_FNS)`).
- A new sweep harness `run_sweep.py` that runs `evaluate_aptness.evaluate()` once per variation in a YAML/JSON config and emits a structured JSON result + ranked markdown comparison table.
- Per-variation failure isolation (a bad config row does not abort the rest of the sweep).
- Provenance block (schema_version, git_commit, ISO timestamp, all input file paths) on every JSON output.
- Optional MRR reference column populated from the existing `eval_baseline_v2.json`.
- Strict allow-list validation of sweep configs (typo'd keys rejected at the boundary, not silently defaulted).
- Exit-code escalation: 0 = all-ok, 1 = partial failure, 2 = all-failed.
- Operator README under `data-pipeline/sweeps/` with prerequisites, run instructions, exit-code semantics, and troubleshooting.
- First sweep config `data-pipeline/sweeps/baseline_v2.yaml`.
- `data-pipeline/CLAUDE.md` updated to document `run_sweep.py` as the 5th primary pipeline operation.

## Files reviewed

- `data-pipeline/scripts/evaluate_aptness.py` (refactor for pluggable scoring)
- `data-pipeline/scripts/test_evaluate_aptness.py` (registry coverage)
- `data-pipeline/scripts/run_sweep.py` (NEW — sweep harness)
- `data-pipeline/scripts/test_run_sweep.py` (NEW)
- `data-pipeline/sweeps/baseline_v2.yaml` (NEW — first sweep config)
- `data-pipeline/sweeps/README.md` (NEW)
- `data-pipeline/CLAUDE.md` (doc update)

User-facing surfaces touched: NONE in the browser sense. Operator-facing CLI/README/markdown report only.

## Loop summary

11 iterations, 3-reviewer round-robin (`superpowers` → `pr-review-toolkit` → `ux-designer`).

| Iter | Reviewer | Items | Outcome |
|------|----------|-------|---------|
| 1 | superpowers | 0 | CLEAN |
| 2 | pr-review-toolkit | 6 | 5 fix commits (3 Important + 3 Low; 2 skipped with rationale) |
| 3 | ux-designer | 12 | 3 fix commits (3 Important + 7 Low; 2 skipped with rationale) |
| 4 | superpowers | 2 | 2 fix commits (1 Low + 1 Cosmetic) |
| 5 | pr-review-toolkit | 6 | 4 fix commits (1 Important + 3 Low + 2 Cosmetic — combined) |
| 6 | ux-designer | 1 | 1 fix commit (1 Low) |
| 7 | superpowers | 1 | 1 fix commit (1 Low) |
| 8 | pr-review-toolkit | 1 | 1 fix commit (1 Low) |
| 9 | ux-designer | 0 | CLEAN |
| 10 | superpowers | 0 | CLEAN |
| 11 | pr-review-toolkit | 0 | CLEAN — **HALT** |

**Halt path:** ux-designer (9) → superpowers (10) → pr-review-toolkit (11) — three consecutive clean reviewer passes after the last fix at `76b7c4d8`.

## Findings catalogue (resolved)

### Important (7)

| ID | File | Iter | Fix SHA |
|----|------|------|---------|
| `main-exits-0-on-all-failed` | `run_sweep.py:347-389` | 2 | `aa94e53d` |
| `variation-result-shape-untyped-union` | `run_sweep.py:131-205` | 2 | `2b411ca5` |
| `sweep-config-no-typed-schema` | `run_sweep.py:62-99,210-241` | 2 | `3e9b706e` |
| `readme-prerequisites-cwd-missing` | `sweeps/README.md` | 3 | `cd046112` |
| `required-key-errors-no-baseline-pointer` | `run_sweep.py` argparse + validator | 3 | `1919a711` |
| `markdown-report-headline-invisible` | `run_sweep.py:render_markdown_report` | 3 | `0d120235` |
| `empty-variations-exits-zero` | `run_sweep.py:603-616` | 5 | `9fb40208` |

### Low (17)

| ID | File | Iter | Fix SHA |
|----|------|------|---------|
| `parse-errors-no-file-context` | `run_sweep.py:62-126` | 2 | `c3c18b8e` |
| `scoringfn-dict-vs-mapping` | `evaluate_aptness.py:103-112` | 2 | `3da7dccd` |
| `variation-name-uniqueness-not-validated` | `run_sweep.py:131-275` | 2 | `3e9b706e` (bundled) |
| `help-no-scoring-formula-list` | argparse | 3 | `1919a711` |
| `failed-row-rendering-inconsistent` | render_markdown_report | 3 | `0d120235` |
| `no-rank-column` | render_markdown_report | 3 | `0d120235` |
| `no-summary-line` | render_markdown_report | 3 | `0d120235` |
| `failures-buried-in-table-cells` | render_markdown_report | 3 | `0d120235` |
| `exit-code-semantics-undocumented` | sweeps/README.md | 3 | `cd046112` |
| `per-variation-failure-undocumented` | sweeps/README.md | 3 | `cd046112` |
| `summary-tail-empty-variations-bug` | `run_sweep.py:457-468` | 4 | `bcd8cee4` |
| `sweepconfig-required-vs-optional` | `run_sweep.py:113` | 5 | `a332418f` |
| `empty-variations-allowed-by-schema` | `run_sweep.py:170` | 5 | `9fb40208` (combined) |
| `variation-name-default-contradicts-validator` | `run_sweep.py:266` | 5 | `b53f6a3d` |
| `error-prefix-casing-inconsistency` | `run_sweep.py` (4 sites) | 6 | `6d9e6db0` |
| `cast-sweepconfig-lying-at-call-site` | `run_sweep.py:128, 362-376` | 7 | `3fb4cce6` |
| `run-one-variation-param-discards-typedicat` | `run_sweep.py:279` | 8 | `76b7c4d8` |

### Cosmetic (3)

| ID | File | Iter | Fix SHA |
|----|------|------|---------|
| `readme-scoring-help-flag-inaccuracy` | `sweeps/README.md:53-54` | 4 | `ffcd1fe3` |
| `stale-module-docstring-error-field` | `run_sweep.py:25-28` | 5 | `7d01add4` |
| `load-sweep-config-return-type-discards-validation` | `run_sweep.py:127` | 5 | `a332418f` (bundled) |

## Findings skipped (with project-rule-grounded rationale)

These were considered and skipped per CLAUDE.md (no speculative defensive validation, trust internal boundaries, DRY/YAGNI):

- **`ScoringFn` return-bound `[0.0, 1.0]` not encoded in the type** (iter 2) — Python lacks refinement types; runtime clamp would mask future bugs.
- **Salience non-negativity at the data boundary** (iter 2) — internal DB boundary populated by trusted upstream pipeline.
- **`--list-scorings` flag for runtime registry discovery** (iter 3) — feature creep; iter-2's allow-list validator already rejects unknown scoring names.
- **Bold the best-by-separation row in the markdown table** (iter 3) — bold-row support is patchy across renderers; Summary line above the table covers the need universally.
- **`SweepResult` envelope as `dict[str, Any]`** (iters 5, 8, 10, 11) — would be speculative TypedDict work to encode an envelope that hasn't surfaced a bug; contained to one module.

## Final code state

- **Type chain end-to-end honest** — validator → `SweepConfig` → `run_sweep` → `_run_one_variation: VariationSpec` → `VariationResult` discriminated union → `render_markdown_report` narrowing on `status`. No widening, no lying casts.
- **Error catalogue uniform** — every `sweep config` validator error is path-prefixed, lowercase, and rejection-class errors all point at `data-pipeline/sweeps/baseline_v2.yaml`.
- **Schema is a fence** — empty variations rejected; missing `db`/`pairs`/`controls` rejected; unknown keys rejected; per-variation `name` required and unique. The `cast(SweepConfig, data)` at `load_sweep_config` return is honest.
- **Failure isolation preserved** — per-variation `except Exception` (with `# noqa: BLE001` and explicit comment) captures `error_type` + `error_message` into the structured `FailedVariationResult` row and emits a WARNING log. Failures aggregate up to the exit-code escalation (1 partial / 2 all-failed) so CI cannot silently green-light a broken sweep.
- **Operator UX skim-readable** — markdown report has a Summary line ("N succeeded, M failed. Best by separation_score: …"), a leading rank column, em-dash placeholders for failed cells, and a Failures appendix only emitted when any variation failed. CLI `--help` lists the scoring registry. Required-key errors point at the canonical example. README has Prerequisites + cwd guidance + Troubleshooting + exit-code semantics.

## Verification

```
source data-pipeline/.venv/bin/activate && python -m pytest data-pipeline/scripts/ -v
# 497 passed, 1 skipped in 51.22s
```

Test growth: 478 (pre-loop) → 497 (post-loop). +19 net new tests across the 11 iterations, primarily TDD red/green drivers for the validator tightening, exit-code escalation, markdown report rework, and tagged-union shape contracts. The single skip is a `pytest.importorskip("yaml")` gate for the YAML-config path; JSON path is unconditionally exercised.

## Verdict

**APPROVE.**

Slice S02 meets all must-haves from the slice plan: pluggable scoring on `evaluate_aptness`, ranked structured JSON + markdown sweep output with provenance, per-variation failure isolation that does not abort the sweep, optional MRR reference column, fail-fast schema validation, and exit-code escalation for CI. The 11-iteration loop drove the type chain to end-to-end honesty (validator-enforced → cast-honest → narrowing-correct), unified the operator-facing error catalogue, and turned the markdown report into a skim-readable artefact with summary-first structure.

No remaining critical or important findings. The four future-work backlog notes (`SweepResult` typing, `per_pair_scores` OOM watch above ~1000 pairs, `ScoringFn` return-bound, salience non-negativity at the DB boundary) are correctly out of scope for this slice and recorded in the iteration log for capture if/when adjacent surfaces change.

Recommended next step: complete S02 (`gsd_complete_slice` or equivalent), then proceed to the next slice in M001-yywgwj's roadmap.

