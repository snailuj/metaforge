---
id: T02
parent: S01
milestone: M002-kitkng
key_files:
  - data-pipeline/scripts/enrich_pipeline.py
  - data-pipeline/scripts/test_enrich_pipeline.py
key_decisions:
  - Use numpy.ndarray.tobytes() instead of struct.pack(f'{EMBEDDING_DIM}f', *row) for embedding blobs — bytes are identical (300 × float32 native order) so no DB migration is needed and the new path avoids per-element Python boxing.
  - Vectorise compound-word averaging with np.mean(np.stack(rows), axis=0).astype(float32, copy=False) instead of element-wise Python sum over EMBEDDING_DIM — both more correct under FastTextVectors and meaningfully faster.
  - Test infrastructure: introduce a small _ft(mapping) helper to build FastTextVectors from a {word: row} dict so individual tests can keep their compact inline vector literals.
duration: 
verification_result: passed
completed_at: 2026-05-02T07:25:01.535Z
blocker_discovered: false
---

# T02: refactor: migrate enrich_pipeline FastText consumers to FastTextVectors + numpy bytes

**refactor: migrate enrich_pipeline FastText consumers to FastTextVectors + numpy bytes**

## What Happened

Replaced the four `dict[str, tuple[float, ...]]` consumers in `data-pipeline/scripts/enrich_pipeline.py` with the new `FastTextVectors` container introduced in T01. `_get_embedding` and `store_lemma_embeddings` now write embedding blobs via `vectors[word].tobytes()` instead of `struct.pack(f"{EMBEDDING_DIM}f", *vectors[word])`. The on-disk layout (300 × float32, native byte order) is byte-identical to the prior writer, so existing `lemma_embeddings` / `property_vocabulary.embedding` blobs stay readable.

`_get_compound_embedding` now stacks the in-vocab matrix rows and averages them with `np.mean(np.stack(rows), axis=0).astype(np.float32, copy=False)` instead of running an O(EMBEDDING_DIM) Python comprehension over per-element tuple sums. This is both clearer and considerably faster for the compound/hyphenated property path. `struct` and the `dict[str, tuple[float, ...]]` annotation were removed entirely; `numpy` and `FastTextVectors` are now the imports.

TDD discipline: updated `test_enrich_pipeline.py` first — added a `_ft(mapping)` helper that builds a `FastTextVectors` container from a `{word: row}` dict, switched `_make_vec` to return `np.ndarray(dtype=float32)`, made `_make_vectors()` return `FastTextVectors`, and wrapped every inline `vectors = {...}` literal at the test call sites with `_ft(...)`. Initial run was already green because the old production code happened to duck-type with FastTextVectors (`__contains__` plus iteration over a numpy row works with `*row` unpacking and struct.pack), but the task contract required the type signatures and numpy-native operations regardless. After production migration the suite stayed green at 36/36.

Key decision: byte-compat the embedding blob format by using `numpy.tobytes()` on a contiguous float32 row, which produces the identical layout as `struct.pack(f"{EMBEDDING_DIM}f", *row)` on the same machine — no DB migration needed for downstream consumers (`property_vocabulary.embedding`, `lemma_embeddings.embedding`).

## Verification

Ran `python -m pytest data-pipeline/scripts/test_enrich_pipeline.py -v` — 36/36 passed in 8.71s. Confirmed `grep -c 'tuple\[float' data-pipeline/scripts/enrich_pipeline.py` returns 0 and `grep -n FastTextVectors data-pipeline/scripts/enrich_pipeline.py` shows the new annotation on `_get_embedding`, `_get_compound_embedding`, `curate_properties`, and `store_lemma_embeddings`.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -m pytest data-pipeline/scripts/test_enrich_pipeline.py -v` | 0 | pass | 8710ms |
| 2 | `grep -c 'tuple\[float' data-pipeline/scripts/enrich_pipeline.py` | 1 | pass (0 matches) | 5ms |
| 3 | `grep -n 'FastTextVectors' data-pipeline/scripts/enrich_pipeline.py` | 0 | pass (5 references) | 5ms |

## Deviations

None — plan followed as written. Production code passed the unmodified tests on first run because of duck-typing; migrated annotations and numpy-native operations anyway per the task contract (no `dict[str, tuple[float, ...]]` may remain).

## Known Issues

test_predict_concreteness.py likely still expects a dict-typed vectors argument; T03 will migrate that consumer per the slice trajectory.

## Files Created/Modified

- `data-pipeline/scripts/enrich_pipeline.py`
- `data-pipeline/scripts/test_enrich_pipeline.py`
