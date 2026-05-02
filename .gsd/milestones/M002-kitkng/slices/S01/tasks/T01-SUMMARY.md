---
id: T01
parent: S01
milestone: M002-kitkng
key_files:
  - data-pipeline/scripts/utils.py
  - data-pipeline/scripts/test_utils.py
key_decisions:
  - FastTextVectors.__getitem__ returns a numpy row view (not a copy) — callers must treat it as read-only; matches dict[word] ergonomics with zero allocation overhead.
  - Pre-allocate a (num_words, dim) float32 buffer up-front and trim with .copy() if malformed rows are skipped, instead of np.vstack/append (avoids O(n) regrowth).
  - Parse rows via np.array(values, dtype=np.float32) directly from the split string list — avoids the intermediate Python tuple of float64s that drove the old representation's RSS cost.
duration: 
verification_result: passed
completed_at: 2026-05-02T07:15:35.390Z
blocker_discovered: false
---

# T01: refactor: store FastText vectors as numpy float32 matrix + word→idx dict

**refactor: store FastText vectors as numpy float32 matrix + word→idx dict**

## What Happened

Introduced a `FastTextVectors` dataclass in `data-pipeline/scripts/utils.py` holding a contiguous `np.ndarray` (float32, shape n × 300) plus a `word_to_idx: dict[str, int]`. Implemented `__contains__`, `__getitem__` (returns the matrix row directly — a view, treat as read-only), `__len__`, and a `.dim` property so the new container is a drop-in for the prior `dict[str, tuple[float, ...]]` access pattern.

Refactored `load_fasttext_vectors()` to parse each line straight into a float32 numpy row and write it into a pre-allocated matrix sized to the header. Skipped/malformed rows still drop cleanly; the final matrix is trimmed with `matrix[:n].copy()` so `matrix.shape[0] == len(word_to_idx)` and the unused tail is released. Updated `_fasttext_cache` annotation to `dict[str, FastTextVectors]`. The error path (header dim ≠ EMBEDDING_DIM) and the cache-by-path semantics are preserved.

TDD discipline: wrote 11 new tests in `test_utils.py` first (container `__contains__`/`__getitem__`/shape/dim/len plus loader return type, caching, malformed-line handling, and dim-mismatch ValueError) and watched them fail with `ImportError: cannot import name 'FastTextVectors'`. Then added the dataclass + numpy-rewrite of the loader and watched all 20 tests in the module turn green. Used `monkeypatch` to reset the module-level `_fasttext_cache` between tests so they remain hermetic.

Note: the return type of `load_fasttext_vectors()` has changed from `dict` to `FastTextVectors`, which will surface failures in `test_enrich_pipeline.py` and `test_predict_concreteness.py` until T02 and T03 migrate those consumers — this is the planned slice trajectory and not a regression in T01's scope.

Captured a reusable pattern as MEM014 for future loader work: pre-allocate contiguous float32 matrix from header, parse rows directly via np.array(values, dtype=np.float32), trim with .copy() when rows are dropped.

## Verification

Ran `python -m pytest data-pipeline/scripts/test_utils.py -v` — 20/20 passed (9 pre-existing + 11 new container/loader tests). Ran `grep -r 'tuple\[float' data-pipeline/scripts/utils.py | wc -l` — returns 0 (initial result was 1; removed the stale literal `tuple[float, ...]` reference from the FastTextVectors docstring). Both gates from the task plan's Verify clause are green.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -m pytest data-pipeline/scripts/test_utils.py -v` | 0 | ✅ pass | 210ms |
| 2 | `grep -r 'tuple\[float' data-pipeline/scripts/utils.py | wc -l` | 0 | ✅ pass (returns 0) | 5ms |

## Deviations

Removed a literal `tuple[float, ...]` reference from the FastTextVectors docstring (replaced with prose) so the second verification grep returns 0. The class is functionally unchanged; only the docstring wording was adjusted.

## Known Issues

test_enrich_pipeline.py and test_predict_concreteness.py will fail on the slice's full-suite run until T02 and T03 migrate their consumers — this is the planned trajectory and explicitly scoped to the next two tasks.

## Files Created/Modified

- `data-pipeline/scripts/utils.py`
- `data-pipeline/scripts/test_utils.py`
