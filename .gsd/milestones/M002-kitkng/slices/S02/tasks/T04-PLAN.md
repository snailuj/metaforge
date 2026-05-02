---
estimated_steps: 1
estimated_files: 3
skills_used: []
---

# T04: Pipeline integration ordering test with marker and pytest config

Create test_pipeline_integration.py with @pytest.mark.pipeline_integration. Build a small fixture DB (~10 synsets, 3-4 properties each) with a tiny mock FastText file (5 words, 300d). Run the full pipeline end-to-end and assert row counts at 5 checkpoints: (1) synset_properties > 0 after curate+populate, (2) lemma_embeddings > 0 after store_lemma_embeddings, (3) vocab_clusters > 0 after cluster_vocab, (4) synset_properties_curated > 0 after snap_properties, (5) synset_concreteness > 0 after predict_concreteness (if shootout JSON provided). Create conftest.py to register the pipeline_integration marker. Create pytest.ini to exclude pipeline_integration from default runs. Document the CI path filter pattern in a comment.

## Inputs

- `run_pipeline() orchestrator in enrich_pipeline.py`
- `Pipeline stage ordering from conversation analysis`
- `PRE_ENRICH.sql schema for fixture DB structure`

## Expected Output

- `test_pipeline_integration.py with @pytest.mark.pipeline_integration`
- `conftest.py registering the marker`
- `pytest.ini excluding pipeline_integration by default`
- `Test asserts row counts at 5 pipeline checkpoints`
- `Test uses in-memory DB with small fixture data, no real FastText file`

## Verification

python -m pytest data-pipeline/scripts/test_pipeline_integration.py -v -m pipeline_integration && python -m pytest data-pipeline/scripts/ -v --co -q 2>&1 | grep -c pipeline_integration returns 0
