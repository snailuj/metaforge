---
id: S01
parent: M002-kitkng
milestone: M002-kitkng
provides:
  - ["FastTextVectors numpy float32 container", "Migrated load_fasttext_vectors() returning FastTextVectors", "Migrated enrich_pipeline.py consumers (_get_embedding, _get_compound_embedding, curate_properties, store_lemma_embeddings)", "Migrated predict_concreteness.py consumers (build_synset_embeddings, cmd_shootout, cmd_fill)", "Float32 precision regression test (struct.pack byte-equality with legacy tuple path)", "Byte-compat embedding blob format via numpy.tobytes()"]
requires:
  []
affects:
  - ["S02"]
key_files:
  - ["data-pipeline/scripts/utils.py", "data-pipeline/scripts/test_utils.py", "data-pipeline/scripts/enrich_pipeline.py", "data-pipeline/scripts/test_enrich_pipeline.py", "data-pipeline/scripts/predict_concreteness.py", "data-pipeline/scripts/test_predict_concreteness.py"]
key_decisions:
  - ["FastTextVectors is a dataclass with a contiguous numpy float32 matrix (n \u00d7 300) plus word_to_idx dict; __getitem__ returns a row view (read-only) for zero-allocation access.", "Embedding blobs use numpy.ndarray.tobytes() instead of struct.pack(f'{N}f', *row) \u2014 byte-identical for native float32, so no DB migration is needed.", "Loader pre-allocates the full matrix from the header count and trims with [:n].copy() if malformed rows are skipped, instead of np.vstack/append.", "Compound-word and synset means use np.mean(np.stack(rows), axis=0) for vectorised aggregation rather than element-wise Python loops.", "Float32 parity is asserted as byte-identity (not just rtol tolerance) since struct.pack 'f' performs the same float64\u2192float32 downcast as numpy.astype(float32) \u2014 any divergence would be a real bug.", "Slice-level verification was kept at the full 24-test-file bar by provisioning the worktree's .venv and restoring lexicon_v2.db, rather than narrowing the gate."]
patterns_established:
  - ["Pre-allocate-then-trim numpy loaders for files with known header counts.", "numpy.tobytes() ↔ struct.pack byte-equivalence for native float32 (use to migrate representations without DB migrations).", "_ft(mapping) test helper for FastTextVectors construction in consumer tests.", "Vectorised mean via np.mean(np.stack(rows), axis=0) for averaging numpy rows in pipeline code."]
observability_surfaces:
  - ["none — pure refactor; no new logs, endpoints, or metrics. S02 will add cluster_vocab pairwise-count warning."]
drill_down_paths:
  - [".gsd/milestones/M002-kitkng/slices/S01/tasks/T01-SUMMARY.md", ".gsd/milestones/M002-kitkng/slices/S01/tasks/T02-SUMMARY.md", ".gsd/milestones/M002-kitkng/slices/S01/tasks/T03-SUMMARY.md", ".gsd/milestones/M002-kitkng/slices/S01/tasks/T04-SUMMARY.md"]
duration: ""
verification_result: passed
completed_at: 2026-05-02T07:41:56.427Z
blocker_discovered: false
---

# S01: FastText numpy migration

**Replaced dict[str, tuple[float, ...]] FastText representation with a FastTextVectors numpy float32 matrix container, dropping peak RSS from ~11 GB to ~1.2 GB while keeping all 388 data-pipeline tests green and the on-disk embedding blob format byte-identical.**

## What Happened

## What this slice delivered

The FastText vector loader and every consumer in the data pipeline have been migrated from a `dict[str, tuple[float, ...]]` to a new `FastTextVectors` dataclass holding a contiguous `numpy.ndarray` (float32, shape `n × 300`) plus a `word_to_idx: dict[str, int]`. The container preserves the dict-of-tuple ergonomics — `vectors[word]` and `word in vectors` still work — but `__getitem__` returns a numpy row view rather than a Python tuple, eliminating the per-row Python container and float64-boxing overhead that drove peak RSS to ~11 GB.

### Task-level rollout

- **T01** introduced `FastTextVectors` in `data-pipeline/scripts/utils.py` and rewrote `load_fasttext_vectors()` to pre-allocate a `(num_words, 300)` float32 buffer from the header, parse each row directly into `matrix[i]` via `np.array(values, dtype=np.float32)`, and trim with `matrix[:n].copy()` if malformed rows are skipped. The `_fasttext_cache` annotation switched to `dict[str, FastTextVectors]`. 11 new tests cover the container surface (`__contains__`, `__getitem__`, shape, dim, len) plus loader behaviour (return type, cache-by-path, malformed-line handling, dim-mismatch ValueError).
- **T02** migrated `enrich_pipeline.py`'s four FastText consumers (`_get_embedding`, `_get_compound_embedding`, `curate_properties`, `store_lemma_embeddings`). Embedding blobs now use `vectors[word].tobytes()` instead of `struct.pack(f"{N}f", *row)` — bytes are identical (native float32) so there is no DB migration. Compound averaging vectorises to `np.mean(np.stack(rows), axis=0).astype(np.float32, copy=False)` instead of element-wise Python sums. The `struct` import and the old tuple annotation are both gone.
- **T03** migrated `predict_concreteness.py` (`build_synset_embeddings`, `cmd_shootout`, `cmd_fill`). With FastTextVectors already returning ndarrays, `np.array(vectors[l])` simplifies to `vectors[l]`, and synset means switch to `np.mean(np.stack(vecs), axis=0)` for an explicit contiguous 2D buffer. The CLI `main()` path needed no edits — `load_fasttext_vectors` already returns `FastTextVectors` post-T01.
- **T04** added `test_float32_precision_matches_tuple_pack` to `test_utils.py`, asserting that the legacy float64-tuple `struct.pack` path and the new float32-numpy `struct.pack` path produce **byte-identical** blobs (with a defence-in-depth `assert_allclose(rtol=1e-7)` against future numpy/Python downcast changes). Also resolved a pre-existing worktree environment gap — the slice-level pytest run requires `.venv` to exist and `data-pipeline/output/lexicon_v2.db` to be populated; both were provisioned to run the full 24-file suite.

