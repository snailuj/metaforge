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
