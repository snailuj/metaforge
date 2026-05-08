---
task: T02
parent: S02
milestone: M001-yywgwj
verdict: APPROVE
reviewed_at: 2026-05-02T22:10:00Z
scope: critical-and-high-only
note: Written retroactively after the original code-review loop timed out. The slice was already DB-complete; this review closes the missing per-task review artefact for traceability.
---

# T02 Code Review — APPROVE

## Scope

Reviewed code changes from commit `a2376e90` for critical and high-severity
issues only (crash bugs, data loss, security vulnerabilities, missing
external-boundary error handling, broken API contracts). Cosmetic and
low-severity issues deferred to slice-level review.

## Files reviewed

- `data-pipeline/scripts/run_sweep.py` (commit a2376e90, +389 lines)
- `data-pipeline/scripts/test_run_sweep.py` (commit a2376e90, +310 lines)

## Findings

**None at critical or high severity.**

## Notes considered and cleared

| Concern | Resolution |
| --- | --- |
| Broad `except Exception` in `_run_one_variation` could mask genuine bugs | Required by slice must-have for per-variation failure isolation. Documented with `# noqa: BLE001` and an inline comment. The exception type+message is captured in the result dict and a WARNING log is emitted, so failures are visible — they're isolated, not silenced. |
| DB connection leak on partial failure | `conn = sqlite3.connect(...)` lives inside the inner `try`, with `conn.close()` in `finally`. Outer `try/except` catches anything before the connect succeeds (so no leak path). |
| `evaluate_aptness.evaluate()` raises `ValueError` for unknown scoring — does the harness catch it? | Yes — caught by the broad `except` block; the variation's row records `status='failed'` with the ValueError message. Test `test_unknown_scoring_marks_variation_failed_without_aborting` exercises this end-to-end across 3 variations. |
| Per-variation isolation — could a connection-level error in one variation poison the next? | No. Each variation opens its own `sqlite3.connect(db_path)`, closed in its own `finally`. Test `test_per_variation_isolation_uses_fresh_connection` verifies this by tracking connect calls. |
| Sort key for ranked report could crash on missing `separation_score` | `_rank_key` uses `.get('separation_score', 0.0)` for ok rows, and the failed branch returns `(1, 0.0)` without touching the field. Failed rows pin to the bottom via the tuple's first element — verified by test. |
| MRR reference shape divergence | Loader accepts both `{"mrr": {"value": float}}` (current `eval_baseline_v2.json` shape) and flat `{"mrr": float}`. Both cases tested. Missing path raises `FileNotFoundError` (fail-fast on typo). |
| Config schema validation | `load_sweep_config` validates: file exists, extension is supported, top-level is a mapping, `variations` is a present list. Each guard has a focused test. |
| Required inputs validation in `run_sweep` | Validates `db`, `pairs`, `controls` are set AND exist on disk before running any variation — saves wasted compute on a typo. Test `test_sweep_validates_required_inputs` exercises this. |
| Provenance block correctness | JSON output carries `schema_version=1`, ISO `timestamp`, `git_commit`, `config_path`, `db_path`, `pairs_file`, `controls_file`, `mrr_reference_path`, `mrr_reference_value`, sweep `duration_ms`. Test asserts schema_version + git_commit + timestamp shape. |
| YAML dependency — would importing yaml at module load break pipelines that don't have it? | YAML import is lazy (inside `load_sweep_config`, only when `.yaml`/`.yml` extension is detected). JSON path works without PyYAML. Clear `ImportError` with install hint if YAML is requested but unavailable. |
| Logging — secrets or PII? | Logs only config name, scoring formula name, db path, separation/aptness floats, n_apt/n_inapt, duration. No credentials, no row content. |
| SQL injection / path traversal | `sqlite3.connect(db_path)` — path comes from config, opened directly as a filesystem path. No SQL string interpolation. No shell-out. Path is validated via `Path.is_file()` before opening. |
| Output path safety | `output_path.parent.mkdir(parents=True, exist_ok=True)` — creates parent dirs if needed. Permission errors propagate to the operator. Fine. |
| `time.perf_counter()` correctness | Monotonic, safe across time-of-day changes. Used only for relative durations. |
| Testing — coverage of must-haves | All slice plan must-haves have at least one test: ranking by separation_score DESC (`test_two_variation_sweep_ranks_by_separation_score`), failure isolation (`test_unknown_scoring_marks_variation_failed_without_aborting`), MRR reference column (`test_mrr_reference_populates_report_column`), fail-fast inputs (`test_sweep_validates_required_inputs`), per-variation connection isolation (`test_per_variation_isolation_uses_fresh_connection`). |

## Verification

```
source .venv/bin/activate && python -m pytest data-pipeline/scripts/test_run_sweep.py -v
# 13 passed in 0.34s
```

Full pipeline suite (rerun for the original task verification gate) was
469/469 green per `T02-SUMMARY.md`. No regressions to T01's
`evaluate_aptness` registry.

## Verdict

APPROVE. The harness meets all slice S02 must-haves: ranked structured
JSON output with provenance, markdown comparison table sorted by
separation_score DESC with failed rows pinned to the bottom, per-variation
failure isolation that does not abort the sweep, optional MRR reference
column populated from the existing baseline JSON shape, and fail-fast
validation of required inputs before any work runs. Test coverage is
proportional to the surface area, and the broad-catch in
`_run_one_variation` is justified, documented, and exercised.
