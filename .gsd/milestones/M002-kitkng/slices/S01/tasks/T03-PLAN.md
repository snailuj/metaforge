---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T03: Migrate predict_concreteness.py consumers to FastTextVectors

Update build_synset_embeddings(), cmd_shootout(), and cmd_fill() to accept FastTextVectors. build_synset_embeddings already converts to np.array — with FastTextVectors it can index directly into the matrix (vectors[lemma] already returns ndarray). Update _make_vectors() in test_predict_concreteness.py to return a FastTextVectors. The main() CLI path also loads vectors via load_fasttext_vectors — this just works since the return type changed in T01. TDD: update test helper first, run tests red, then fix production code.

## Inputs

- `FastTextVectors type from T01`
- `Current signatures: build_synset_embeddings (line 25), cmd_shootout (line 334), cmd_fill (line 367)`
- `Test helper at test_predict_concreteness.py:49-57`

## Expected Output

- `All three functions accept FastTextVectors parameter`
- `No dict[str, tuple[float, ...]] type annotations in predict_concreteness.py`
- `Test helper creates FastTextVectors instance`
- `All existing predict_concreteness tests pass`

## Verification

python -m pytest data-pipeline/scripts/test_predict_concreteness.py -v
