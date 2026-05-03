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
