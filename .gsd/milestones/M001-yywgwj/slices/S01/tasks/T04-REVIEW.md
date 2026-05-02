---
task: T04
verdict: APPROVE
reviewed_at: 2026-05-02T13:33:00Z
critical_issues: 0
high_issues: 0
---

# T04 Code Review

## Verdict: APPROVE

No critical or high-severity issues found in the T04 changes
(`data-pipeline/scripts/evaluate_aptness.py`,
`data-pipeline/scripts/test_evaluate_aptness.py`).

## Audit Findings

| Dimension | Result | Evidence |
|-----------|--------|----------|
| SQL injection | ✅ Safe | All queries use `?` placeholders (`evaluate_aptness.py:58-72,78-82`) |
| Resource leaks | ✅ Safe | `conn.close()` in `try/finally` (`:344-354`); `with open(...)` for all file IO (`:123,140,391`) |
| Error handling at boundaries | ✅ Safe | `load_apt_pairs` validates JSON shape (`:125-127`); malformed JSONL fails loudly via `json.loads` — correct for a CLI batch tool |
| API contract | ✅ Stable | End-to-end test asserts JSON shape (`test_evaluate_aptness.py:223-235`); 17/17 unit tests green |
| Math correctness | ✅ Sound | Salience-weighted Jaccard `sum(min)/sum(max)` over union; symmetry verified by test |
| OOM / scaling | ✅ Bounded | Inputs ~1.7K rows; JSONL streamed line-by-line; `_get_properties` uses indexed lookup |
| Edge cases | ✅ Covered | Empty cohorts, unresolved lemmas, percentile bounds, missing inapt — all tested |

## Verification

- Test suite: `.venv/bin/python -m pytest data-pipeline/scripts/test_evaluate_aptness.py -v` → **17/17 passed in 0.20s**.
- Real-data run already verified by T04 itself: `separation_score = 0.0103` (>0 bar cleared).

## Notes (non-blocking)

- The known shortfall on the slice-level `separation_score >= 0.3` target is documented in the task summary as deferred to S02 tuning work — not a code defect.
- File `open()` calls don't pin `encoding="utf-8"`. Defaults are platform-dependent but irrelevant here (data is ASCII English lemmas). Cosmetic only — handled at slice review.
