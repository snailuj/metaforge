# S02: Pipeline memory streamlining

**Goal:** Eliminate remaining memory waste: stream snap_properties via cursor instead of materialising ~294 MB, fold predict_concreteness into run_pipeline() to kill the double FastText load, add a threshold guard to cluster_vocab, and create a pipeline integration ordering test that verifies stage dependencies on every pipeline change.
**Demo:** Pipeline runs without 294 MB snap_properties spike, without double FastText load, and cluster_vocab warns on excessive pair counts.

## Must-Haves

- snap_properties processes rows via cursor iteration, never materialising the full synset_props list
- predict_concreteness fill runs inside run_pipeline() sharing the already-loaded FastTextVectors
- enrich.sh no longer invokes predict_concreteness.py as a separate process for the fill step
- cluster_vocab logs a warning when any chunk produces >100k pairs
- test_pipeline_integration.py exists with @pytest.mark.pipeline_integration marker
- pytest.ini (or conftest.py) registers the marker and excludes it from default runs
- Integration test asserts row counts at 5 checkpoints: synset_properties, lemma_embeddings, vocab_clusters, synset_properties_curated, synset_concreteness

## Proof Level

- This slice proves: Not provided.

## Integration Closure

Not provided.

## Verification

- Not provided.

## Tasks

- [ ] **T01: Stream snap_properties via cursor iteration** `est:30min`
  Refactor snap_properties() to avoid materialising the full synset_props list (~245k rows, ~294 MB with embedding blobs). Split into two passes: Pass 1 (Stages 1-2) queries synset_id, property text, salience only (no embedding blob) and resolves exact + morphological matches via cursor iteration. Pass 2 (Stage 3) queries only the unmatched synset-property pairs with their embedding blobs for cosine similarity. This avoids loading 1200-byte blobs for the ~60-70% of properties that match in Stages 1-2. TDD: write a test that verifies snap_properties produces identical output with the two-pass approach vs the current single-pass.
  - Files: `data-pipeline/scripts/snap_properties.py`, `data-pipeline/scripts/test_snap_properties.py`
  - Verify: python -m pytest data-pipeline/scripts/test_snap_properties.py -v

- [ ] **T02: Fold predict_concreteness fill into run_pipeline()** `est:30min`
  Move the concreteness gap-fill step from a separate process invocation (enrich.sh line 261) into run_pipeline() in enrich_pipeline.py, running after store_lemma_embeddings(). This eliminates a second 1.2 GB FastText load (was 11 GB pre-S01). Import cmd_fill (or the underlying functions) and call them with the already-loaded FastTextVectors and open connection. Update enrich.sh to remove the standalone predict_concreteness.py fill invocation. The shootout step remains standalone (it's an evaluation, not a pipeline stage). Handle the case where no shootout JSON exists (skip gracefully, matching current enrich.sh behaviour). TDD: add a test to test_enrich_pipeline.py verifying run_pipeline() populates synset_concreteness when a shootout JSON is provided.
  - Files: `data-pipeline/scripts/enrich_pipeline.py`, `data-pipeline/scripts/test_enrich_pipeline.py`, `data-pipeline/enrich.sh`
  - Verify: python -m pytest data-pipeline/scripts/test_enrich_pipeline.py data-pipeline/scripts/test_predict_concreteness.py -v

- [ ] **T03: Add threshold guard to cluster_vocab** `est:10min`
  Add a warning log to cluster_vocab() when any pairwise chunk produces more than 100k above-threshold pairs. This is a canary for threshold misconfiguration that could cause combinatoric explosion. The guard goes inside the inner loop at cluster_vocab.py:137, after the np.where call. TDD: write a test with a low threshold that triggers the warning, assert it was logged.
  - Files: `data-pipeline/scripts/cluster_vocab.py`, `data-pipeline/scripts/test_cluster_vocab.py`
  - Verify: python -m pytest data-pipeline/scripts/test_cluster_vocab.py -v

- [ ] **T04: Pipeline integration ordering test with marker and pytest config** `est:40min`
  Create test_pipeline_integration.py with @pytest.mark.pipeline_integration. Build a small fixture DB (~10 synsets, 3-4 properties each) with a tiny mock FastText file (5 words, 300d). Run the full pipeline end-to-end and assert row counts at 5 checkpoints: (1) synset_properties > 0 after curate+populate, (2) lemma_embeddings > 0 after store_lemma_embeddings, (3) vocab_clusters > 0 after cluster_vocab, (4) synset_properties_curated > 0 after snap_properties, (5) synset_concreteness > 0 after predict_concreteness (if shootout JSON provided). Create conftest.py to register the pipeline_integration marker. Create pytest.ini to exclude pipeline_integration from default runs. Document the CI path filter pattern in a comment.
  - Files: `data-pipeline/scripts/test_pipeline_integration.py`, `data-pipeline/scripts/conftest.py`, `data-pipeline/pytest.ini`
  - Verify: python -m pytest data-pipeline/scripts/test_pipeline_integration.py -v -m pipeline_integration && python -m pytest data-pipeline/scripts/ -v --co -q 2>&1 | grep -c pipeline_integration returns 0

## Files Likely Touched

- data-pipeline/scripts/snap_properties.py
- data-pipeline/scripts/test_snap_properties.py
- data-pipeline/scripts/enrich_pipeline.py
- data-pipeline/scripts/test_enrich_pipeline.py
- data-pipeline/enrich.sh
- data-pipeline/scripts/cluster_vocab.py
- data-pipeline/scripts/test_cluster_vocab.py
- data-pipeline/scripts/test_pipeline_integration.py
- data-pipeline/scripts/conftest.py
- data-pipeline/pytest.ini
