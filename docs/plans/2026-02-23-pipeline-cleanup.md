# Pipeline Cleanup: Remove Dead Computation Steps

**Date:** 2026-02-23

## Context

The enrichment pipeline computes three intermediate tables — `property_similarity`, `synset_centroids`, and IDF values — that are no longer consumed by any live code path. The Go API's forge matching switched to the curated vocabulary pipeline (`synset_properties_curated` + `cluster_antonyms`). The old embedding-based forge function `GetSynsetsWithSharedProperties` exists in `db.go` but is never called from any handler.

## Removal Scope

### Python (`enrich_pipeline.py`)

- Delete `compute_idf()` function
- Delete `compute_property_similarity()` function
- Delete `compute_synset_centroids()` function
- Remove their calls from `run_pipeline()`
- Remove `SIMILARITY_CHUNK_SIZE` constant

### Go (`api/internal/db/`)

- Delete `GetSynsetsWithSharedProperties()` function from `db.go`
- Delete `SynsetMatch` struct from `db.go`
- Delete all tests for `GetSynsetsWithSharedProperties` from `db_test.go`

### DB Schema (`SCHEMA.sql`)

- Remove `property_similarity` table + 3 indexes
- Remove `synset_centroids` table
- Remove `idf` column from `property_vocabulary`

### Tests (`test_enrich_pipeline.py`)

- Remove tests for the 3 deleted functions
- Update `run_pipeline` integration test expectations (no IDF/similarity/centroid stats)
- Update any test schema constants that include the removed tables/columns

## What Stays

- `property_vocabulary` — embeddings used by snap stage 3
- `synset_properties` — raw links used by snap
- `store_lemma_embeddings()` — used by Go API for cross-domain distance
- Full curated pipeline: build_vocab → cluster → snap → antonyms

## Build Sequence

1. Remove Python functions + calls, update tests → green → commit
2. Remove Go function + struct + tests → green → commit
3. Update SCHEMA.sql → commit

## Post-Cleanup

Work through 7 PR review fixes on the cleaned codebase.
