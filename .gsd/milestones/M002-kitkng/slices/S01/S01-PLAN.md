# S01: FastText numpy migration

**Goal:** Replace Python dict[str, tuple[float, ...]] FastText representation with numpy float32 matrix + word-to-index dict, dropping peak memory from ~11 GB to ~1.2 GB. All existing tests pass, no tuple-of-floats representation remains.
**Demo:** Pipeline loads FastText vectors in ~1.2 GB RSS instead of ~11 GB. All tests pass.

## Must-Haves

- load_fasttext_vectors returns a FastTextVectors container with numpy float32 matrix (shape: n_words × 300) and word_to_idx dict
- All consumers in enrich_pipeline.py and predict_concreteness.py updated to use the new type
- struct.pack output from numpy path matches tuple path within float32 tolerance (1e-7)
- All existing data-pipeline tests pass
- No dict[str, tuple[float, ...]] signatures remain in the codebase

## Proof Level

- This slice proves: Not provided.

## Integration Closure

Not provided.

## Verification

- Not provided.

## Tasks

- [x] **T01: Define FastTextVectors container and refactor loader** `est:45min`
  Create a FastTextVectors dataclass in utils.py holding a numpy float32 matrix (n × 300) and a word_to_idx dict[str, int]. Implement __contains__ and __getitem__ for ergonomic access. Refactor load_fasttext_vectors() to parse directly into numpy rows instead of Python tuples. Update _fasttext_cache type. TDD: write tests for the new container's __contains__, __getitem__, .matrix shape, and .dim properties first.
  - Files: `data-pipeline/scripts/utils.py`, `data-pipeline/scripts/test_utils.py`
  - Verify: python -m pytest data-pipeline/scripts/test_utils.py -v && grep -r 'tuple\[float' data-pipeline/scripts/utils.py | wc -l returns 0

- [x] **T02: Migrate enrich_pipeline.py consumers to FastTextVectors** `est:30min`
  Update _get_embedding(), _get_compound_embedding(), curate_properties(), and store_lemma_embeddings() to accept FastTextVectors instead of dict[str, tuple[float, ...]]. Key changes: _get_embedding uses vectors[word] which returns a numpy row — struct.pack needs *row.tolist() or row.tobytes(). _get_compound_embedding averages numpy rows directly instead of element-wise tuple math. store_lemma_embeddings packs from numpy row. Update test helpers (_make_vectors, _make_vec) in test_enrich_pipeline.py to return FastTextVectors. TDD: update tests first, watch them fail, then fix the production code.
  - Files: `data-pipeline/scripts/enrich_pipeline.py`, `data-pipeline/scripts/test_enrich_pipeline.py`
  - Verify: python -m pytest data-pipeline/scripts/test_enrich_pipeline.py -v

- [x] **T03: Migrate predict_concreteness.py consumers to FastTextVectors** `est:20min`
  Update build_synset_embeddings(), cmd_shootout(), and cmd_fill() to accept FastTextVectors. build_synset_embeddings already converts to np.array — with FastTextVectors it can index directly into the matrix (vectors[lemma] already returns ndarray). Update _make_vectors() in test_predict_concreteness.py to return a FastTextVectors. The main() CLI path also loads vectors via load_fasttext_vectors — this just works since the return type changed in T01. TDD: update test helper first, run tests red, then fix production code.
  - Files: `data-pipeline/scripts/predict_concreteness.py`, `data-pipeline/scripts/test_predict_concreteness.py`
  - Verify: python -m pytest data-pipeline/scripts/test_predict_concreteness.py -v

- [x] **T04: Float32 precision regression test and full suite verification** `est:15min`
  Add a focused test in test_utils.py that verifies struct.pack output from the numpy float32 path matches the old tuple-of-float64 path within float32 tolerance (1e-7 relative). This catches any silent precision drift that could shift similarity thresholds. Then run the complete data-pipeline test suite to verify no regressions across all 24 test files.
  - Files: `data-pipeline/scripts/test_utils.py`
  - Verify: cd data-pipeline && ../.venv/bin/python -m pytest scripts/ -v --tb=short

## Files Likely Touched

- data-pipeline/scripts/utils.py
- data-pipeline/scripts/test_utils.py
- data-pipeline/scripts/enrich_pipeline.py
- data-pipeline/scripts/test_enrich_pipeline.py
- data-pipeline/scripts/predict_concreteness.py
- data-pipeline/scripts/test_predict_concreteness.py
