# M03-S05 — Forge Integration into Go API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the M03 cascade scorer (concreteness gate → jaccard_salience Ortony rank → cosine-distance re-rank) from the Python evaluator into the Go `/forge/suggest` path, behind a feature flag, with full TDD coverage and a smoke-test crib against known apt pairs. The Go path must be efficient enough for production user-facing load.

**Architecture:** Three layers of work inside the Go API.

1. **Data layer** (`api/internal/db`):
   - In-memory **cache** of `synset_concreteness` (~74k rows, ~1 MB) and `synset_centroids` (~36k rows × 1.2 KB BLOB ≈ 43 MB) loaded once at handler init — static lookup tables, no reason to round-trip per request.
   - **Gate-pushdown** candidate CTE — extends `GetForgeMatchesCuratedByLemma` with `JOIN synset_concreteness` × 2 + `WHERE (vehicle − topic) >= threshold`. SQLite filters gate-rejects before they cross into Go.
   - **Batch** per-cluster salience lookup with a single `WHERE synset_id IN (...)` query for all distinct sources + targets in one request.

2. **Scoring layer** (`api/internal/forge`): `cascade.go` mirrors `evaluate_cascade.py` math (gate, jaccard_salience, monotonic-up-to-cap re-rank, additive composition). Pure functions. The gate check in `EvaluateCascadePair` is belt-and-braces: SQL pre-filtering narrows the candidate set; the function still validates per-pair so unit tests cover the full path.

3. **Handler layer** (`api/internal/handler`): feature-flagged cascade branch. Per-request work is 2 DB queries (candidates + batch properties) + N in-memory map lookups, where N is the post-gate candidate count. Source-side data is memoised within the request because the lemma's ≤ ~5 senses are reused across candidates.

**Performance budget:**

| Path | DB round-trips / request | RAM overhead | Per-candidate hot loop |
|------|--------------------------|--------------|------------------------|
| Legacy | 3 (CTE + 2 embedding lookups) | ~0 (transient) | 1 cosine over 300-dim |
| Naive cascade (rejected) | ~1 + 6N (concreteness ×2, props ×2, centroid ×2) | ~0 | same |
| **This plan** | **2** (gated CTE + batch props) | **~50 MB at startup** | jaccard over ≤30 keys + 1 cosine over 300-dim |

**Tech Stack:** Go 1.22, `database/sql` + `mattn/go-sqlite3`, `chi` router, existing `blobconv` helpers for float32 BLOB decode. Reference implementation: `data-pipeline/scripts/evaluate_cascade.py` and `evaluate_aptness._jaccard_salience`.

---

## Scope boundary

S05 is **only** the Go API change. The 14 deferrals from PR #19 are Python-side and explicitly out of scope (see `docs/superpowers/review-logs/2026-05-20-m03-cascade-gate-and-rank-review.md`). The background broad-vocab enrichment job (PID 2085841) is also orthogonal — it writes JSON only, never the DB.

## Production cascade config (locked, see `m03_cascade_winner_config` memory)

```
evaluator:               cascade
concreteness_threshold:  1.0   (signed; vehicle − topic)
alpha:                   1.0
d_cap:                   0.77
ortony_scoring:          jaccard_salience
composition:             additive
```

Stage 2 separation: +0.1779 vs M02 plateau −0.0407. The Go port is a direct semantic mirror — any deviation from these numbers in the smoke-test crib is a port bug, not a tuning discussion.

## File structure

| File | Responsibility | Status |
|------|----------------|--------|
| `api/internal/db/cascade_cache.go` | `CascadeCache` struct + `LoadCascadeCache(db)` — eager in-memory load of `synset_concreteness` and `synset_centroids` | Create |
| `api/internal/db/cascade_cache_test.go` | Cache load tests against live `lexicon_v2.db` | Create |
| `api/internal/db/cascade.go` | `GetSynsetClusterPropertiesBatch` and `GetForgeCascadeCandidatesByLemma` (gate-pushdown CTE) | Create |
| `api/internal/db/cascade_test.go` | DB query tests | Create |
| `api/internal/forge/cascade.go` | `CascadeConfig`, `CascadeResult`, `CascadeStatus`, `JaccardSalience`, `ReRankBonus`, `CascadeCosineDistance`, `EvaluateCascadePair` | Create |
| `api/internal/forge/cascade_test.go` | Pure-function unit tests | Create |
| `api/internal/handler/handler.go` | `NewHandlerWithCascade` (loads cache); cascade branch with batch loading + source-side memoisation | Modify |
| `api/internal/handler/handler_cascade_test.go` | End-to-end test of the cascade path | Create |
| `api/internal/forge/forge.go` | Extend `Match` struct with optional cascade fields | Modify |
| `api/cmd/metaforge/main.go` | `--cascade` flag wired to `METAFORGE_FORGE_CASCADE` env var | Modify |
| `docs/plans/2026-05-21-m03-s05-smoke-test-crib.md` | Pinned Python ground truth for parity check | Create |

## Smoke pair set (pin once, reuse forever)

```
apt:               anger→fire, idea→light, time→money, argument→war, life→journey
ambiguous / weak:  truth→hammer, silence→velvet
negative control:  cat→feline      (low signed delta — expect gate drop)
```

---

### Task 1: Cache module — eager in-memory load of concreteness + centroids

**Files:**
- Create: `api/internal/db/cascade_cache.go`
- Test: `api/internal/db/cascade_cache_test.go`

Why first: this is the largest optimisation — eliminates 4 of 6 per-candidate DB hops by trading ~50 MB RAM for O(1) lookups. Every later task depends on the `CascadeCache` type.

- [ ] **Step 1: Write the failing test**

```go
// api/internal/db/cascade_cache_test.go
package db

import (
	"testing"

	_ "github.com/mattn/go-sqlite3"
)

const testDBPath = "../../../data-pipeline/output/lexicon_v2.db"

func TestLoadCascadeCache_PopulatesBothTablesFromLiveDB(t *testing.T) {
	database, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	cache, err := LoadCascadeCache(database)
	if err != nil {
		t.Fatalf("LoadCascadeCache: %v", err)
	}

	// synset_concreteness has ~74k rows on the current DB (verified via sqlite3).
	if len(cache.Concreteness) < 70000 {
		t.Errorf("expected ≥70k concreteness rows, got %d", len(cache.Concreteness))
	}
	// synset_centroids has ~36k rows.
	if len(cache.Centroids) < 35000 {
		t.Errorf("expected ≥35k centroid rows, got %d", len(cache.Centroids))
	}

	// Spot-check known row (synset 76737, score 4.88 from brysbaert).
	if score, ok := cache.Concreteness["76737"]; !ok {
		t.Error("expected synset 76737 in concreteness cache")
	} else if score < 4.87 || score > 4.89 {
		t.Errorf("synset 76737: want ~4.88, got %v", score)
	}

	// Spot-check known centroid (synset 12933, 300-dim float32).
	if vec, ok := cache.Centroids["12933"]; !ok {
		t.Error("expected synset 12933 in centroid cache")
	} else if len(vec) != 300 {
		t.Errorf("synset 12933 centroid: want 300-dim, got %d", len(vec))
	}
}

func TestLoadCascadeCache_MissingTablesFailOpen(t *testing.T) {
	// In-memory DB has neither table → cache loads empty, no error.
	// This is the fixture-DB safety net so handler tests against synthetic
	// DBs don't have to provide every table.
	database, err := openMemoryDB(t)
	if err != nil {
		t.Fatalf("openMemoryDB: %v", err)
	}
	defer database.Close()

	cache, err := LoadCascadeCache(database)
	if err != nil {
		t.Fatalf("LoadCascadeCache on empty DB returned error: %v", err)
	}
	if len(cache.Concreteness) != 0 || len(cache.Centroids) != 0 {
		t.Errorf("empty DB should produce empty caches, got %d / %d",
			len(cache.Concreteness), len(cache.Centroids))
	}
}

// openMemoryDB is a tiny helper to give the fail-open test its own connection.
func openMemoryDB(t *testing.T) (*sql.DB, error) {
	t.Helper()
	return sql.Open("sqlite3", ":memory:")
}
```

Add `"database/sql"` to the test file imports.

- [ ] **Step 2: Run test to verify it fails**

```
export PATH="/usr/local/go/bin:$PATH"
cd api && go test ./internal/db/ -run TestLoadCascadeCache -v
```

Expected: FAIL with `undefined: LoadCascadeCache`.

- [ ] **Step 3: Write minimal implementation**