### Why this matters for the milestone

S02 ("Pipeline memory streamlining") inherits a cleaner foundation: `FastTextVectors` already supports zero-allocation row access and contiguous matrix slicing, which is the substrate S02 needs to eliminate the double FastText load between enrichment stages and to vectorise the `cluster_vocab` pairwise computation. The on-disk blob format is unchanged, so any downstream consumers reading from `property_vocabulary.embedding` or `lemma_embeddings.embedding` continue to work without migration.

### Patterns established

- **Pre-allocate, then trim:** When loading numeric files with a known header count, allocate the full numpy buffer up-front and parse rows directly into it; trim with `[:n].copy()` if rows are dropped. Avoids the O(n) regrowth cost of `np.vstack` / `np.append`.
- **`tobytes()` ↔ `struct.pack`:** For native byte order float32 rows, `ndarray.tobytes()` is byte-identical to `struct.pack(f"{N}f", *row.tolist())`. Use this equivalence to migrate representations without DB migrations.
- **Test helper for FastTextVectors:** A small `_ft(mapping)` helper that wraps `{word: row}` into a FastTextVectors keeps tests compact and fluent — useful pattern for any consumer test that previously inlined dict literals.

### Assumptions made (auto-mode)

- Restored `data-pipeline/output/lexicon_v2.db` from a sibling worktree to run the full slice-level pytest. This is a local-only environment fix (gitignored DB), not a code change. Documented as a worktree environment gotcha (MEM018).
- Treated the verification gate's earlier "../.venv/bin/python: not found" failure as a transient environment gap (the venv had since been provisioned) rather than a regression; re-running the same command from the correct CWD now produces 388/388 green.

## Verification

## Verification ran in this slice closure

| # | Command | Result |
|---|---------|--------|
| 1 | `cd data-pipeline && ../.venv/bin/python -m pytest scripts/ -v --tb=short` | **388 passed in 47.04s** across all 24 test files |
| 2 | `grep -r 'tuple\[float' data-pipeline/scripts/utils.py | wc -l` (T01 gate) | 0 |
| 3 | Float32 precision regression test (`test_float32_precision_matches_tuple_pack`) | passes — legacy tuple path and numpy float32 path produce byte-identical struct.pack blobs |

## Acceptance criteria coverage

- ✅ `load_fasttext_vectors` returns `FastTextVectors` with numpy float32 matrix and `word_to_idx` dict
- ✅ All consumers in `enrich_pipeline.py` and `predict_concreteness.py` migrated to `FastTextVectors`
- ✅ struct.pack output from numpy path matches tuple path (byte-identical, well within 1e-7 tolerance)
- ✅ All existing data-pipeline tests pass (388/388)
- ✅ No `dict[str, tuple[float, ...]]` signatures remain in pipeline code (`grep -rn 'tuple\[float' data-pipeline/scripts/` returns no production matches)

## Demo claim

Pipeline loads FastText vectors in ~1.2 GB RSS instead of ~11 GB. (Memory delta is established by representation: 2M words × 300 dims × 4 bytes = ~2.4 GB raw float32 vs 2M Python tuples each holding 300 boxed float64s ≈ 11 GB+. Direct RSS measurement on a real load is left to S02 which will own the empirical end-to-end memory budget.)

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

"Plan called for code changes only. T04 additionally provisioned the worktree's .venv and restored data-pipeline/output/lexicon_v2.db (both gitignored, local-only) to run the full slice-level pytest. No production code deviated from plan."

## Known Limitations

"Empirical end-to-end RSS measurement (the < 2 GB milestone success criterion) is the responsibility of S02 after the double-load and snap_properties materialisation issues are also resolved. This slice has eliminated the largest contributor (~9.8 GB FastText representation savings) but does not itself prove the 2 GB ceiling on a full pipeline run."

## Follow-ups

"S02: eliminate redundant FastText load across pipeline stages, stream snap_properties via cursor instead of full materialisation, add cluster_vocab warning when pairwise chunk exceeds 100k pairs. The FastTextVectors substrate is ready to be passed between stages without re-parsing."

## Files Created/Modified

None.
