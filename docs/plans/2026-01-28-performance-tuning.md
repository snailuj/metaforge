# Performance Tuning Notes

**Project:** Metaforge
**Phase:** Sprint Zero → Production
**Last Updated:** 2026-01-28

This document tracks performance considerations, optimisation opportunities, and scaling strategies identified during development.

---

## Overview

Sprint Zero uses a pilot corpus (1k synsets) to prove the data pipeline. Production will scale to the full WordNet corpus (120k synsets). This document captures performance implications and required optimisations.

---

## Database Layer Performance

### Issue: `GetSynsetsWithSharedProperties()` Full-Table Scan

**Identified:** 2026-01-28 (Task 6 code review)
**Component:** `api/internal/db/db.go`
**Status:** Acceptable for pilot, requires optimisation for production

#### Current Implementation

- Loads all enriched synsets into memory
- Performs in-memory property matching using Go map lookups
- Returns all matches (no limit)

#### Performance Characteristics

**Pilot Scale (1k synsets):**
- Memory usage: ~200 KB
- Query time: <10ms
- Status: ✅ Acceptable

**Full Corpus (120k synsets):**
- Memory usage: ~24 MB base, 50-100 MB peak
- Query time: 200-500ms (estimated)
- Status: ⚠️ Requires optimisation

#### Optimisation Strategy

##### Phase 1: Quick Wins (Implement with full corpus)

1. **Result Limiting**
   - Limit to top 50 matches by overlap count
   - Add early termination once N high-quality matches found
   - Expected improvement: 50% reduction in processing time

2. **Streaming Architecture**
   - Current implementation already streams rows from SQLite
   - Optimise slice preallocation: `matches := make([]SynsetMatch, 0, 50)`
   - No major refactor needed

##### Phase 2: Database Optimisations

**Option A: SQLite FTS5 (Recommended for MVP)**

Add Full-Text Search virtual table:

```sql
CREATE VIRTUAL TABLE properties_fts USING fts5(synset_id, properties);
```

Query becomes:
```sql
SELECT synset_id FROM properties_fts
WHERE properties MATCH 'prop1 OR prop2 OR prop3'
LIMIT 50;
```

**Advantages:**
- 10-50x speedup for property lookups
- Offloads work to SQLite's optimised C code
- No operational complexity (still single-file database)
- Works with existing Go stdlib `database/sql`

**Implementation:**
- Modify `04_extract_enrichment.py` to populate FTS5 table
- Update `GetSynsetsWithSharedProperties()` to query FTS5
- Estimated effort: 4-6 hours

**Option B: SQLite JSON1 Extension**

Use JSON array indexing:

```sql
CREATE INDEX idx_enrichment_props ON enrichment(json_each.value)
```

**Advantages:**
- Native JSON support (no schema duplication)
- Good for exact property matching

**Disadvantages:**
- Slower than FTS5 for multi-property queries
- Requires SQLite 3.38+ (check runtime version)

##### Phase 3: If SQLite Insufficient

**Option C: Migrate to PostgreSQL with GIN Indexes**

```sql
CREATE TABLE enrichment (
    synset_id TEXT PRIMARY KEY,
    properties JSONB NOT NULL
);
CREATE INDEX idx_properties_gin ON enrichment USING GIN(properties);
```

Query:
```sql
SELECT synset_id FROM enrichment
WHERE properties ?| array['prop1','prop2','prop3']
LIMIT 50;
```

**Advantages:**
- Best performance for complex queries
- Scales to millions of rows
- Rich indexing options

**Disadvantages:**
- Requires PostgreSQL server (ops complexity)
- Breaks zero-dependency deployment model
- Overkill for read-heavy workload with 120k rows

#### Recommendation

1. **Immediate (with full corpus):** Add result limiting (top 50 matches)
2. **Next iteration:** Implement SQLite FTS5 virtual table
3. **Benchmark:** Measure query time with full corpus
4. **Decision point:** If <100ms with FTS5, ship it. Otherwise evaluate PostgreSQL.

**Confidence:** SQLite FTS5 will be sufficient for MVP. Read-heavy workload with proper indexing should handle 120k rows comfortably.

---

## Future Optimisation Areas

### Embedding Distance Calculations

**Component:** `api/internal/embeddings/embeddings.go` (Task 7)
**Note:** Not yet implemented. Consider these when building:

- Pre-normalise vectors to avoid repeated norm calculations
- Use SIMD instructions for cosine distance (consider CGO binding to BLAS)
- Cache frequent word pair distances

### API Response Times

**Target:** <100ms p95 for `/forge/suggest` endpoint

**Breakdown:**
- Database query: <50ms
- Embedding distance: <30ms
- Tier classification: <5ms
- JSON serialisation: <5ms
- Network overhead: <10ms

**Monitor:** Add timing instrumentation in handler layer (Task 9)

---

## Benchmarking Plan

### Phase: Post Full Corpus Extraction

1. **Load Testing**
   - Tool: `vegeta` or `k6`
   - Scenario: 100 concurrent users, 1000 req/s
   - Duration: 5 minutes
   - Metrics: p50, p95, p99 latency; throughput; error rate

2. **Memory Profiling**
   - Use `pprof` to capture heap profiles
   - Identify allocation hotspots
   - Target: <200 MB steady-state memory usage

3. **Query Analysis**
   - Enable SQLite query logging
   - Analyse slow queries (>50ms)
   - Verify index usage with EXPLAIN QUERY PLAN

### Success Criteria

- p95 response time: <100ms
- Memory usage: <200 MB
- Throughput: >500 req/s (single instance)
- Zero errors under normal load

---

## Notes

- All optimisations should be data-driven (benchmark first, optimise second)
- SQLite is likely sufficient for MVP -- don't over-engineer
- Prioritise simplicity and operational ease over micro-optimisations
- Document all performance decisions for future reference

---

## References

- [SQLite FTS5 Documentation](https://www.sqlite.org/fts5.html)
- [PostgreSQL GIN Indexes](https://www.postgresql.org/docs/current/gin-intro.html)
- Code: `api/internal/db/db.go` lines 66-116 (detailed implementation notes)