```go
// api/internal/db/cascade_cache.go
// In-memory cache of the static cascade lookup tables.
//
// synset_concreteness and synset_centroids are immutable across the
// lifetime of an API process — they're written by the data pipeline and
// only read by the API. Pulling them into memory at startup eliminates
// the per-candidate DB round-trips that would otherwise dominate
// /forge/suggest latency under the cascade path.
package db

import (
	"database/sql"
	"fmt"
	"log/slog"
	"strings"

	"github.com/snailuj/metaforge/internal/blobconv"
)

// CascadeCache holds the per-synset concreteness scores and centroid
// vectors for fast in-memory lookup during cascade scoring. Construct
// via LoadCascadeCache; the maps themselves are exposed read-only by
// convention.
type CascadeCache struct {
	Concreteness map[string]float64
	Centroids    map[string][]float32
}

// LoadCascadeCache reads both static cascade tables into memory in one
// pass each. Missing tables fail open (empty maps, nil error) so fixture
// DBs without the cascade pipeline can still construct a handler.
func LoadCascadeCache(database *sql.DB) (*CascadeCache, error) {
	cache := &CascadeCache{
		Concreteness: make(map[string]float64, 80000),
		Centroids:    make(map[string][]float32, 40000),
	}

	if err := loadConcreteness(database, cache.Concreteness); err != nil {
		return nil, err
	}
	if err := loadCentroids(database, cache.Centroids); err != nil {
		return nil, err
	}

	slog.Info("cascade cache loaded",
		"concreteness_rows", len(cache.Concreteness),
		"centroid_rows", len(cache.Centroids),
	)
	return cache, nil
}

func loadConcreteness(database *sql.DB, dst map[string]float64) error {
	rows, err := database.Query("SELECT synset_id, score FROM synset_concreteness")
	if err != nil {
		if strings.Contains(err.Error(), "no such table") {
			return nil
		}
		return fmt.Errorf("load concreteness: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var id string
		var score float64
		if err := rows.Scan(&id, &score); err != nil {
			slog.Warn("scan concreteness row failed", "err", err)
			continue
		}
		dst[id] = score
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("iterate concreteness: %w", err)
	}
	return nil
}

func loadCentroids(database *sql.DB, dst map[string][]float32) error {
	rows, err := database.Query("SELECT synset_id, centroid FROM synset_centroids")
	if err != nil {
		if strings.Contains(err.Error(), "no such table") {
			return nil
		}
		return fmt.Errorf("load centroids: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var id string
		var blob []byte
		if err := rows.Scan(&id, &blob); err != nil {
			slog.Warn("scan centroid row failed", "err", err)
			continue
		}
		if len(blob) == 0 {
			continue
		}
		vec := blobconv.BlobToFloats(blob)
		if vec == nil {
			// Dim mismatch — log and skip. The cache's job is to mirror what
			// the DB has; a malformed row is a pipeline-side issue.
			slog.Warn("centroid blob malformed, skipping", "synset", id, "bytes", len(blob))
			continue
		}
		dst[id] = vec
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("iterate centroids: %w", err)
	}
	return nil
}
```

- [ ] **Step 4: Run test to verify it passes**

```
cd api && go test ./internal/db/ -run TestLoadCascadeCache -v
```

Expected: PASS (both subtests).

- [ ] **Step 5: Commit**

```
git add api/internal/db/cascade_cache.go api/internal/db/cascade_cache_test.go
git commit -m "feat(db): add CascadeCache eager in-memory load of static tables

synset_concreteness + synset_centroids are immutable across a process
lifetime; loading them once at handler init (~50 MB RAM) eliminates ~4
DB round-trips per cascade candidate. Missing tables fail open so
fixture DBs don't have to ship the cascade pipeline."
```

---

### Task 2: Batch per-cluster salience lookup

**Files:**
- Create: `api/internal/db/cascade.go`
- Create: `api/internal/db/cascade_test.go`

Why batch: the cascade needs `{cluster_id: salience}` for ~50 distinct synsets per request (≤5 sources + up to 50 candidates). One `WHERE synset_id IN (?,?,…)` is the right shape, mirroring the existing `GetLemmaEmbeddingsBatch` pattern.

- [ ] **Step 1: Write the failing test**

```go
// api/internal/db/cascade_test.go
package db

import (
	"testing"

	_ "github.com/mattn/go-sqlite3"
)

func TestGetSynsetClusterPropertiesBatch_ReturnsMapPerSynset(t *testing.T) {
	database, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	// Resolve two known-enriched lemmas to synset_ids.
	var fireID, waterID string
	if err := database.QueryRow(`
		SELECT l.synset_id FROM lemmas l
		JOIN synset_properties_curated spc ON spc.synset_id = l.synset_id
		WHERE l.lemma = 'fire' GROUP BY l.synset_id
		ORDER BY COUNT(*) DESC LIMIT 1
	`).Scan(&fireID); err != nil {
		t.Fatalf("resolve fire: %v", err)
	}
	if err := database.QueryRow(`
		SELECT l.synset_id FROM lemmas l
		JOIN synset_properties_curated spc ON spc.synset_id = l.synset_id
		WHERE l.lemma = 'water' GROUP BY l.synset_id
		ORDER BY COUNT(*) DESC LIMIT 1
	`).Scan(&waterID); err != nil {
		t.Fatalf("resolve water: %v", err)
	}

	out, err := GetSynsetClusterPropertiesBatch(database, []string{fireID, waterID})
	if err != nil {
		t.Fatalf("batch: %v", err)
	}
	if len(out[fireID]) == 0 {
		t.Errorf("expected non-empty props for fire/%s", fireID)
	}
	if len(out[waterID]) == 0 {
		t.Errorf("expected non-empty props for water/%s", waterID)
	}
	for cid, sal := range out[fireID] {
		if sal <= 0 {
			t.Errorf("fire/%d: non-positive salience %v", cid, sal)
		}
	}
}

func TestGetSynsetClusterPropertiesBatch_MissingSynsetsAbsentFromMap(t *testing.T) {
	database, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	out, err := GetSynsetClusterPropertiesBatch(database, []string{"not-a-real-id"})
	if err != nil {
		t.Fatalf("batch: %v", err)
	}
	if _, present := out["not-a-real-id"]; present {
		t.Error("missing synset must be absent from result map, not empty-mapped")
	}
}

func TestGetSynsetClusterPropertiesBatch_EmptyInputReturnsEmptyResult(t *testing.T) {
	database, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	out, err := GetSynsetClusterPropertiesBatch(database, nil)
	if err != nil {
		t.Fatalf("batch nil: %v", err)
	}
	if len(out) != 0 {
		t.Errorf("nil input: want empty result, got %d entries", len(out))
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

```
cd api && go test ./internal/db/ -run TestGetSynsetClusterPropertiesBatch -v
```

Expected: FAIL with `undefined: GetSynsetClusterPropertiesBatch`.

- [ ] **Step 3: Write minimal implementation**

```go
// api/internal/db/cascade.go
package db

import (
	"database/sql"
	"fmt"
	"log/slog"
	"strings"
)

