---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T01: Stream snap_properties via cursor iteration

Refactor snap_properties() to avoid materialising the full synset_props list (~245k rows, ~294 MB with embedding blobs). Split into two passes: Pass 1 (Stages 1-2) queries synset_id, property text, salience only (no embedding blob) and resolves exact + morphological matches via cursor iteration. Pass 2 (Stage 3) queries only the unmatched synset-property pairs with their embedding blobs for cosine similarity. This avoids loading 1200-byte blobs for the ~60-70% of properties that match in Stages 1-2. TDD: write a test that verifies snap_properties produces identical output with the two-pass approach vs the current single-pass.

## Inputs

- `Current snap_properties implementation at snap_properties.py:91-284`
- `synset_props list materialisation at lines 141-147`
- `Stage 3 embedding lookup at lines 214-251`

## Expected Output

- `snap_properties uses cursor iteration for Pass 1 (no embedding blob)`
- `Pass 2 fetches embeddings only for unmatched property IDs`
- `All existing snap_properties tests pass`
- `No list materialisation of full synset_props`

## Verification

python -m pytest data-pipeline/scripts/test_snap_properties.py -v
