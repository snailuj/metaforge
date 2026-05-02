---
id: T03
parent: S01
milestone: M002-kitkng
key_files:
  - data-pipeline/scripts/predict_concreteness.py
  - data-pipeline/scripts/test_predict_concreteness.py
key_decisions:
  - Replaced `np.array(vectors[l])` with `vectors[l]` in build_synset_embeddings — FastTextVectors.__getitem__ already returns an ndarray view, so the per-lemma allocation goes away.
  - Switched per-synset mean from `np.mean(list_of_arrays, axis=0)` to `np.mean(np.stack(vecs), axis=0)` for an explicit contiguous 2D buffer (matches the T02 convention in enrich_pipeline).
duration: 
verification_result: passed
completed_at: 2026-05-02T07:30:47.192Z
blocker_discovered: false
---

# T03: refactor: migrate predict_concreteness consumers to FastTextVectors

**refactor: migrate predict_concreteness consumers to FastTextVectors**

## What Happened

Migrated `build_synset_embeddings`, `cmd_shootout`, and `cmd_fill` in `predict_concreteness.py` from `dict[str, tuple[float, ...]]` to `FastTextVectors`. The implementation simplifies as `vectors[lemma]` already returns a numpy row from FastTextVectors, so `np.array(vectors[l])` becomes `vectors[l]` and the mean is now computed via `np.mean(np.stack(vecs), axis=0)` for vectorised aggregation. The CLI `main()` path needed no changes — `load_fasttext_vectors` already returns `FastTextVectors` after T01.

Updated test helpers in `test_predict_concreteness.py`: added an `_ft()` helper that wraps a `{word: tuple-or-array}` mapping into a `FastTextVectors` (4d for tests), converted the module-level `_make_vectors()` to return one, and rewrapped the three inline single-word dicts and the bulk-test helper `_make_cmd_test_db_and_vectors()` to return a `FastTextVectors`. The 4d test dim is preserved — `FastTextVectors` itself doesn't enforce `EMBEDDING_DIM`; that check lives only in `load_fasttext_vectors`.

Note on the prior verification failure (auto-fix attempt 1): the gate's command was `python -m pytest …` invoked without activating the venv, which produced exit code 2 (no pytest on PATH). The actual test suite passes cleanly under `data-pipeline/.venv/bin/python`. No code-level regression — purely an environment issue in the gate harness.

## Verification

Ran `python -m pytest scripts/test_predict_concreteness.py -v` from `data-pipeline/` against the project venv: 19/19 pass. Re-ran `test_enrich_pipeline.py` and `test_utils.py` to confirm no upstream regression: 56/56 pass. Confirmed no `tuple[float` annotations remain in `predict_concreteness.py`.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -m pytest data-pipeline/scripts/test_predict_concreteness.py -v` | 0 | ✅ pass | 37030ms |
| 2 | `python -m pytest data-pipeline/scripts/test_enrich_pipeline.py data-pipeline/scripts/test_utils.py -q` | 0 | ✅ pass | 8880ms |
| 3 | `grep -n 'tuple\[float' data-pipeline/scripts/predict_concreteness.py` | 1 | ✅ pass (no matches) | 50ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `data-pipeline/scripts/predict_concreteness.py`
- `data-pipeline/scripts/test_predict_concreteness.py`