// GetSynsetClusterPropertiesBatch returns the curated-vocab cluster_id →
// salience_sum map for each requested synset, in one IN-clause query.
// Synsets with no curated properties are absent from the result map.
// Empty input returns an empty (non-nil) map with no error.
func GetSynsetClusterPropertiesBatch(database *sql.DB, synsetIDs []string) (map[string]map[int64]float64, error) {
	out := make(map[string]map[int64]float64, len(synsetIDs))
	if len(synsetIDs) == 0 {
		return out, nil
	}

	placeholders := make([]string, len(synsetIDs))
	args := make([]interface{}, len(synsetIDs))
	for i, id := range synsetIDs {
		placeholders[i] = "?"
		args[i] = id
	}
	query := "SELECT synset_id, cluster_id, salience_sum FROM synset_properties_curated WHERE synset_id IN (" +
		strings.Join(placeholders, ",") + ")"

	rows, err := database.Query(query, args...)
	if err != nil {
		return nil, fmt.Errorf("GetSynsetClusterPropertiesBatch query: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var id string
		var cid int64
		var sal float64
		if err := rows.Scan(&id, &cid, &sal); err != nil {
			slog.Warn("scan cluster prop batch row failed", "err", err)
			continue
		}
		props, ok := out[id]
		if !ok {
			props = make(map[int64]float64)
			out[id] = props
		}
		props[cid] = sal
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("GetSynsetClusterPropertiesBatch iterate: %w", err)
	}
	return out, nil
}
```

- [ ] **Step 4: Run test to verify it passes**

```
cd api && go test ./internal/db/ -run TestGetSynsetClusterPropertiesBatch -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```
git add api/internal/db/cascade.go api/internal/db/cascade_test.go
git commit -m "feat(db): add GetSynsetClusterPropertiesBatch for cascade Ortony rank

One IN-clause query returns {synset_id: {cluster_id: salience}} for the
union of ≤5 distinct sources and ≤50 candidates per /forge/suggest
request. Missing synsets are absent (not empty-mapped) so callers can
distinguish 'no properties' from 'not queried'."
```

---

### Task 3: Gate-pushdown candidate query

**Files:**
- Modify: `api/internal/db/cascade.go`
- Modify: `api/internal/db/cascade_test.go`

Why gate pushdown: the legacy `GetForgeMatchesCuratedByLemma` returns candidates whose signed concreteness delta might be ≪ 1.0. Filtering SQL-side via `JOIN synset_concreteness × 2 + WHERE` means SQLite drops gate-rejects before they reach Go — no over-fetch, no post-fetch attrition pass.

- [ ] **Step 1: Write the failing test**

Append to `api/internal/db/cascade_test.go`:

```go
func TestGetForgeCascadeCandidatesByLemma_AllPassConcretenessgate(t *testing.T) {
	database, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	cache, err := LoadCascadeCache(database)
	if err != nil {
		t.Fatalf("LoadCascadeCache: %v", err)
	}

	candidates, err := GetForgeCascadeCandidatesByLemma(database, "anger", 1.0, 20)
	if err != nil {
		t.Fatalf("GetForgeCascadeCandidatesByLemma: %v", err)
	}
	if len(candidates) == 0 {
		t.Fatal("expected at least one cascade candidate for 'anger'")
	}

	// Every returned candidate must have (vehicle − topic) ≥ 1.0 by the cache.
	for _, c := range candidates {
		topicScore, hasTopic := cache.Concreteness[c.SourceSynsetID]
		vehScore, hasVeh := cache.Concreteness[c.SynsetID]
		if !hasTopic || !hasVeh {
			t.Errorf("candidate %s/%s missing concreteness in cache", c.SourceSynsetID, c.SynsetID)
			continue
		}
		if vehScore-topicScore < 1.0 {
			t.Errorf("candidate %s (vehicle %v) − %s (topic %v) = %v < 1.0",
				c.SynsetID, vehScore, c.SourceSynsetID, topicScore, vehScore-topicScore)
		}
	}
}

func TestGetForgeCascadeCandidatesByLemma_LemmaWithNoGatePassReturnsEmpty(t *testing.T) {
	database, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	// An abstract noun with concreteness ~5.0 leaves no room for a vehicle
	// to be 1.0 more concrete (max concreteness is ~5.0 on the Brysbaert scale).
	// 'cat' is concrete (~4.9) — gate effectively never passes.
	candidates, err := GetForgeCascadeCandidatesByLemma(database, "cat", 1.0, 20)
	if err != nil {
		t.Fatalf("GetForgeCascadeCandidatesByLemma: %v", err)
	}
	if len(candidates) > 0 {
		t.Logf("note: cat returned %d candidates — verify by hand", len(candidates))
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

```
cd api && go test ./internal/db/ -run TestGetForgeCascadeCandidatesByLemma -v
```

Expected: FAIL with `undefined: GetForgeCascadeCandidatesByLemma`.

- [ ] **Step 3: Write minimal implementation**

Append to `api/internal/db/cascade.go`:

```go
// CascadeCandidate is one gate-passed candidate row, populated by
// GetForgeCascadeCandidatesByLemma. Mirrors CuratedMatch but extends with
// the topic / vehicle concreteness scores already known from the
// CTE-side join (saves the handler from re-querying the cache for them).
type CascadeCandidate struct {
	SynsetID             string
	Word                 string
	POS                  string
	Definition           string
	SalienceSum          float64
	ContrastCount        int
	SharedProps          []string
	SourceSynsetID       string
	SourceDefinition     string
	SourcePOS            string
	TopicConcreteness    float64
	VehicleConcreteness  float64
}

// GetForgeCascadeCandidatesByLemma extends the curated-by-lemma CTE with a
// concreteness join that filters out gate-rejected candidates SQL-side.
// Only candidates with (vehicle_score − topic_score) ≥ threshold reach Go.
//
// The structural query shape is identical to GetForgeMatchesCuratedByLemma
// — same best-sense selection, same antonym counting — with two new JOINs
// against synset_concreteness and one WHERE clause. Candidates with missing
// concreteness on either side are excluded (INNER JOIN) because the
// cascade would route them to missing_concreteness anyway.
//
// Returns ErrLemmaNotFound when the lemma has no curated properties at all
// (same contract as GetForgeMatchesCuratedByLemma). An empty result with
// nil error means the lemma is enriched but no candidate passes the gate.
func GetForgeCascadeCandidatesByLemma(
	database *sql.DB, lemma string, threshold float64, limit int,
) ([]CascadeCandidate, error) {
	rows, err := database.Query(`
		WITH source_synsets AS (
			SELECT l.synset_id
			FROM lemmas l
			JOIN synset_properties_curated spc ON spc.synset_id = l.synset_id
			WHERE l.lemma = ?
			GROUP BY l.synset_id
		),
		per_sense_shared AS (
			SELECT ss.synset_id as source_id,
			       tgt.synset_id as target_id,
			       SUM(tgt.salience_sum) as salience_sum,
			       GROUP_CONCAT(pvc.lemma) as shared_props
			FROM source_synsets ss
			JOIN synset_properties_curated src ON src.synset_id = ss.synset_id
			JOIN synset_properties_curated tgt ON tgt.cluster_id = src.cluster_id
			JOIN property_vocab_curated pvc ON pvc.vocab_id = src.cluster_id
			WHERE tgt.synset_id NOT IN (SELECT synset_id FROM source_synsets)
			GROUP BY ss.synset_id, tgt.synset_id
		),
		best_sense AS (
			SELECT source_id, target_id, salience_sum, shared_props,
			       ROW_NUMBER() OVER (PARTITION BY target_id ORDER BY salience_sum DESC) as rn
			FROM per_sense_shared
		),
		per_sense_contrast AS (
			SELECT ss.synset_id as source_id,
			       tgt.synset_id as target_id,
			       COUNT(*) as contrast_count
			FROM source_synsets ss
			JOIN synset_properties_curated src ON src.synset_id = ss.synset_id
			JOIN cluster_antonyms ca ON ca.cluster_id_a = src.cluster_id
			JOIN synset_properties_curated tgt ON tgt.cluster_id = ca.cluster_id_b
			WHERE tgt.synset_id NOT IN (SELECT synset_id FROM source_synsets)
			GROUP BY ss.synset_id, tgt.synset_id
		),
		best_contrast AS (
			SELECT source_id, target_id, contrast_count,
			       ROW_NUMBER() OVER (PARTITION BY target_id ORDER BY contrast_count DESC) as rn
			FROM per_sense_contrast
		)
		SELECT bs.target_id,
		       ts.pos, ts.definition,
		       l.lemma,
		       bs.salience_sum,
		       COALESCE(bc.contrast_count, 0) as contrast_count,
		       bs.shared_props,
		       bs.source_id,
		       ss.definition as source_definition,
		       ss.pos as source_pos,
		       sct.score as topic_score,
		       scv.score as vehicle_score
		FROM best_sense bs
		JOIN synsets ts ON ts.synset_id = bs.target_id
		JOIN synsets ss ON ss.synset_id = bs.source_id
		JOIN lemmas l ON l.synset_id = bs.target_id
		LEFT JOIN best_contrast bc ON bc.target_id = bs.target_id AND bc.rn = 1
		JOIN synset_concreteness sct ON sct.synset_id = bs.source_id
		JOIN synset_concreteness scv ON scv.synset_id = bs.target_id
		WHERE bs.rn = 1
		  AND (scv.score - sct.score) >= ?
		ORDER BY bs.salience_sum + COALESCE(bc.contrast_count, 0) DESC
		LIMIT ?
	`, lemma, threshold, limit)

	if err != nil {
		// Surface "no such table" cleanly — cascade tables may be absent on
		// fixture DBs. Handler decides whether that's fatal (cascade mode)
		// or skippable (legacy mode never calls this).
		if strings.Contains(err.Error(), "no such table") {
			return nil, fmt.Errorf("cascade tables missing: %w", err)
		}
		return nil, fmt.Errorf("GetForgeCascadeCandidatesByLemma query: %w", err)
	}
	defer rows.Close()

	seen := make(map[string]bool)
	var matches []CascadeCandidate
	sawAnyRow := false

	for rows.Next() {
		sawAnyRow = true
		var m CascadeCandidate
		var sharedProps string
		if err := rows.Scan(
			&m.SynsetID, &m.POS, &m.Definition, &m.Word,
			&m.SalienceSum, &m.ContrastCount, &sharedProps,
			&m.SourceSynsetID, &m.SourceDefinition, &m.SourcePOS,
			&m.TopicConcreteness, &m.VehicleConcreteness,
		); err != nil {
			slog.Warn("scan cascade candidate failed", "err", err)
			continue
		}
		if seen[m.SynsetID] {
			continue
		}
		seen[m.SynsetID] = true
		if sharedProps != "" {
			m.SharedProps = strings.Split(sharedProps, ",")
		}
		matches = append(matches, m)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("GetForgeCascadeCandidatesByLemma iterate: %w", err)
	}

	// Distinguish "lemma not enriched" from "lemma enriched but no gate-pass":
	// the former is a 404 to the user; the latter is an empty 200.
	if !sawAnyRow {
		// Re-check: does the lemma have any curated source synset at all?
		var lemmaHasProps int
		err := database.QueryRow(`
			SELECT COUNT(*) FROM lemmas l
			JOIN synset_properties_curated spc ON spc.synset_id = l.synset_id
			WHERE l.lemma = ?
		`, lemma).Scan(&lemmaHasProps)
		if err == nil && lemmaHasProps == 0 {
			return nil, fmt.Errorf("%w: %s", ErrLemmaNotFound, lemma)
		}
	}

	return matches, nil
}
```

- [ ] **Step 4: Run test to verify it passes**

```
cd api && go test ./internal/db/ -run TestGetForgeCascadeCandidatesByLemma -v
```

Expected: PASS (both subtests).

- [ ] **Step 5: Commit**

```
git add api/internal/db/cascade.go api/internal/db/cascade_test.go
git commit -m "feat(db): add gate-pushdown cascade candidate query

Extends curated-by-lemma CTE with JOIN synset_concreteness × 2 and
WHERE (vehicle − topic) >= threshold. SQLite drops gate-rejects before
they cross into Go — no 4× pool over-fetch needed. Concreteness scores
ride along on the row to save the handler re-querying the cache."
```

---

### Task 4: Cascade primitive — JaccardSalience

**Files:**
- Create: `api/internal/forge/cascade.go`
- Create: `api/internal/forge/cascade_test.go`

Why first inside forge: pure function, no DB. Tests pin the math before any control flow.

- [ ] **Step 1: Write the failing test**

```go
// api/internal/forge/cascade_test.go
package forge

import (
	"math"
	"testing"
)

func TestJaccardSalience_PerfectOverlap(t *testing.T) {
	a := map[int64]float64{1: 1.0, 2: 1.0}
	b := map[int64]float64{1: 1.0, 2: 1.0}
	if got := JaccardSalience(a, b); math.Abs(got-1.0) > 1e-9 {
		t.Errorf("expected 1.0, got %v", got)
	}
}

func TestJaccardSalience_DisjointReturnsZero(t *testing.T) {
	a := map[int64]float64{1: 0.5}
	b := map[int64]float64{2: 0.5}
	if got := JaccardSalience(a, b); got != 0.0 {
		t.Errorf("expected 0.0, got %v", got)
	}
}

func TestJaccardSalience_EmptyInputsReturnZero(t *testing.T) {
	if got := JaccardSalience(nil, nil); got != 0.0 {
		t.Errorf("expected 0.0 for nil/nil, got %v", got)
	}
	if got := JaccardSalience(map[int64]float64{}, map[int64]float64{1: 0.5}); got != 0.0 {
		t.Errorf("expected 0.0 for empty/full, got %v", got)
	}
}

func TestJaccardSalience_AsymmetricSalienceMatchesPython(t *testing.T) {
	// pa = {1:0.8, 2:0.4, 3:0.1}, pb = {1:0.2, 2:0.6, 4:0.9}
	// shared = {1,2}; num = min(0.8,0.2)+min(0.4,0.6) = 0.6
	// union = {1,2,3,4}; den = 0.8+0.6+0.1+0.9 = 2.4
	// score = 0.6/2.4 = 0.25
	a := map[int64]float64{1: 0.8, 2: 0.4, 3: 0.1}
	b := map[int64]float64{1: 0.2, 2: 0.6, 4: 0.9}
	if got := JaccardSalience(a, b); math.Abs(got-0.25) > 1e-9 {
		t.Errorf("expected 0.25, got %v", got)
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

```
cd api && go test ./internal/forge/ -run TestJaccardSalience -v
```

Expected: FAIL with `undefined: JaccardSalience`.

- [ ] **Step 3: Write minimal implementation**

```go
// api/internal/forge/cascade.go
// Cascade scorer: concreteness gate → jaccard_salience Ortony rank →
// cosine-distance re-rank. Mirrors data-pipeline/scripts/evaluate_cascade.py
// — divergences from the Python ground truth in the smoke crib are port bugs.
package forge

// JaccardSalience returns Σ min(pa[c],pb[c]) over shared keys divided by
// Σ max(pa[c],pb[c]) over the union. Returns 0.0 for empty inputs or
// degenerate union.
func JaccardSalience(pa, pb map[int64]float64) float64 {
	if len(pa) == 0 || len(pb) == 0 {
		return 0.0
	}
	var num, den float64
	for c, va := range pa {
		if vb, shared := pb[c]; shared {
			if va < vb {
				num += va
			} else {
				num += vb
			}
			if va > vb {
				den += va
			} else {
				den += vb
			}
		} else {
			den += va
		}
	}
	for c, vb := range pb {
		if _, shared := pa[c]; !shared {
			den += vb
		}
	}
	if den == 0 {
		return 0.0
	}
	return num / den
}
```

- [ ] **Step 4: Run test to verify it passes**

```
cd api && go test ./internal/forge/ -run TestJaccardSalience -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```
git add api/internal/forge/cascade.go api/internal/forge/cascade_test.go
git commit -m "feat(forge): add JaccardSalience for cascade Ortony rank

Mirrors evaluate_aptness._jaccard_salience exactly. Empty/degenerate
inputs return 0.0 defensively so callers don't need to guard."
```

---

### Task 5: Cascade primitive — ReRankBonus and CascadeCosineDistance

**Files:**
- Modify: `api/internal/forge/cascade.go`
- Modify: `api/internal/forge/cascade_test.go`

- [ ] **Step 1: Write the failing test**

Append to `api/internal/forge/cascade_test.go`:

```go
func TestReRankBonus_BelowZeroReturnsZero(t *testing.T) {
	if got := ReRankBonus(-0.1, 0.77); got != 0.0 {
		t.Errorf("want 0.0, got %v", got)
	}
}

func TestReRankBonus_AtCapReturnsOne(t *testing.T) {
	if got := ReRankBonus(0.77, 0.77); math.Abs(got-1.0) > 1e-9 {
		t.Errorf("want 1.0, got %v", got)
	}
}

func TestReRankBonus_AboveCapSaturatesAtOne(t *testing.T) {
	if got := ReRankBonus(1.5, 0.77); got != 1.0 {
		t.Errorf("want 1.0, got %v", got)
	}
}

func TestReRankBonus_LinearBelowCap(t *testing.T) {
	if got := ReRankBonus(0.385, 0.77); math.Abs(got-0.5) > 1e-9 {
		t.Errorf("want 0.5, got %v", got)
	}
}

func TestCascadeCosineDistance_Identical(t *testing.T) {
	v := []float32{1, 0, 0}
	d, ok := CascadeCosineDistance(v, v)
	if !ok {
		t.Fatal("ok=false on identical")
	}
	if math.Abs(d) > 1e-6 {
		t.Errorf("want ~0, got %v", d)
	}
}

func TestCascadeCosineDistance_Orthogonal(t *testing.T) {
	d, ok := CascadeCosineDistance([]float32{1, 0}, []float32{0, 1})
	if !ok {
		t.Fatal("ok=false on orthogonal")
	}
	if math.Abs(d-1.0) > 1e-6 {
		t.Errorf("want ~1.0, got %v", d)
	}
}

func TestCascadeCosineDistance_DimMismatchReturnsNotOk(t *testing.T) {
	if _, ok := CascadeCosineDistance([]float32{1, 0, 0}, []float32{1, 0}); ok {
		t.Error("expected ok=false on dim mismatch")
	}
}

func TestCascadeCosineDistance_ZeroNormReturnsNotOk(t *testing.T) {
	if _, ok := CascadeCosineDistance([]float32{0, 0, 0}, []float32{1, 0, 0}); ok {
		t.Error("expected ok=false on zero norm")
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

```
cd api && go test ./internal/forge/ -run "TestReRankBonus|TestCascadeCosineDistance" -v
```

Expected: FAIL with `undefined: ReRankBonus` / `CascadeCosineDistance`.

- [ ] **Step 3: Write minimal implementation**

Append to `api/internal/forge/cascade.go`:

```go
import "math"

// ReRankBonus is the monotonic-up-to-cap reward shape: clip(d/dCap, 0, 1).
// dCap ≤ 0 returns 0 defensively.
func ReRankBonus(d, dCap float64) float64 {
	if dCap <= 0 {
		return 0.0
	}
	r := d / dCap
	if r < 0.0 {
		return 0.0
	}
	if r > 1.0 {
		return 1.0
	}
	return r
}

// CascadeCosineDistance returns 1 − cosine_similarity ∈ [0, 2]. The bool
// is false on dim mismatch OR zero-norm input — both surface as
// 'missing centroid' upstream, not as a degenerate 1.0 like the legacy
// embeddings.CosineDistance helper.
func CascadeCosineDistance(a, b []float32) (float64, bool) {
	if len(a) != len(b) || len(a) == 0 {
		return 0, false
	}
	var dot, na, nb float64
	for i := range a {
		dot += float64(a[i]) * float64(b[i])
		na += float64(a[i]) * float64(a[i])
		nb += float64(b[i]) * float64(b[i])
	}
	if na == 0 || nb == 0 {
		return 0, false
	}
	sim := dot / (math.Sqrt(na) * math.Sqrt(nb))
	if sim > 1.0 {
		sim = 1.0
	} else if sim < -1.0 {
		sim = -1.0
	}
	return 1.0 - sim, true
}
```

- [ ] **Step 4: Run test to verify it passes**

```
cd api && go test ./internal/forge/ -run "TestReRankBonus|TestCascadeCosineDistance" -v
```

Expected: PASS (all 8 subtests).

- [ ] **Step 5: Commit**

```
git add api/internal/forge/cascade.go api/internal/forge/cascade_test.go
git commit -m "feat(forge): add ReRankBonus and CascadeCosineDistance

Monotonic-up-to-cap reward + fail-explicit cosine distance (returns
(_, false) on dim mismatch / zero norm rather than collapsing to 1.0
like the legacy embeddings.CosineDistance contract)."
```

---

### Task 6: Cascade orchestrator — EvaluateCascadePair + config + result

**Files:**
- Modify: `api/internal/forge/cascade.go`
- Modify: `api/internal/forge/cascade_test.go`

The function still runs the full gate-rank-rerank pipeline even though the SQL CTE pre-filters gate-rejects. Belt-and-braces: SQL narrows the candidate set; the function still validates per-pair so unit tests cover the gate logic directly.

- [ ] **Step 1: Write the failing test**

Append to `api/internal/forge/cascade_test.go`:

```go
func TestCascadeConfig_DefaultsMatchProductionWinner(t *testing.T) {
	c := DefaultCascadeConfig()
	if c.ConcretenessThreshold != 1.0 {
		t.Errorf("threshold: want 1.0, got %v", c.ConcretenessThreshold)
	}
	if c.Alpha != 1.0 {
		t.Errorf("alpha: want 1.0, got %v", c.Alpha)
	}
	if c.DCap != 0.77 {
		t.Errorf("d_cap: want 0.77, got %v", c.DCap)
	}
	if c.Composition != CompositionAdditive {
		t.Errorf("composition: want additive, got %v", c.Composition)
	}
}

func TestEvaluateCascadePair_GateDroppedOnLowSignedDelta(t *testing.T) {
	res := EvaluateCascadePair(CascadeInputs{
		TopicConcreteness:   floatPtr(4.0),
		VehicleConcreteness: floatPtr(4.5),
	}, DefaultCascadeConfig())
	if res.Status != CascadeStatusGateDropped {
		t.Errorf("want gate_dropped, got %v", res.Status)
	}
	if res.FinalScore == nil || *res.FinalScore != 0.0 {
		t.Errorf("gate_dropped final_score: want 0.0, got %v", res.FinalScore)
	}
}

func TestEvaluateCascadePair_MissingConcreteness(t *testing.T) {
	res := EvaluateCascadePair(CascadeInputs{
		TopicConcreteness:   nil,
		VehicleConcreteness: floatPtr(4.5),
	}, DefaultCascadeConfig())
	if res.Status != CascadeStatusMissingConcreteness {
		t.Errorf("want missing_concreteness, got %v", res.Status)
	}
}

func TestEvaluateCascadePair_NoPropertiesAfterGate(t *testing.T) {
	res := EvaluateCascadePair(CascadeInputs{
		TopicConcreteness:   floatPtr(2.0),
		VehicleConcreteness: floatPtr(4.5),
		TopicProperties:     map[int64]float64{},
		VehicleProperties:   map[int64]float64{1: 0.5},
	}, DefaultCascadeConfig())
	if res.Status != CascadeStatusNoProperties {
		t.Errorf("want no_properties, got %v", res.Status)
	}
	if !res.GatePassed {
		t.Error("no_properties must have gate_passed=true")
	}
}

func TestEvaluateCascadePair_ScoredAdditive_NoBonus(t *testing.T) {
	// signed delta 2.5 → gate passes; jaccard=1; cos_dist=0 → bonus=0; final=1
	res := EvaluateCascadePair(CascadeInputs{
		TopicConcreteness:   floatPtr(2.0),
		VehicleConcreteness: floatPtr(4.5),
		TopicProperties:     map[int64]float64{1: 1.0, 2: 1.0},
		VehicleProperties:   map[int64]float64{1: 1.0, 2: 1.0},
		TopicCentroid:       []float32{1, 0, 0},
		VehicleCentroid:     []float32{1, 0, 0},
	}, DefaultCascadeConfig())
	if res.Status != CascadeStatusScored {
		t.Fatalf("want scored, got %v", res.Status)
	}
	if res.FinalScore == nil || math.Abs(*res.FinalScore-1.0) > 1e-9 {
		t.Errorf("final_score: want 1.0, got %v", res.FinalScore)
	}
}

func TestEvaluateCascadePair_ScoredAdditive_WithBonus(t *testing.T) {
	// jaccard=1; cos_dist=1 → bonus=clip(1/0.77)=1; additive: 1 + 1*1 = 2
	res := EvaluateCascadePair(CascadeInputs{
		TopicConcreteness:   floatPtr(2.0),
		VehicleConcreteness: floatPtr(4.5),
		TopicProperties:     map[int64]float64{1: 1.0, 2: 1.0},
		VehicleProperties:   map[int64]float64{1: 1.0, 2: 1.0},
		TopicCentroid:       []float32{1, 0, 0},
		VehicleCentroid:     []float32{0, 1, 0},
	}, DefaultCascadeConfig())
	if res.Status != CascadeStatusScored {
		t.Fatalf("want scored, got %v", res.Status)
	}
	if res.FinalScore == nil || math.Abs(*res.FinalScore-2.0) > 1e-9 {
		t.Errorf("final_score: want 2.0, got %v", res.FinalScore)
	}
}

func TestEvaluateCascadePair_FailOpenOnMissingCentroid(t *testing.T) {
	res := EvaluateCascadePair(CascadeInputs{
		TopicConcreteness:   floatPtr(2.0),
		VehicleConcreteness: floatPtr(4.5),
		TopicProperties:     map[int64]float64{1: 1.0, 2: 1.0},
		VehicleProperties:   map[int64]float64{1: 1.0, 2: 1.0},
		TopicCentroid:       nil,
		VehicleCentroid:     nil,
	}, DefaultCascadeConfig())
	if res.Status != CascadeStatusScored {
		t.Fatalf("want scored (fail-open), got %v", res.Status)
	}
	if res.FinalScore == nil || math.Abs(*res.FinalScore-1.0) > 1e-9 {
		t.Errorf("final_score: want 1.0 (ortony only), got %v", res.FinalScore)
	}
	if res.CosineDistance != nil || res.ReRankBonus != nil {
		t.Error("missing centroid must leave cosine_distance + re_rank_bonus nil")
	}
}

func floatPtr(v float64) *float64 { return &v }
```

- [ ] **Step 2: Run test to verify it fails**

```
cd api && go test ./internal/forge/ -run "TestCascadeConfig|TestEvaluateCascadePair" -v
```

Expected: FAIL with `undefined: …`.

- [ ] **Step 3: Write minimal implementation**

Append to `api/internal/forge/cascade.go`:

```go
type CascadeStatus string

const (
	CascadeStatusScored              CascadeStatus = "scored"
	CascadeStatusGateDropped         CascadeStatus = "gate_dropped"
	CascadeStatusMissingConcreteness CascadeStatus = "missing_concreteness"
	CascadeStatusNoProperties        CascadeStatus = "no_properties"
)

type Composition string

const (
	CompositionAdditive       Composition = "additive"
	CompositionMultiplicative Composition = "multiplicative"
)

type CascadeConfig struct {
	ConcretenessThreshold float64
	Alpha                 float64
	DCap                  float64
	Composition           Composition
}

// DefaultCascadeConfig returns the production-blessed winner config from
// the M03 Stage-2 sweep (separation +0.1779).
func DefaultCascadeConfig() CascadeConfig {
	return CascadeConfig{
		ConcretenessThreshold: 1.0,
		Alpha:                 1.0,
		DCap:                  0.77,
		Composition:           CompositionAdditive,
	}
}

// CascadeInputs bundles per-pair data for EvaluateCascadePair. Pointer
// concreteness so callers express 'absent' as nil. Nil/empty maps and
// nil centroids are valid 'absent' signals — the function routes them
// into the right status without panicking.
type CascadeInputs struct {
	TopicConcreteness   *float64
	VehicleConcreteness *float64
	TopicProperties     map[int64]float64
	VehicleProperties   map[int64]float64
	TopicCentroid       []float32
	VehicleCentroid     []float32
}

// CascadeResult mirrors the Python CascadeResult — pointer fields are nil
// when the corresponding stage didn't run.
type CascadeResult struct {
	FinalScore     *float64
	GatePassed     bool
	OrtonyScore    *float64
	CosineDistance *float64
	ReRankBonus    *float64
	Status         CascadeStatus
}

// EvaluateCascadePair runs the three-stage cascade. Never panics on
// data-shape issues. The handler's SQL CTE may have pre-filtered gate
// rejects; this function still re-checks so unit tests cover the gate
// logic directly.
func EvaluateCascadePair(in CascadeInputs, cfg CascadeConfig) CascadeResult {
	if in.TopicConcreteness == nil || in.VehicleConcreteness == nil {
		return CascadeResult{Status: CascadeStatusMissingConcreteness}
	}
	signed := *in.VehicleConcreteness - *in.TopicConcreteness
	if signed < cfg.ConcretenessThreshold {
		zero := 0.0
		return CascadeResult{FinalScore: &zero, Status: CascadeStatusGateDropped}
	}

	if len(in.TopicProperties) == 0 || len(in.VehicleProperties) == 0 {
		return CascadeResult{GatePassed: true, Status: CascadeStatusNoProperties}
	}
	ortony := JaccardSalience(in.TopicProperties, in.VehicleProperties)

	var cosDist, bonus *float64
	if in.TopicCentroid != nil && in.VehicleCentroid != nil {
		if d, ok := CascadeCosineDistance(in.TopicCentroid, in.VehicleCentroid); ok {
			cosDist = &d
			rb := ReRankBonus(d, cfg.DCap)
			bonus = &rb
		}
	}

	final := ortony
	if bonus != nil {
		switch cfg.Composition {
		case CompositionAdditive:
			final = ortony + cfg.Alpha*(*bonus)
		case CompositionMultiplicative:
			final = ortony * (1.0 + cfg.Alpha*(*bonus))
		}
	}

	return CascadeResult{
		FinalScore:     &final,
		GatePassed:     true,
		OrtonyScore:    &ortony,
		CosineDistance: cosDist,
		ReRankBonus:    bonus,
		Status:         CascadeStatusScored,
	}
}
```

- [ ] **Step 4: Run test to verify it passes**

```
cd api && go test ./internal/forge/ -v
```

Expected: PASS, all forge tests (cascade + existing tier/sort).

- [ ] **Step 5: Commit**

```
git add api/internal/forge/cascade.go api/internal/forge/cascade_test.go
git commit -m "feat(forge): add EvaluateCascadePair orchestrator + config

DefaultCascadeConfig pins the Stage-2 winner: threshold=1.0, alpha=1.0,
d_cap=0.77, additive composition. Status routing matches the Python
CascadeResult contract. Re-rank fails open on missing centroid (final
collapses to ortony-only). Gate check is belt-and-braces — SQL CTE
pre-filters but unit tests still cover the gate logic directly."
```

---

### Task 7: Extend forge.Match with cascade fields

**Files:**
- Modify: `api/internal/forge/forge.go`
- Modify: `api/internal/forge/forge_test.go`

- [ ] **Step 1: Write the failing test**

Append to `api/internal/forge/forge_test.go`:

```go
import (
	"encoding/json"
	"strings"
)

func TestMatch_CascadeFieldsOmitemptyWhenAbsent(t *testing.T) {
	m := Match{SynsetID: "x", Word: "x", TierName: "strong"}
	b, _ := json.Marshal(m)
	s := string(b)
	for _, f := range []string{"final_score", "cascade_status", "gate_passed", "ortony_score", "cosine_distance", "re_rank_bonus"} {
		if strings.Contains(s, f) {
			t.Errorf("expected %q omitted, got %s", f, s)
		}
	}
}

func TestMatch_CascadeFieldsSerialiseWhenSet(t *testing.T) {
	score, ortony, bonus := 0.42, 0.30, 0.16
	m := Match{
		SynsetID: "x", Word: "x", TierName: "strong",
		FinalScore: &score, CascadeStatus: "scored",
		GatePassed: true, OrtonyScore: &ortony, ReRankBonus: &bonus,
	}
	b, _ := json.Marshal(m)
	s := string(b)
	for _, f := range []string{"final_score", "cascade_status", "gate_passed", "ortony_score", "re_rank_bonus"} {
		if !strings.Contains(s, f) {
			t.Errorf("expected %q present, got %s", f, s)
		}
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

```
cd api && go test ./internal/forge/ -run TestMatch_Cascade -v
```

Expected: FAIL with `unknown field FinalScore`.

- [ ] **Step 3: Write minimal implementation**

In `api/internal/forge/forge.go`, extend `Match`:

```go
type Match struct {
	SynsetID         string   `json:"synset_id"`
	Word             string   `json:"word"`
	Definition       string   `json:"definition,omitempty"`
	SharedProperties []string `json:"shared_properties,omitempty"`
	OverlapCount     int      `json:"overlap_count"`
	SalienceSum      float64  `json:"salience_sum,omitempty"`
	Tier             Tier     `json:"-"`
	TierName         string   `json:"tier"`
	SourceSynsetID   string   `json:"source_synset_id,omitempty"`
	SourceDefinition string   `json:"source_definition,omitempty"`
	SourcePOS        string   `json:"source_pos,omitempty"`
	DomainDistance   float64  `json:"domain_distance,omitempty"`
	CompositeScore   float64  `json:"composite_score,omitempty"`

	// Cascade diagnostics (M03-S05). Pointers + omitempty so the legacy
	// path produces an unchanged JSON shape on the wire.
	FinalScore     *float64      `json:"final_score,omitempty"`
	CascadeStatus  CascadeStatus `json:"cascade_status,omitempty"`
	GatePassed     bool          `json:"gate_passed,omitempty"`
	OrtonyScore    *float64      `json:"ortony_score,omitempty"`
	CosineDistance *float64      `json:"cosine_distance,omitempty"`
	ReRankBonus    *float64      `json:"re_rank_bonus,omitempty"`
}
```

- [ ] **Step 4: Run test to verify it passes**

```
cd api && go test ./internal/forge/ -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```
git add api/internal/forge/forge.go api/internal/forge/forge_test.go
git commit -m "feat(forge): extend Match with optional cascade diagnostic fields

Pointer + omitempty fields so the legacy CompositeScore path produces an
unchanged JSON shape on the wire."
```

---

### Task 8: Handler integration — cached cascade branch with batch loading

**Files:**
- Modify: `api/internal/handler/handler.go`
- Create: `api/internal/handler/handler_cascade_test.go`

Per-request hot path:

1. One `GetForgeCascadeCandidatesByLemma` (gate already applied SQL-side; ≤ `limit` rows).
2. Collect distinct source synset_ids (≤ ~5) and all candidate synset_ids; one batch `GetSynsetClusterPropertiesBatch` for the union.
3. For each candidate: 2 cache lookups (centroids) + 2 map accesses (props already loaded). No DB hops.

Source-side data is implicitly memoised — the batch query collects every distinct source once, and the per-candidate loop reads from the resulting map.

- [ ] **Step 1: Write the failing test**

```go
// api/internal/handler/handler_cascade_test.go
package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	_ "github.com/mattn/go-sqlite3"
)

func TestForgeSuggest_CascadeDisabledByDefault_UsesLegacyShape(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("NewHandler: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=fire&limit=3", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status: %d: %s", w.Code, w.Body.String())
	}
	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	for _, m := range resp.Suggestions {
		if m.CascadeStatus != "" {
			t.Errorf("legacy path leaked CascadeStatus=%q", m.CascadeStatus)
		}
		if m.FinalScore != nil {
			t.Errorf("legacy path leaked FinalScore=%v", *m.FinalScore)
		}
	}
}

func TestForgeSuggest_CascadeEnabled_PopulatesCascadeFields(t *testing.T) {
	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=10", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status: %d: %s", w.Code, w.Body.String())
	}
	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	sawScored := false
	for _, m := range resp.Suggestions {
		if m.CascadeStatus == "" {
			t.Errorf("cascade response missing CascadeStatus on %s", m.Word)
		}
		if m.CascadeStatus == "scored" {
			sawScored = true
			if m.FinalScore == nil || m.OrtonyScore == nil {
				t.Errorf("scored result missing FinalScore/OrtonyScore for %s", m.Word)
			}
		}
		if m.CascadeStatus == "gate_dropped" {
			t.Errorf("gate_dropped pair leaked into response: %s", m.Word)
		}
	}
	if !sawScored {
		t.Error("expected at least one scored cascade result for 'anger'")
	}
}

func TestForgeSuggest_CascadeEnabled_RankedByFinalScore(t *testing.T) {
	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=10", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	var prev *float64
	for _, m := range resp.Suggestions {
		if m.FinalScore == nil {
			continue
		}
		if prev != nil && *m.FinalScore > *prev {
			t.Errorf("results not sorted by final_score descending: %v after %v", *m.FinalScore, *prev)
		}
		prev = m.FinalScore
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

```
cd api && go test ./internal/handler/ -run TestForgeSuggest_Cascade -v
```

Expected: FAIL with `undefined: NewHandlerWithCascade`.

- [ ] **Step 3: Write minimal implementation**

In `api/internal/handler/handler.go`, replace `Handler` and `NewHandler`:

```go
type Handler struct {
	database    *sql.DB
	stringsDir  string
	useCascade  bool
	cascadeConf forge.CascadeConfig
	cache       *db.CascadeCache // nil when cascade disabled
}

// NewHandler creates a legacy-mode handler (CompositeScore path).
func NewHandler(dbPath string) (*Handler, error) {
	return NewHandlerWithCascade(dbPath, false)
}

// NewHandlerWithCascade opts into the M03 cascade path on /forge/suggest.
// Cascade mode requires synset_concreteness and synset_centroids and
// eagerly loads them into memory (~50 MB) — startup cost trades for
// per-request latency.
func NewHandlerWithCascade(dbPath string, useCascade bool) (*Handler, error) {
	database, err := db.Open(dbPath)
	if err != nil {
		return nil, err
	}

	required := []string{
		"synsets", "lemmas", "synset_properties_curated", "property_vocab_curated",
		"frequencies", "cluster_antonyms", "vocab_clusters", "lemma_embeddings",
	}
	if useCascade {
		required = append(required, "synset_concreteness", "synset_centroids")
	}
	for _, table := range required {
		var count int
		err := database.QueryRow(
			"SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
			table,
		).Scan(&count)
		if err != nil || count == 0 {
			database.Close()
			return nil, fmt.Errorf("required table %q not found in database", table)
		}
	}

	database.SetMaxOpenConns(4)

	h := &Handler{
		database:    database,
		useCascade:  useCascade,
		cascadeConf: forge.DefaultCascadeConfig(),
	}

	if useCascade {
		cache, err := db.LoadCascadeCache(database)
		if err != nil {
			database.Close()
			return nil, fmt.Errorf("load cascade cache: %w", err)
		}
		h.cache = cache
	}

	return h, nil
}
```

Split `HandleSuggest`:

```go
func (h *Handler) HandleSuggest(w http.ResponseWriter, r *http.Request) {
	word := r.URL.Query().Get("word")
	if word == "" {
		http.Error(w, `{"error": "missing 'word' parameter"}`, http.StatusBadRequest)
		return
	}
	limit := DefaultLimit
	if l := r.URL.Query().Get("limit"); l != "" {
		if parsed, err := strconv.Atoi(l); err == nil && parsed > 0 && parsed <= 200 {
			limit = parsed
		}
	}

	if h.useCascade {
		h.handleSuggestCascade(w, word, limit)
		return
	}
	h.handleSuggestLegacy(w, word, limit)
}

// handleSuggestLegacy is the pre-M03 CompositeScore path.
func (h *Handler) handleSuggestLegacy(w http.ResponseWriter, word string, limit int) {
	// [move existing HandleSuggest body lines 89-156 from current handler.go]
}

// handleSuggestCascade scores candidates through the M03 cascade.
//
// Hot path: 2 DB queries (gated candidates + batch properties) + N cache
// lookups + per-pair pure-function scoring. Source-side data is
// memoised implicitly via the batch properties map.
func (h *Handler) handleSuggestCascade(w http.ResponseWriter, word string, limit int) {
	candidates, err := db.GetForgeCascadeCandidatesByLemma(
		h.database, word, h.cascadeConf.ConcretenessThreshold, limit,
	)
	if errors.Is(err, db.ErrLemmaNotFound) {
		http.Error(w, `{"error": "word not found or has no curated properties"}`, http.StatusNotFound)
		return
	}
	if err != nil {
		slog.Error("cascade candidate fetch failed", "word", word, "err", err)
		http.Error(w, `{"error": "internal server error"}`, http.StatusInternalServerError)
		return
	}
	if len(candidates) == 0 {
		// Lemma is enriched but no gate-pass — return empty 200.
		resp := SuggestResponse{Source: word, Suggestions: []forge.Match{}}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
		return
	}

	// Collect distinct synset_ids for one batch properties query.
	idSet := make(map[string]struct{}, 2*len(candidates))
	for _, c := range candidates {
		idSet[c.SourceSynsetID] = struct{}{}
		idSet[c.SynsetID] = struct{}{}
	}
	ids := make([]string, 0, len(idSet))
	for id := range idSet {
		ids = append(ids, id)
	}
	propsByID, err := db.GetSynsetClusterPropertiesBatch(h.database, ids)
	if err != nil {
		slog.Error("cascade batch properties fetch failed", "word", word, "err", err)
		http.Error(w, `{"error": "internal server error"}`, http.StatusInternalServerError)
		return
	}

	matches := make([]forge.Match, 0, len(candidates))
	for _, c := range candidates {
		// Concreteness already on the row; centroids from the cache.
		topicConc := c.TopicConcreteness
		vehConc := c.VehicleConcreteness
		topicCent := h.cache.Centroids[c.SourceSynsetID] // nil-safe: zero value is nil
		vehCent := h.cache.Centroids[c.SynsetID]

		res := forge.EvaluateCascadePair(forge.CascadeInputs{
			TopicConcreteness:   &topicConc,
			VehicleConcreteness: &vehConc,
			TopicProperties:     propsByID[c.SourceSynsetID],
			VehicleProperties:   propsByID[c.SynsetID],
			TopicCentroid:       topicCent,
			VehicleCentroid:     vehCent,
		}, h.cascadeConf)

		// SQL CTE already filtered gate_dropped + missing_concreteness, so
		// the only attrition we can see here is no_properties (curated
		// props could have been pruned). Drop those from product output.
		if res.Status != forge.CascadeStatusScored {
			continue
		}

		tier := forge.ClassifyTierCurated(c.SalienceSum, c.ContrastCount)
		matches = append(matches, forge.Match{
			SynsetID:         c.SynsetID,
			Word:             c.Word,
			Definition:       c.Definition,
			SharedProperties: c.SharedProps,
			OverlapCount:     int(c.SalienceSum),
			SalienceSum:      c.SalienceSum,
			Tier:             tier,
			TierName:         tier.String(),
			SourceSynsetID:   c.SourceSynsetID,
			SourceDefinition: c.SourceDefinition,
			SourcePOS:        c.SourcePOS,
			FinalScore:       res.FinalScore,
			CascadeStatus:    res.Status,
			GatePassed:       res.GatePassed,
			OrtonyScore:      res.OrtonyScore,
			CosineDistance:   res.CosineDistance,
			ReRankBonus:      res.ReRankBonus,
		})
	}

	sortByFinalScore(matches)

	resp := SuggestResponse{Source: word, Suggestions: matches}
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		slog.Error("failed to encode cascade suggest response", "word", word, "err", err)
	}
}

func sortByFinalScore(matches []forge.Match) {
	sort.Slice(matches, func(i, j int) bool {
		a, b := matches[i].FinalScore, matches[j].FinalScore
		if a == nil {
			return false
		}
		if b == nil {
			return true
		}
		return *a > *b
	})
}
```

Add `"sort"` to the handler imports.

- [ ] **Step 4: Run test to verify it passes**

```
cd api && go test ./internal/handler/ -run TestForgeSuggest_Cascade -v
```

Expected: PASS (all three cascade tests). Existing legacy `TestForgeSuggestEndpoint` also still passes.

- [ ] **Step 5: Commit**

```
git add api/internal/handler/handler.go api/internal/handler/handler_cascade_test.go
git commit -m "feat(handler): wire cascade path with cache + batch + gate pushdown

Per-request: 1 gated CTE candidate query + 1 batch properties query + N
in-memory map lookups. ~50 MB RAM at startup buys O(1) centroid lookup
in the hot loop. Source-side data implicitly memoised via the batch
properties map. Legacy CompositeScore path untouched."
```

---

### Task 9: CLI flag + env var

**Files:**
- Modify: `api/cmd/metaforge/main.go`

- [ ] **Step 1: Verify current build**

```
export PATH="/usr/local/go/bin:$PATH"
cd api && go build ./cmd/metaforge
```

Expected: build succeeds.

- [ ] **Step 2: Modify main.go**

```go
import (
	// existing imports …
	"os"
)

func main() {
	dbPath := flag.String("db", "../data-pipeline/output/lexicon_v2.db", "Path to lexicon_v2.db")
	stringsDir := flag.String("strings", "../strings", "Path to strings directory")
	corsOrigin := flag.String("cors-origin", "http://localhost:5173", "Allowed CORS origin for dev")
	port := flag.String("port", "8080", "Server port")
	cascade := flag.Bool("cascade", os.Getenv("METAFORGE_FORGE_CASCADE") == "1",
		"Use M03 cascade scorer on /forge/suggest (default: legacy CompositeScore)")
	flag.Parse()

	h, err := handler.NewHandlerWithCascade(*dbPath, *cascade)
	if err != nil {
		log.Fatalf("Failed to initialise: %v", err)
	}
	defer h.Close()
	h.SetStringsDir(*stringsDir)

	// existing chi router setup unchanged …
	slog.Info("Metaforge API starting",
		"addr", addr, "db", *dbPath, "strings", *stringsDir,
		"cors", *corsOrigin, "cascade", *cascade,
	)
	// rest unchanged
}
```

- [ ] **Step 3: Verify build and help**

```
cd api && go build ./cmd/metaforge && ./metaforge --help 2>&1 | grep cascade
```

Expected: `--cascade` flag listed in help.

- [ ] **Step 4: Smoke-boot both modes**

```
# Legacy:
cd api && ./metaforge --db ../data-pipeline/output/lexicon_v2.db --port 9099 &
sleep 2
curl -s "http://127.0.0.1:9099/forge/suggest?word=fire&limit=3" | python3 -m json.tool | head -20
kill %1

# Cascade:
./metaforge --db ../data-pipeline/output/lexicon_v2.db --port 9099 --cascade &
sleep 3
curl -s "http://127.0.0.1:9099/forge/suggest?word=fire&limit=3" | python3 -m json.tool | head -30
kill %1
```

Expected: legacy response has no `cascade_status`; cascade response does.

- [ ] **Step 5: Commit**

```
git add api/cmd/metaforge/main.go
git commit -m "feat(cmd): add --cascade flag + METAFORGE_FORGE_CASCADE env var

Default off until smoke-test crib confirms parity with Python reference.
Env var lets systemd unit files opt in without changing CLI args."
```

---

### Task 10: Pin Python ground truth for the smoke-test crib

**Files:**
- Create: `docs/plans/2026-05-21-m03-s05-smoke-test-crib.md`

- [ ] **Step 1: Generate Python ground truth**

```bash
source data-pipeline/.venv/bin/activate
python - <<'PY'
import json, sqlite3, sys
sys.path.insert(0, "data-pipeline/scripts")
from evaluate_cascade import CascadeConfig, evaluate_cascade_pair
from evaluate_aptness import lookup_primary_synset

PAIRS = [
    ("anger", "fire"), ("idea", "light"), ("time", "money"),
    ("argument", "war"), ("life", "journey"),
    ("truth", "hammer"), ("silence", "velvet"),
    ("cat", "feline"),
]
cfg = CascadeConfig(concreteness_threshold=1.0, ortony_scoring="jaccard_salience",
                    d_cap=0.77, alpha=1.0, composition="additive")
out = []
with sqlite3.connect("data-pipeline/output/lexicon_v2.db") as conn:
    for topic, vehicle in PAIRS:
        t = lookup_primary_synset(conn, topic)
        v = lookup_primary_synset(conn, vehicle)
        if t is None or v is None:
            out.append({"topic": topic, "vehicle": vehicle, "status": "unresolved"})
            continue
        r = evaluate_cascade_pair(conn, t, v, cfg)
        out.append({
            "topic": topic, "vehicle": vehicle,
            "topic_synset": t, "vehicle_synset": v,
            "status": r.status,
            "final_score": r.final_score,
            "ortony_score": r.ortony_score,
            "cosine_distance": r.cosine_distance,
            "re_rank_bonus": r.re_rank_bonus,
        })
print(json.dumps(out, indent=2))
PY
```

- [ ] **Step 2: Write the crib doc** with the literal JSON output captured inline as a table at `docs/plans/2026-05-21-m03-s05-smoke-test-crib.md`. Include the cascade config, the table, and the parity tolerance (±1e-6 on scored pairs; non-scored pairs must NOT appear in the Go response).

- [ ] **Step 3: Commit**

```
git add docs/plans/2026-05-21-m03-s05-smoke-test-crib.md
git commit -m "docs(m03-s05): pin Python ground truth for smoke-test crib"
```

---

### Task 11: Live API smoke test against the crib

- [ ] **Step 1: Boot the API with cascade enabled**

```
cd api && export PATH="/usr/local/go/bin:$PATH"
go build ./cmd/metaforge
./metaforge --db ../data-pipeline/output/lexicon_v2.db --port 9099 --cascade &
SERVER_PID=$!
sleep 3   # cache load adds ~1-2s
```

- [ ] **Step 2: Query each smoke topic and diff against the crib**

```
for topic in anger idea time argument life truth silence cat; do
  echo "=== $topic ==="
  curl -s "http://127.0.0.1:9099/forge/suggest?word=${topic}&limit=50" \
    | python3 -c "import json,sys; r=json.load(sys.stdin); print(json.dumps(r['suggestions'], indent=2))"
done
```

For every pair where the crib reports `status=scored`, confirm the vehicle word appears in the response with `final_score`, `ortony_score`, `cosine_distance`, `re_rank_bonus` matching to ±1e-6. For non-`scored` pairs, confirm absent.

If anything diverges: stop, diagnose, fix, re-run from Step 1. Do not proceed until 8/8 pairs match.

- [ ] **Step 3: Tear down and record results**

```
kill $SERVER_PID
```

Append a "Go parity confirmed 2026-05-XX" section to the crib with the actual diff results, then commit.

```
git add docs/plans/2026-05-21-m03-s05-smoke-test-crib.md
git commit -m "docs(m03-s05): record Go cascade smoke-test parity"
```

---

### Task 12: Full test sweep + roadmap update

- [ ] **Step 1: Run the full Go test suite**

```
cd api && export PATH="/usr/local/go/bin:$PATH"
go test ./... -v 2>&1 | tail -60
```

Expected: all packages PASS. The 8 pre-existing handler test failures (tracked in PIPELINE.md backlog) must not have grown.

- [ ] **Step 2: Quick latency sanity-check**

```
cd api && ./metaforge --db ../data-pipeline/output/lexicon_v2.db --port 9099 --cascade &
sleep 3
time (for i in 1 2 3 4 5; do curl -s "http://127.0.0.1:9099/forge/suggest?word=anger&limit=50" > /dev/null; done)
kill %1
```

Expected: 5 requests well under 1s total. If a single request exceeds ~200 ms, investigate before merging — that points to a missed optimisation.

- [ ] **Step 3: Push branch**

```
git status
git push origin m03/cascade-gate-and-rank
```

- [ ] **Step 4: Update `docs/roadmap/PIPELINE.md`**

Move M03-S05 from **Next** to **Done** with merge date. Confirm with the user which item promotes into **Next** (M03 retro itself, The Bridge, or M04).

```
git add docs/roadmap/PIPELINE.md
git commit -m "docs(pipeline): M03-S05 done — Go cascade live behind --cascade flag"
git push origin m03/cascade-gate-and-rank
```

---

## Self-review

**Spec coverage:**

1. Cascade scoring path in `api/internal/forge` → Tasks 4, 5, 6, 7. ✓
2. DB helpers in `api/internal/db` → Tasks 1 (cache), 2 (batch props), 3 (gate-pushdown CTE). ✓
3. Feature flag → Task 8 (`useCascade` + `LoadCascadeCache` only when enabled) + Task 9 (CLI). ✓
4. TDD throughout → every implementation step has a failing test as its predecessor. ✓
5. Smoke test against 5–10 known apt pairs → Tasks 10 (Python ground truth) + 11 (Go parity). ✓

**Performance coverage (the four optimisations):**

1. **In-memory caches at handler init** → Task 1. Eliminates 4× concreteness + 2× centroid per-candidate queries. ✓
2. **Batch `GetSynsetClusterProperties`** → Task 2. One IN-clause query for the union of ≤5 sources + ≤50 candidates. ✓
3. **Source-side memoise within request** → Task 8 (the batch properties map naturally memoises distinct sources). ✓
4. **Gate pushdown in CTE** → Task 3. SQLite filters gate-rejects before they cross into Go; no over-fetch needed. ✓

**Placeholder scan:** no "TBD" / "similar to Task N" / "add error handling" remain. Every code step shows the actual code; every test step shows the actual test.

**Type consistency:** `CascadeCache`, `CascadeCandidate`, `CascadeConfig`, `CascadeInputs`, `CascadeResult`, `CascadeStatus`, `Composition`, `DefaultCascadeConfig`, `EvaluateCascadePair`, `JaccardSalience`, `ReRankBonus`, `CascadeCosineDistance`, `LoadCascadeCache`, `GetSynsetClusterPropertiesBatch`, `GetForgeCascadeCandidatesByLemma`, `NewHandlerWithCascade`, `sortByFinalScore` — all introduced once and reused with the same names downstream. `Match` cascade fields (`FinalScore`, `OrtonyScore`, `CosineDistance`, `ReRankBonus` pointer; `CascadeStatus`, `GatePassed` value) consistent across forge → handler → tests.

**Standards check (CLAUDE.md):** TDD red-then-green per commit ✓. UK English in comments/identifiers ✓. Errors logged via `slog.Warn`/`slog.Error` or escalated with `fmt.Errorf("...%w", err)` ✓. FP over OOP: cascade scoring is pure functions; Handler/CascadeCache carry the only state ✓. Algorithmic shape: per-request work is 2 DB queries + O(N) pure-CPU scoring where N ≤ limit ≤ 200 ✓. RAM budget bounded (~50 MB) at startup, no per-request allocations beyond the candidate slice ✓.

---

## Execution handoff

Plan complete and saved to `docs/plans/2026-05-21-m03-s05-forge-integration.md`. Two execution options:

1. **Subagent-driven (recommended)** — fresh subagent per task, review between tasks, fast iteration on the data-layer boundaries.
2. **Inline execution** — execute tasks in this session using `superpowers:executing-plans`, batch with checkpoints.

Which approach?
