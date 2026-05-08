---
id: T01
parent: S02
milestone: M001-yywgwj
key_files:
  - data-pipeline/scripts/evaluate_aptness.py
  - data-pipeline/scripts/test_evaluate_aptness.py
key_decisions:
  - Registry keys are lowercase snake_case to match Python convention and downstream YAML sweep configs
  - cosine_salience zero-pads cluster_ids missing from either side (standard sparse-cosine convention)
  - Unknown scoring names raise ValueError in evaluate() AND argparse rejects via choices=sorted(SCORING_FNS) — defence in depth so library callers and CLI users both get fail-fast behaviour
  - score_pair() default kwarg is _jaccard_salience callable (not the registry string) — keeps call sites that bypass evaluate() backwards-compatible without forcing them through registry lookup
duration: 
verification_result: passed
completed_at: 2026-05-02T15:00:57.643Z
blocker_discovered: false
---

# T01: refactor(evaluate_aptness): make scoring formula pluggable via SCORING_FNS registry with --scoring CLI flag

**refactor(evaluate_aptness): make scoring formula pluggable via SCORING_FNS registry with --scoring CLI flag**

## What Happened

Refactored `evaluate_aptness.py` to select the scoring function via a named registry rather than hard-coding salience-weighted Jaccard. Added the `SCORING_FNS` dict with three registered formulas — `jaccard_salience` (the historic default, extracted from the previous inline implementation in `score_pair`), `jaccard_raw` (unweighted set-Jaccard control), and `cosine_salience` (cosine over salience vectors, zero-padded by cluster_id). All three share the `(pa: dict[int,float], pb: dict[int,float]) -> float` signature defined by the new `ScoringFn` type alias.

Threaded a `scoring_fn` parameter through `score_pair()` and `_score_cohort()` (default `_jaccard_salience` to keep call sites that omit it backwards-compatible). `evaluate()` now takes a `scoring: str` kwarg, looks the callable up in `SCORING_FNS`, and raises `ValueError` listing registered options if the name is unknown — fail-fast behaviour so a sweep-config typo does not silently fall back to the default. The chosen scoring name is recorded in `result["config"]["scoring"]` alongside the existing threshold/percentile fields.

Added a `--scoring NAME` CLI flag (default `jaccard_salience`, `choices=sorted(SCORING_FNS)`) and updated the stderr eval banner to display the active scoring name. Module docstring expanded to document each formula and the snake_case / zero-padding conventions.

Crucially, the `PairScore` status semantics are unchanged: `score_pair` still resolves synsets first, then checks for curated properties, and only invokes the scoring function when both sides are populated — so `unresolved` and `no_properties` statuses are decided before any formula runs. A formula returning 0.0 (no overlap, orthogonal vectors) yields `status="scored", score=0.0`, distinct from a coverage gap. A regression-style test (`test_score_pair_status_unchanged_across_scoring_formulas`) asserts this invariant across all three registered formulas.

Test additions cover the slice plan's required cases: per-formula focused tests on known-overlap, no-overlap, and salience-asymmetric vector pairs (raw Jaccard's invariance to salience and cosine's invariance to magnitude scaling are both verified with crafted inputs); a registry-membership test guarding the contract with downstream sweep configs; `evaluate()` tests for default, override, and unknown-name behaviour; and two CLI dispatch tests using `monkeypatch` to stub `sqlite3.connect` with the in-memory fixture and `sys.argv` with `--scoring jaccard_raw --output …`. The CLI rejection test confirms argparse `choices=` rejects unregistered names before any DB work runs. Test count grew from 21 to 41, all green.

End-to-end verification ran the canonical command (`--scoring jaccard_raw` against `lexicon_v2.db`) and the resulting JSON's `config.scoring` field reads `"jaccard_raw"`, separation_score is -0.0130 on 232 apt + 317 inapt — different from the historic salience-weighted baseline as expected, providing live evidence that the formula swap actually changes the metric (not just the label).

No deviations from the task plan. The salience-weighted Jaccard inline body in `score_pair` was lifted verbatim into `_jaccard_salience` so existing behaviour is byte-identical when scoring defaults to `jaccard_salience` — confirmed by `test_score_pair_default_scoring_matches_jaccard_salience`.

## Verification

Ran the slice's stated verification chain: `pytest data-pipeline/scripts/test_evaluate_aptness.py -v` (41 passed, exit 0); `python data-pipeline/scripts/evaluate_aptness.py --scoring jaccard_raw --db data-pipeline/output/lexicon_v2.db --output /tmp/aptness_jaccard_raw.json` (exit 0, produced 284KB JSON with 232 apt + 317 inapt pair scores); `grep -q '"scoring":' /tmp/aptness_jaccard_raw.json` (exit 0, field present in config block). Programmatic JSON inspection confirmed `config.scoring == "jaccard_raw"`. Backwards-compat verified: existing 21 tests still pass unmodified, default behaviour byte-identical to the previous salience-weighted Jaccard implementation.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `source .venv/bin/activate && python -m pytest data-pipeline/scripts/test_evaluate_aptness.py -v` | 0 | ✅ pass — 41/41 tests green (was 21 before this task) | 590ms |
| 2 | `python data-pipeline/scripts/evaluate_aptness.py --scoring jaccard_raw --db data-pipeline/output/lexicon_v2.db --output /tmp/aptness_jaccard_raw.json` | 0 | ✅ pass — produced 284118-byte JSON with config.scoring='jaccard_raw', n_apt=232, n_inapt=317, separation_score=-0.0130 | 45000ms |
| 3 | `grep -q '"scoring":' /tmp/aptness_jaccard_raw.json` | 0 | ✅ pass — scoring field present in output config block | 5ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `data-pipeline/scripts/evaluate_aptness.py`
- `data-pipeline/scripts/test_evaluate_aptness.py`
