---
estimated_steps: 1
estimated_files: 1
skills_used: []
---

# T04: Float32 precision regression test and full suite verification

Add a focused test in test_utils.py that verifies struct.pack output from the numpy float32 path matches the old tuple-of-float64 path within float32 tolerance (1e-7 relative). This catches any silent precision drift that could shift similarity thresholds. Then run the complete data-pipeline test suite to verify no regressions across all 24 test files.

## Inputs

- `FastTextVectors.__getitem__ returns float32 row`
- `struct.pack(f'{300}f', *tuple_of_floats) is the existing pack pattern`
- `Downstream consumers: _get_embedding, store_lemma_embeddings both struct.pack the vector`

## Expected Output

- `test_float32_precision_matches_tuple_pack in test_utils.py`
- `Full test suite (24 files) passes with 0 failures`

## Verification

cd data-pipeline && ../.venv/bin/python -m pytest scripts/ -v --tb=short
