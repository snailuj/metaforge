# Code Review: Sprint Zero API Integration

**Date:** 2026-02-06
**Commits:** 0f03595..eb2a777
**Reviewer:** Claude (superpowers:code-reviewer)

## Strengths

### 1. Strong Architectural Decisions
- **Clean package separation**: The code is well-organised into distinct packages (`db`, `embeddings`, `forge`, `handler`) with clear responsibilities.
- **Backward compatibility**: The `GetSynsetsWithSharedProperties` function includes automatic detection of v1/v2 database schemas and falls back gracefully to legacy exact-match implementation.
- **Pre-computed similarity matrix**: Moving the O(n^2) similarity computation to build time (Python pipeline) rather than query time is a sound performance decision.

### 2. Matches Design Requirements
- **5-tier classification** (`api/internal/forge/forge.go` lines 10-16): Implements all five tiers exactly as specified in the design document (Legendary, Interesting, Strong, Obvious, Unlikely).
- **IDF weighting**: Properties are weighted by rarity, matching the design goal of prioritising "surprising" metaphor connections.
- **Threshold and limit parameters**: The HTTP handler supports configurable similarity threshold and result limits as specified.

### 3. Good Testing Coverage
- All Go packages have tests that pass.
- Python pipeline scripts have corresponding test files.
- Tests verify both happy paths and edge cases (invalid threshold, missing word, unknown word).
- Tests use real database data rather than mocks, validating actual behaviour.

### 4. Code Quality
- Clear, readable code with good documentation.
- Proper error handling with wrapped errors providing context.
- Nullable database fields handled correctly with `sql.NullString`.
- UK English spelling used consistently (e.g., "normalised", "vectorised").

---

## Issues

### Critical (Must Fix)

**None identified.** The implementation is functionally correct and secure.

---

### Important (Should Fix)

#### 1. N+1 Query Problem in Handler
**File:** `api/internal/handler/handler.go` lines 106-136

**What's wrong:** For each candidate match, the handler issues 3 separate database queries:
1. `db.GetSynset(c.SynsetID)` - line 108
2. `db.GetLemmaForSynset(c.SynsetID)` - line 114
3. `embeddings.ComputeSynsetDistance(...)` - line 120 (which queries embeddings)

With a default limit of 50 candidates, this results in 150+ queries per request.

**Why it matters:** Response time will be poor for production use. Current tests show ~0.24-0.75s per request, which may become problematic under load.

**How to fix:**
- Create a batch query function that retrieves synset details and lemmas for multiple synset IDs in a single query.
- Consider caching synset distance computations or pre-computing them in the similarity matrix.

---

#### 2. Missing SharedProperties in V2 Response
**File:** `api/internal/db/db.go` lines 121-146

**What's wrong:** The V2 similarity-based query returns `OverlapCount` but not the actual `SharedProperties` list. The `SynsetMatch.SharedProperties` field remains empty for V2 queries.

**Why it matters:** The design document shows users should see which properties are shared (for the "hint system"). The API response will have empty `shared_properties` arrays.

**How to fix:** Add a subquery or post-processing step to retrieve the actual matching property texts.

---

#### 3. Tier Classification Uses OverlapCount from Similarity Query
**File:** `api/internal/handler/handler.go` line 125

**What's wrong:** `c.OverlapCount` from the V2 query counts similar property pairs (similarity >= threshold), not exact property matches. The tier thresholds (`MinOverlap = 2`, `StrongOverlap = 4`) were designed for exact matches.

**Why it matters:** The tier classification may not behave as intended. A synset with 2 exact matches might now show as having 10+ "matches" if many properties are semantically similar, potentially over-promoting results to higher tiers.

**How to fix:** Either:
1. Re-tune the tier thresholds for similarity-based matching.
2. Pass the exact match count separately from the similarity-weighted score.
3. Document this as intentional behaviour change (similarity matches count toward overlap).

---

#### 4. Logging/Observability Missing
**Files:** All Go handler code

**What's wrong:** No logging of errors or query performance. Failed operations silently continue in loops.

**Why it matters:** Production debugging will be difficult. For example, if `db.GetSynset` fails in the handler loop (line 108-111), the error is silently swallowed with `continue`.

**How to fix:** Add structured logging for:
- Query failures (at least at debug level)
- Request latency
- Number of candidates processed vs returned

---

### Minor (Nice to Have)

#### 1. Bubble Sort in Legacy Path
**File:** `api/internal/db/db.go` lines 224-230

**What's wrong:** Uses O(n^2) bubble sort instead of the standard library's `sort.Slice`.

**Why it matters:** For large result sets, this is unnecessarily slow.

**How to fix:** Use `sort.Slice`.

---

#### 2. Hardcoded Default Distance
**File:** `api/internal/handler/handler.go` line 122

**What's wrong:** When distance computation fails, defaults to `0.5` which is below `HighDistanceThreshold (0.6)`, biasing failed computations toward "Obvious" or "Unlikely" tiers.

**Why it matters:** This may incorrectly demote potentially good metaphors when embeddings are missing.

**How to fix:** Consider defaulting to `0.7` (above threshold) or using a separate "unknown" tier.

---

#### 3. Missing Index on synset_properties.synset_id
**File:** Not in diff, but relevant to `api/internal/db/db.go`

**What's wrong:** The V2 query joins `synset_properties` by both `synset_id` and `property_id`. Verify indexes exist on both columns.

**Why it matters:** Query performance on larger datasets.

**How to fix:** Verify with `EXPLAIN QUERY PLAN` and add indexes if missing.

---

#### 4. Python Script Drops Table Unconditionally
**File:** `data-pipeline/scripts/07_compute_property_similarity.py` line 26

**What's wrong:** `DROP TABLE IF EXISTS property_similarity` always runs, losing existing data.

**Why it matters:** Re-running the script with a higher threshold would lose all existing similarity pairs.

**How to fix:** Add confirmation prompt or `--force` flag before dropping.

---

## Plan Alignment Assessment

| Plan Requirement | Status | Notes |
|-----------------|--------|-------|
| DB layer for lexicon_v2.db | Done | Junction table queries work correctly |
| FastText 300d embeddings layer | Done | Blob decoding, centroid comparison implemented |
| 5-tier matching algorithm | Done | All tiers implemented as designed |
| /forge/suggest HTTP endpoint | Done | With threshold/limit parameters |
| IDF weighting | Done | Pipeline script + SQL query integration |
| Property similarity matrix | Done | Pre-computed with configurable threshold |

**Deviations from Plan:**
1. Plan specified `ComputePropertySetDistance` taking property lists; implementation uses `ComputeSynsetDistance` taking synset IDs (improvement - cleaner API).
2. Plan mentioned chi router for main.go; main.go not in this diff (may be in separate commit).

---

## Assessment

**Ready to merge?** Yes, with fixes

**Reasoning:** The implementation correctly delivers the Sprint Zero API with the 5-tier classification, IDF weighting, and similarity-based matching. All tests pass. The architecture is sound and matches the design. However, the N+1 query problem in the handler and missing SharedProperties in V2 responses should be addressed before production use. For an MVP/pilot deployment, the current state is acceptable with awareness of the performance characteristics.
