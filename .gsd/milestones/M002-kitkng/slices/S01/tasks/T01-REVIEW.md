---
task: M002-kitkng/S01/T01
verdict: APPROVE
reviewed_at: 2026-05-02T07:17:00Z
scope: task-level (critical/high only)
---

# T01 Code Review — APPROVE

## Scope

Reviewed only the code changes in commit `7470b169` for `data-pipeline/scripts/utils.py` and `data-pipeline/scripts/test_utils.py`. Filtered for critical/high severity (crash bugs, data loss, security, missing boundary error handling, broken API contracts). Style/cosmetic deferred to slice-level loop.

## Findings

**Zero critical or high-severity issues.**

### Notes (non-blocking, informational)

- **API contract change is intentional and scoped.** `load_fasttext_vectors()` return type changes from `dict[str, tuple[float, ...]]` to `FastTextVectors`. The task plan and slice plan explicitly schedule T02 (predict_concreteness) and T03 (enrich_pipeline) to migrate consumers. Not a regression in T01's scope.
- **`FastTextVectors.__getitem__` returns a matrix view, not a copy.** This is documented in both the docstring (`utils.py:73-75`) and the SUMMARY's `key_decisions`. Callers must treat the row as read-only. Acceptable given the closed callsite set (T02/T03 will be reviewed when they land).
- **Pre-allocation by header dim.** `np.empty((num_words, dim), dtype=np.float32)` trusts the file header. If the header understates the row count, `matrix[next_idx] = row` will IndexError on overflow — but this is a malformed-file scenario, the FastText format specifies header authority, and the existing dim-mismatch ValueError already gates malformed headers. No fix required for current input contract.

## Verification

Ran the verification gates from the task plan:

| # | Command | Exit | Verdict |
|---|---------|------|---------|
| 1 | `python -m pytest data-pipeline/scripts/test_utils.py -v` | 0 | 20/20 passed (210ms) |
| 2 | `grep -r 'tuple\[float' data-pipeline/scripts/utils.py \| wc -l` | 0 | returns 0 ✓ |

Both gates green. Tests cover container `__contains__` / `__getitem__` / `.matrix` shape / `.dim` / `__len__`, loader return type, path-cached identity, malformed-line skip, and dim-mismatch ValueError.

## Verdict

**APPROVE** — task is ready to advance to T02.
