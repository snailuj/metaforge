---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T02: Migrate enrich_pipeline.py consumers to FastTextVectors

Update _get_embedding(), _get_compound_embedding(), curate_properties(), and store_lemma_embeddings() to accept FastTextVectors instead of dict[str, tuple[float, ...]]. Key changes: _get_embedding uses vectors[word] which returns a numpy row — struct.pack needs *row.tolist() or row.tobytes(). _get_compound_embedding averages numpy rows directly instead of element-wise tuple math. store_lemma_embeddings packs from numpy row. Update test helpers (_make_vectors, _make_vec) in test_enrich_pipeline.py to return FastTextVectors. TDD: update tests first, watch them fail, then fix the production code.

## Inputs

- `FastTextVectors type from T01`
- `Current signatures: _get_embedding (line 86), _get_compound_embedding (line 95), curate_properties (line 126), store_lemma_embeddings (line 267)`
- `Test helpers at test_enrich_pipeline.py:92-143`

## Expected Output

- `All four functions accept FastTextVectors parameter`
- `No dict[str, tuple[float, ...]] type annotations in enrich_pipeline.py`
- `Test helpers create FastTextVectors instances`
- `All existing enrich_pipeline tests pass`

## Verification

python -m pytest data-pipeline/scripts/test_enrich_pipeline.py -v
