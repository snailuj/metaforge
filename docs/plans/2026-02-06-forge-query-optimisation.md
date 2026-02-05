# Forge Query Optimisation Design

**Date:** 2026-02-06
**Status:** Ready for implementation

## Problem Statement

Two issues identified in code review:

1. **N+1 Query Problem:** Handler runs 150+ queries per request (3 per candidate × 50 limit)
2. **OverlapCount Semantics:** Tier thresholds designed for exact matches, but V2 counts similarity matches

## Design Decisions

### Issue 3: Overlap Semantics

**Decision:** Separate concerns
- **Similarity matrix** → candidate discovery (find synsets with semantically related properties)
- **Exact property intersection** → overlap count for tier classification and hint system

**Rationale:** The hint system says "you share 3 properties" - this should mean 3 actual properties to reveal, not fuzzy similarity counts.

**Future work:** Property canonicalisation script to collapse obvious synonyms ("holds_in_place" / "keeps_in_place") using similarity clusters.

### Issue 1: N+1 Queries

**Decision:** Pre-compute synset centroids at pipeline time

**Rationale:** Project philosophy is augmenting raw data. We already pre-compute property IDF and similarity matrix. Centroids follow the same pattern.

## Schema Changes

**New table: `synset_centroids`**

```sql
CREATE TABLE synset_centroids (
    synset_id TEXT PRIMARY KEY,
    centroid BLOB NOT NULL,  -- 300 × float32 = 1200 bytes
    property_count INTEGER NOT NULL
);

CREATE INDEX idx_synset_centroids_synset ON synset_centroids(synset_id);
```

**Size estimate:** 17k enriched synsets × 1.2KB ≈ 20MB (scales to ~200MB at full 107k enrichment)

## Query Design

**Single query replaces N+1 loop:**

```sql
WITH source_props AS (
    SELECT property_id FROM synset_properties WHERE synset_id = :source_id
),
candidates AS (
    -- Similarity-based candidate discovery (existing logic)
    SELECT sp.synset_id,
           SUM(ps.similarity * pv.idf) as total_score
    FROM source_props src
    JOIN property_similarity ps ON ps.property_id_a = src.property_id
    JOIN synset_properties sp ON sp.property_id = ps.property_id_b
    JOIN property_vocabulary pv ON pv.property_id = ps.property_id_b
    WHERE ps.similarity >= :threshold
      AND sp.synset_id != :source_id
    GROUP BY sp.synset_id
    ORDER BY total_score DESC
    LIMIT :limit
),
exact_overlap AS (
    -- Exact property matches for tier classification
    SELECT c.synset_id,
           COUNT(*) as exact_count,
           GROUP_CONCAT(pv.text) as shared_props
    FROM candidates c
    JOIN synset_properties sp ON sp.synset_id = c.synset_id
    JOIN source_props src ON src.property_id = sp.property_id
    JOIN property_vocabulary pv ON pv.property_id = sp.property_id
    GROUP BY c.synset_id
)
SELECT c.synset_id,
       s.definition,
       l.lemma,
       COALESCE(eo.exact_count, 0) as exact_count,
       eo.shared_props,
       c.total_score,
       src_c.centroid as source_centroid,
       tgt_c.centroid as target_centroid
FROM candidates c
JOIN synsets s ON s.synset_id = c.synset_id
JOIN lemmas l ON l.synset_id = c.synset_id
LEFT JOIN exact_overlap eo ON eo.synset_id = c.synset_id
JOIN synset_centroids src_c ON src_c.synset_id = :source_id
JOIN synset_centroids tgt_c ON tgt_c.synset_id = c.synset_id
```

**Distance computation:** Go-side cosine distance on centroids (no SQLite extension needed)

## Go Code Changes

### db package

```go
// New return type with all data in one query
type SynsetMatchFull struct {
    SynsetID         string
    Word             string
    Definition       string
    SharedProperties []string  // Exact matches for hints
    ExactOverlap     int       // For tier classification
    TotalScore       float64   // Similarity-weighted score for ranking
    SourceCentroid   []float32 // For distance calc
    TargetCentroid   []float32
}

// Replaces GetSynsetsWithSharedProperties + handler loop
func GetForgeMatches(db *sql.DB, sourceID string, threshold float64, limit int) ([]SynsetMatchFull, error)
```

### handler package

```go
func (h *ForgeHandler) HandleSuggest(...) {
    // 1. Single call gets everything
    matches, err := db.GetForgeMatches(h.database, synsetID, threshold, limit)

    // 2. Compute distance and classify tier (in-memory, no DB calls)
    for i := range matches {
        dist := embeddings.CosineDistance(matches[i].SourceCentroid, matches[i].TargetCentroid)
        tier := forge.ClassifyTier(dist, matches[i].ExactOverlap)
        // ... build response
    }

    // 3. Sort and return
}
```

### Removed code

- `GetSynset()` call in handler loop
- `GetLemmaForSynset()` call in handler loop
- `ComputeSynsetDistance()` (if unused elsewhere)

## Implementation Tasks

### Pipeline (Python)
1. Create `08_compute_synset_centroids.py`
2. Create `test_08_compute_synset_centroids.py`
3. Run on lexicon_v2.db

### Go API
1. Add `GetForgeMatches()` to db package with mega-query
2. Add tests for `GetForgeMatches()` (exact overlap, centroids returned)
3. Refactor handler to use `GetForgeMatches()`
4. Update handler tests
5. Remove dead code

## Performance Target

- Before: ~150 queries per request, 0.24-0.75s response time
- After: 1 query per request, target <100ms response time

## Future Work

- Property canonicalisation script (collapse synonyms using similarity clusters)
- Pipeline orchestrator script (run all scripts in correct order)
- SQLite extension for native cosine distance (if Go-side becomes bottleneck)
