---
id: T02
parent: S02
milestone: M001-yywgwj
key_files:
  - data-pipeline/scripts/run_sweep.py
  - data-pipeline/scripts/test_run_sweep.py
key_decisions:
  - YAML config support is lazy-imported and gracefully degrades with an install hint, because PyYAML is NOT currently a pipeline dep (verified via grep of requirements.txt + scripts/) — adding it just for sweep configs would expand the runtime surface for one feature; JSON works out of the box and YAML lights up if a user has it.
  - Each variation opens a fresh sqlite3 connection (rather than sharing one across the sweep) so per-variation failures cannot leak transaction state and so a connection-level error in one variation cannot poison subsequent ones — this matches the slice's idempotency/failure-isolation must-have.
  - MRR reference loader accepts both nested `{mrr: {value: ...}}` (current eval_baseline_v2.json shape) and flat `{mrr: float}` for forward compatibility — single-source-of-truth shape can evolve without breaking sweep configs.
duration: 
verification_result: passed
completed_at: 2026-05-02T15:11:36.177Z
blocker_discovered: false
---

# T02: feat(run_sweep): build sweep harness over evaluate_aptness with ranked JSON+markdown outputs and per-variation failure isolation

**feat(run_sweep): build sweep harness over evaluate_aptness with ranked JSON+markdown outputs and per-variation failure isolation**

## What Happened

Added `data-pipeline/scripts/run_sweep.py` — a CLI harness that loads a YAML or JSON sweep config (extension-detected; YAML import is lazy with a clear install hint, since PyYAML is not currently a pipeline dep) and runs `evaluate_aptness.evaluate()` once per variation. Each variation opens its own SQLite connection so transaction state and DB-level failures cannot leak across variations.

Per-variation failures (unknown scoring name, DB read error, missing inputs) are captured into `status='failed'` + `error` strings rather than aborting — satisfies the slice's idempotency must-have. Successful variations carry `aptness_rate`, `separation_score`, `false_positive_rate`, mean apt/inapt scores, n_apt/n_inapt, threshold, and per-variation duration_ms.

Outputs: a structured JSON via `--output` carrying a provenance block (`schema_version=1`, ISO timestamp, git_commit, config_path, db_path, optional mrr_reference_path/value) and a `variations: [...]` list; plus a markdown report via `--report` (defaults to `<output>.md`) with the contracted columns (`name | scoring | threshold | aptness_rate | separation_score | mean_apt | mean_inapt | n_apt | n_inapt | mrr_ref | status`). Rows are sorted by `separation_score` DESC with failed rows pinned to the bottom via a tuple sort key.

MRR reference resolution accepts both the nested `eval_baseline_v2.json` shape (`{"mrr": {"value": ...}}`) and a flat `{"mrr": float}` shape for forward compatibility. Missing/typo paths fail fast with a `FileNotFoundError`.

Per-variation INFO logs include scoring name, separation_score, aptness_rate, n_apt/n_inapt, and duration_ms; sweep-level start/finish logs include total wall-clock and ok/failed counts. Failed variations log a WARNING with the error.

Tests cover: 2-variation ranked sweep (both ordering and markdown shape), failure isolation (one bad scoring among three variations does not abort, failed row pinned to bottom), MRR reference column population both with and without a reference, fail-fast on missing input paths, per-variation isolation (one DB-connect open per variation), config loading edge cases (missing variations, bad extension, missing file), and both nested + flat MRR reference shapes.

## Verification

Ran `source .venv/bin/activate && python -m pytest data-pipeline/scripts/test_run_sweep.py -v` — 13/13 new tests pass in 0.55s. Then ran the full data-pipeline suite `python -m pytest data-pipeline/scripts/ -v` — 469/469 pass in 90.14s, no regressions to T01's evaluate_aptness changes or any prior pipeline test.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `source .venv/bin/activate && python -m pytest data-pipeline/scripts/test_run_sweep.py -v` | 0 | ✅ pass | 550ms |
| 2 | `source .venv/bin/activate && python -m pytest data-pipeline/scripts/ -v 2>&1 | tail -5` | 0 | ✅ pass | 90140ms |

## Deviations

None of substance. Slice plan suggested YAML-preferred parsing but flagged that I should verify PyYAML is already a dep — it is not, so I kept JSON as the always-available format and made YAML opt-in via lazy import with a clear install hint. This satisfies both the parsing contract and the "do not add a new runtime dep without need" guidance.

## Known Issues

None. The harness has not yet been demoed against the real `lexicon_v2.db` — that's T03's responsibility per the task plan ("Do NOT commit any output files in this task — those happen in T03").

## Files Created/Modified

- `data-pipeline/scripts/run_sweep.py`
- `data-pipeline/scripts/test_run_sweep.py`
