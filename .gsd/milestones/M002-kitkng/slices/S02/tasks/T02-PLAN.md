---
estimated_steps: 1
estimated_files: 3
skills_used: []
---

# T02: Fold predict_concreteness fill into run_pipeline()

Move the concreteness gap-fill step from a separate process invocation (enrich.sh line 261) into run_pipeline() in enrich_pipeline.py, running after store_lemma_embeddings(). This eliminates a second 1.2 GB FastText load (was 11 GB pre-S01). Import cmd_fill (or the underlying functions) and call them with the already-loaded FastTextVectors and open connection. Update enrich.sh to remove the standalone predict_concreteness.py fill invocation. The shootout step remains standalone (it's an evaluation, not a pipeline stage). Handle the case where no shootout JSON exists (skip gracefully, matching current enrich.sh behaviour). TDD: add a test to test_enrich_pipeline.py verifying run_pipeline() populates synset_concreteness when a shootout JSON is provided.

## Inputs

- `Current enrich.sh lines 255-270 (Step 4: Concreteness fill)`
- `predict_concreteness.py cmd_fill() at line 367`
- `run_pipeline() orchestrator at enrich_pipeline.py:307-385`
- `FastTextVectors type from S01`

## Expected Output

- `run_pipeline() calls concreteness fill after store_lemma_embeddings when shootout JSON exists`
- `enrich.sh Step 4 removed (or reduced to a skip-message for standalone use)`
- `New parameter shootout_json: Optional[str] on run_pipeline()`
- `Test verifying concreteness fill runs inside run_pipeline()`

## Verification

python -m pytest data-pipeline/scripts/test_enrich_pipeline.py data-pipeline/scripts/test_predict_concreteness.py -v
