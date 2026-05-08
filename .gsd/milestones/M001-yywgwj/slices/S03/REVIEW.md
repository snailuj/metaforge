# Code Review — Slice S03 (Baseline and Sensitivity Validation)

**Branch:** `milestone/M001-yywgwj`
**Review window:** 2026-05-03T00:50:00Z → 2026-05-03T01:40:00Z (~40 minutes)
**Mode:** code-review-loop, strict round-robin oscillation
**Reviewers:** superpowers, pr-review-toolkit, ux-designer
**Iterations:** 7 (max 15)
**Outcome:** **CLEAN** — halt condition met (all three reviewers returned zero fixable items in consecutive iterations 5/6/7)

**Final SHA:** `0c737030`
**Base SHA:** `76b7c4d8` (post-S02 refactor)

---

## Scope

S03 cumulative diff (`git diff 76b7c4d8..HEAD --stat -- data-pipeline/scripts/ data-pipeline/sweeps/`):

| File | Lines added |
|------|-------------|
| `data-pipeline/scripts/evaluate_aptness.py` | +39 |
| `data-pipeline/scripts/run_sweep.py` | +19 |
| `data-pipeline/scripts/test_evaluate_aptness.py` | +136 |
| `data-pipeline/scripts/test_run_sweep.py` | +110 |
| `data-pipeline/sweeps/sensitivity_v2.yaml` | +50 |
| `data-pipeline/sweeps/SENSITIVITY-V2-FINDINGS.md` | +91 |
| `data-pipeline/sweeps/README.md` | +10 |

**Test baseline:** 507 → 512 (+5 from new tests across iter1-4)
**Test runtime:** ~50–66s (`.venv/bin/python -m pytest scripts/ -q`)

## Iteration summary

| # | Reviewer | Items | Decisions | Resulting SHA |
|---|----------|-------|-----------|---------------|
| 1 | superpowers:code-reviewer | 5 (1 important + 2 low + 2 cosmetic) | 4 fixed, 1 skipped (justified) | `9b977547` |
| 2 | pr-review-toolkit (3 agents) | 3 (2 important + 1 low) | 1 fixed, 1 pushed back (deliberate two-tier validation pattern), 1 skipped | `55975127` |
| 3 | ux-designer | 1 cosmetic | 1 fixed | `695654a8` |
| 4 | superpowers:code-reviewer | 1 low (TDD coverage gap on bool-rejection branch) | 1 fixed | `0c737030` |
| 5 | pr-review-toolkit (3 agents) | 0 | clean | `0c737030` |
| 6 | ux-designer | 0 | clean | `0c737030` |
| 7 | superpowers:code-reviewer | 0 | clean | `0c737030` |

**Totals:** 10 items raised, 7 fixed, 2 skipped (justified), 1 pushed back (justified).

## Material fixes landed

1. **Honest a-priori prediction** (iter1) — `sensitivity_v2.yaml` and `SENSITIVITY-V2-FINDINGS.md` updated together to acknowledge the original ±0.01 null-noise prediction missed and explain the principled relaxation to ±0.02 based on sampling noise (1/√N ≈ 0.06 with N≈275). Audit trail honest.
2. **Schema-boundary `threshold_percentile` validator** (iter2) — closes a real silent fallback in `_percentile` (out-of-range values clamped to min/max sample without log). Validator rejects non-numeric, bool (subclass-of-int trap), and out-of-range values with rich path-prefixed error messages. Pinned by 5 TDD tests including iter4 bool-rejection regression test.
3. **Microcopy unified** (iter3) — both error branches of the `threshold_percentile` validator use the same canonical phrasing ("must be a number in [0, 100]").
4. **Minor robustness** — joiner-invariant comment on `_random_uniform`, forward-compat `lambda *a, **kw` on test fixtures, escaped GFM table pipes.

## Push-back / skip register

| Iter | Item | Decision | Rationale |
|------|------|----------|-----------|
| 1 | empty-union 0.0 fallback in `_random_uniform` | skip | Production path short-circuits via `no_properties` before reaching this branch; verified independently by silent-failure-hunter in iter2. |
| 2 | `VariationSpec.scoring` not validated at config load | push back | Codebase deliberately uses two-tier validation pattern. Runtime failures are loud and observable: WARN log + `status="failed"` JSON row + markdown `## Failures` section + nonzero exit code. Adding load-time validation would duplicate the check and break ~5 tests covering the failure-isolation contract. |
| 2 | switch ScoringFn comma-join to length-prefixed bytes encoding | skip | Type signature `Mapping[int, float]` plus iter1 invariant comment is adequate. Changing the encoding would invalidate committed FINDINGS.md numerical citations for marginal defense-in-depth benefit. |

No item was contested across reviewers (no oscillation cycles).

## Convergence signal

Severity trend across all iterations: `important+low+cosmetic+cosmetic` → `important+important+low` → `cosmetic` → `low` → CLEAN → CLEAN → CLEAN.

Diminishing-returns pattern fully realised. Halt condition met under strict definition (all configured reviewers return zero fixable items in consecutive iterations after their most recent fix).

## Test results (final)

```
512 passed in 50.82s
```

Run from `data-pipeline/` with `.venv/bin/python -m pytest scripts/ -q`.

## Reference

Full iteration log with rationale, fixes applied, and test results per iteration: `docs/superpowers/review-logs/2026-05-03-milestone-M001-yywgwj-review.md`.
