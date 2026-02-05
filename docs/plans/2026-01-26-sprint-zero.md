# Sprint Zero Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Go API serving `/forge/suggest` endpoint using `lexicon_v2.db` (from Sch2 pipeline) to power the Metaphor Forge feature.

**Architecture:** `lexicon_v2.db` contains OEWN synsets, VerbNet roles, SyntagNet collocations, and LLM-extracted properties with FastText 300d embeddings. Go API queries the normalised schema (synset_properties junction table) to find synsets sharing properties, then ranks by semantic distance.

**Tech Stack:** Go 1.21+ (API), SQLite (lexicon_v2.db), FastText 300d embeddings (property_vocabulary.embedding)

**Data Source:** `data-pipeline/output/lexicon_v2.db` — populated by Sch2 pipeline with:
- 107k synsets, 185k lemmas, 234k relations
- 5k curated properties with FastText 300d embeddings
- 2k pilot-enriched synsets with 17k synset-property links
- 609 VerbNet classes, 87k SyntagNet collocations

---

## Prerequisites

The Sch2 pipeline has already populated:

| Table | Count | Purpose |
|-------|-------|---------|
| synsets | 107,519 | OEWN word senses |
| lemmas | 185,081 | Word-to-synset mappings |
| property_vocabulary | 5,066 | Curated properties with embeddings |
| synset_properties | 17,011 | Synset-property links (junction) |
| enrichment | 1,967 | Enriched synsets (pilot) |
| syntagms | 87,265 | SyntagNet collocations |
| vn_classes | 609 | VerbNet verb classes |

**Venv:** Use sprint-zero venv for any Python scripts:
```bash
/home/msi/projects/metaforge/.worktrees/sprint-zero/data-pipeline/.venv/bin/python <script>
```

---

## Task 1: Update Go DB Layer for lexicon_v2.db Schema

**Files:**
- Modify: `api/internal/db/db.go`
- Modify: `api/internal/db/db_test.go`

The existing db.go expects JSON properties column. The new schema uses junction table `synset_properties` → `property_vocabulary`.

### Step 1.1: Write failing test for new schema

Update `api/internal/db/db_test.go` to use `lexicon_v2.db`:

```go
// api/internal/db/db_test.go
package db

import (
	"testing"
)

const testDBPath = "../../../data-pipeline/output/lexicon_v2.db"

func TestOpenDatabase(t *testing.T) {
	db, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	var count int
	err = db.QueryRow("SELECT COUNT(*) FROM synsets").Scan(&count)
	if err != nil {
		t.Fatalf("Failed to query synsets: %v", err)
	}

	if count < 100000 {
		t.Errorf("Expected >100k synsets, got %d", count)
	}
}

func TestGetSynsetWithProperties(t *testing.T) {
	db, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// Get a synset that has properties in the junction table
	var synsetID string
	err = db.QueryRow(`
		SELECT DISTINCT sp.synset_id
		FROM synset_properties sp
		LIMIT 1
	`).Scan(&synsetID)
	if err != nil {
		t.Fatalf("No enriched synsets found: %v", err)
	}

	synset, err := GetSynset(db, synsetID)
	if err != nil {
		t.Fatalf("Failed to get synset %s: %v", synsetID, err)
	}

	if synset.ID != synsetID {
		t.Errorf("Expected %s, got %s", synsetID, synset.ID)
	}

	if len(synset.Properties) == 0 {
		t.Error("Expected properties from synset_properties junction table")
	}
}

func TestGetSynsetsWithSharedProperties(t *testing.T) {
	db, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// Find a synset with properties
	var synsetID string
	err = db.QueryRow(`
		SELECT sp.synset_id
		FROM synset_properties sp
		GROUP BY sp.synset_id
		HAVING COUNT(*) >= 3
		LIMIT 1
	`).Scan(&synsetID)
	if err != nil {
		t.Fatalf("No synset with 3+ properties: %v", err)
	}

	matches, err := GetSynsetsWithSharedProperties(db, synsetID)
	if err != nil {
		t.Fatalf("Failed to get shared properties: %v", err)
	}

	if len(matches) == 0 {
		t.Error("Expected at least one match")
	}

	for _, m := range matches {
		if m.SynsetID == "" {
			t.Error("Match has empty synset ID")
		}
		if len(m.SharedProperties) == 0 {
			t.Error("Match has no shared properties")
		}
		if m.OverlapCount != len(m.SharedProperties) {
			t.Errorf("OverlapCount %d doesn't match SharedProperties length %d",
				m.OverlapCount, len(m.SharedProperties))
		}
	}
}

func TestLookupByLemma(t *testing.T) {
	db, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	synsetID, err := GetSynsetIDForLemma(db, "candle")
	if err != nil {
		t.Fatalf("Failed to lookup 'candle': %v", err)
	}

	if synsetID == "" {
		t.Error("Expected synset ID for 'candle'")
	}
}
```

### Step 1.2: Run test to verify it fails

Run: `cd /home/msi/projects/metaforge/.worktrees/sprint-zero/api && go test ./internal/db/... -v`
Expected: FAIL - GetSynsetIDForLemma not defined, queries fail due to schema mismatch

### Step 1.3: Update db.go for junction table schema

Replace `api/internal/db/db.go`:

```go
// Package db provides database access for the Metaforge lexicon.
// It handles retrieval of OEWN synsets with LLM-enriched properties
// from the lexicon_v2.db normalised schema.
package db

import (
	"database/sql"
	"fmt"

	_ "github.com/mattn/go-sqlite3"
)

// Synset represents a WordNet synset with enrichment data.
type Synset struct {
	ID           string   `json:"id"`
	POS          string   `json:"pos"`
	Definition   string   `json:"definition"`
	Properties   []string `json:"properties,omitempty"`
	Connotation  string   `json:"connotation,omitempty"`
	Register     string   `json:"register,omitempty"`
	UsageExample string   `json:"usage_example,omitempty"`
}

// SynsetMatch represents a candidate match with shared properties.
type SynsetMatch struct {
	SynsetID         string   `json:"synset_id"`
	SharedProperties []string `json:"shared_properties"`
	OverlapCount     int      `json:"overlap_count"`
	Distance         float64  `json:"distance"`
	Tier             string   `json:"tier"`
}

// Open establishes a read-only connection to the lexicon SQLite database.
func Open(path string) (*sql.DB, error) {
	return sql.Open("sqlite3", path+"?mode=ro")
}

// GetSynset retrieves a synset by ID with properties from junction table.
func GetSynset(db *sql.DB, synsetID string) (*Synset, error) {
	var s Synset

	// Get synset base data + enrichment metadata
	err := db.QueryRow(`
		SELECT s.synset_id, s.pos, s.definition,
		       e.connotation, e.register, e.usage_example
		FROM synsets s
		LEFT JOIN enrichment e ON s.synset_id = e.synset_id
		WHERE s.synset_id = ?
	`, synsetID).Scan(&s.ID, &s.POS, &s.Definition,
		&s.Connotation, &s.Register, &s.UsageExample)

	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("synset not found: %s", synsetID)
	}
	if err != nil {
		return nil, fmt.Errorf("query failed: %w", err)
	}

	// Get properties from junction table
	rows, err := db.Query(`
		SELECT pv.text
		FROM synset_properties sp
		JOIN property_vocabulary pv ON pv.property_id = sp.property_id
		WHERE sp.synset_id = ?
	`, synsetID)
	if err != nil {
		return nil, fmt.Errorf("failed to query properties: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var prop string
		if err := rows.Scan(&prop); err != nil {
			continue
		}
		s.Properties = append(s.Properties, prop)
	}

	return &s, nil
}

// GetSynsetIDForLemma finds the first synset ID for a given word.
// Prefers synsets that have enrichment data.
func GetSynsetIDForLemma(db *sql.DB, lemma string) (string, error) {
	var synsetID string

	// Prefer enriched synsets
	err := db.QueryRow(`
		SELECT l.synset_id
		FROM lemmas l
		JOIN enrichment e ON e.synset_id = l.synset_id
		WHERE l.lemma = ?
		LIMIT 1
	`, lemma).Scan(&synsetID)

	if err == nil {
		return synsetID, nil
	}

	// Fall back to any synset
	err = db.QueryRow(`
		SELECT synset_id FROM lemmas WHERE lemma = ? LIMIT 1
	`, lemma).Scan(&synsetID)

	if err == sql.ErrNoRows {
		return "", fmt.Errorf("lemma not found: %s", lemma)
	}
	return synsetID, err
}

// GetSynsetsWithSharedProperties finds synsets sharing properties with source.
// Uses the normalised synset_properties junction table for efficient lookup.
func GetSynsetsWithSharedProperties(db *sql.DB, sourceID string) ([]SynsetMatch, error) {
	// Get source synset's property IDs
	sourceProps, err := getPropertyIDs(db, sourceID)
	if err != nil {
		return nil, err
	}
	if len(sourceProps) == 0 {
		return nil, fmt.Errorf("source synset has no properties")
	}

	// Find all synsets sharing at least one property
	// Uses SQL to compute intersection (more efficient than Go-side)
	rows, err := db.Query(`
		SELECT sp.synset_id, pv.text
		FROM synset_properties sp
		JOIN property_vocabulary pv ON pv.property_id = sp.property_id
		WHERE sp.property_id IN (
			SELECT property_id FROM synset_properties WHERE synset_id = ?
		)
		AND sp.synset_id != ?
		ORDER BY sp.synset_id
	`, sourceID, sourceID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	// Group by synset
	matchMap := make(map[string][]string)
	for rows.Next() {
		var id, prop string
		if err := rows.Scan(&id, &prop); err != nil {
			continue
		}
		matchMap[id] = append(matchMap[id], prop)
	}

	// Convert to slice
	var matches []SynsetMatch
	for id, props := range matchMap {
		matches = append(matches, SynsetMatch{
			SynsetID:         id,
			SharedProperties: props,
			OverlapCount:     len(props),
		})
	}

	return matches, nil
}

// getPropertyIDs returns the property_ids for a synset.
func getPropertyIDs(db *sql.DB, synsetID string) ([]int, error) {
	rows, err := db.Query(`
		SELECT property_id FROM synset_properties WHERE synset_id = ?
	`, synsetID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var ids []int
	for rows.Next() {
		var id int
		if err := rows.Scan(&id); err != nil {
			continue
		}
		ids = append(ids, id)
	}
	return ids, nil
}

// GetLemmaForSynset returns the primary lemma for a synset.
func GetLemmaForSynset(db *sql.DB, synsetID string) (string, error) {
	var lemma string
	err := db.QueryRow(`
		SELECT lemma FROM lemmas WHERE synset_id = ? LIMIT 1
	`, synsetID).Scan(&lemma)
	if err == sql.ErrNoRows {
		return "", fmt.Errorf("no lemma for synset: %s", synsetID)
	}
	return lemma, err
}
```

### Step 1.4: Run test to verify it passes

Run: `cd /home/msi/projects/metaforge/.worktrees/sprint-zero/api && go test ./internal/db/... -v`
Expected: PASS

### Step 1.5: Commit

```bash
git add api/internal/db/db.go api/internal/db/db_test.go
git commit -m "$(cat <<'EOF'
refactor: update db layer for lexicon_v2.db junction table schema

- Query synset_properties junction table instead of JSON column
- Add GetSynsetIDForLemma for word-to-synset lookup
- Add GetLemmaForSynset for synset-to-word lookup
- Use SQL-side property intersection for efficiency
- Update tests to use lexicon_v2.db
EOF
)"
```

---

## Task 2: Add Embeddings Layer for FastText 300d

**Files:**
- Create: `api/internal/embeddings/embeddings.go`
- Create: `api/internal/embeddings/embeddings_test.go`

Property embeddings are stored in `property_vocabulary.embedding` as 1200-byte BLOBs (300 float32s). We need to compute cosine distance between property sets.

### Step 2.1: Write failing test for embeddings

Create `api/internal/embeddings/embeddings_test.go`:

```go
// api/internal/embeddings/embeddings_test.go
package embeddings

import (
	"database/sql"
	"testing"

	_ "github.com/mattn/go-sqlite3"
)

const testDBPath = "../../../data-pipeline/output/lexicon_v2.db"

func openTestDB(t *testing.T) *sql.DB {
	db, err := sql.Open("sqlite3", testDBPath+"?mode=ro")
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	return db
}

func TestGetPropertyEmbedding(t *testing.T) {
	db := openTestDB(t)
	defer db.Close()

	emb, err := GetPropertyEmbedding(db, "warm")
	if err != nil {
		t.Fatalf("Failed to get embedding for 'warm': %v", err)
	}

	if len(emb) != 300 {
		t.Errorf("Expected 300 dimensions, got %d", len(emb))
	}
}

func TestCosineDistance(t *testing.T) {
	// Identical vectors should have distance 0
	v := []float32{1, 0, 0}
	dist := CosineDistance(v, v)
	if dist != 0 {
		t.Errorf("Expected distance 0 for identical vectors, got %f", dist)
	}

	// Orthogonal vectors should have distance 1
	v1 := []float32{1, 0, 0}
	v2 := []float32{0, 1, 0}
	dist = CosineDistance(v1, v2)
	if dist != 1 {
		t.Errorf("Expected distance 1 for orthogonal vectors, got %f", dist)
	}
}

func TestComputePropertySetDistance(t *testing.T) {
	db := openTestDB(t)
	defer db.Close()

	// Similar properties should have low distance
	dist, err := ComputePropertySetDistance(db, []string{"warm", "hot"}, []string{"warm", "heated"})
	if err != nil {
		t.Fatalf("Failed to compute distance: %v", err)
	}

	if dist > 0.5 {
		t.Errorf("Expected low distance for similar properties, got %f", dist)
	}
}
```

### Step 2.2: Run test to verify it fails

Run: `cd /home/msi/projects/metaforge/.worktrees/sprint-zero/api && go test ./internal/embeddings/... -v`
Expected: FAIL - package not found

### Step 2.3: Write embeddings layer

Create `api/internal/embeddings/embeddings.go`:

```go
// Package embeddings provides FastText 300d embedding operations
// for property-based semantic similarity.
package embeddings

import (
	"database/sql"
	"encoding/binary"
	"fmt"
	"math"
)

const EmbeddingDim = 300

// GetPropertyEmbedding retrieves the FastText 300d embedding for a property.
func GetPropertyEmbedding(db *sql.DB, property string) ([]float32, error) {
	var blob []byte
	err := db.QueryRow(`
		SELECT embedding FROM property_vocabulary WHERE text = ?
	`, property).Scan(&blob)

	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("property not found: %s", property)
	}
	if err != nil {
		return nil, err
	}
	if blob == nil {
		return nil, fmt.Errorf("property has no embedding (OOV): %s", property)
	}

	return blobToFloats(blob), nil
}

// blobToFloats converts a byte slice to float32 slice.
func blobToFloats(blob []byte) []float32 {
	if len(blob) != EmbeddingDim*4 {
		return nil
	}
	vec := make([]float32, EmbeddingDim)
	for i := 0; i < EmbeddingDim; i++ {
		bits := binary.LittleEndian.Uint32(blob[i*4 : (i+1)*4])
		vec[i] = math.Float32frombits(bits)
	}
	return vec
}

// CosineDistance computes 1 - cosine_similarity between two vectors.
// Returns 0 for identical vectors, 1 for orthogonal, 2 for opposite.
func CosineDistance(a, b []float32) float64 {
	if len(a) != len(b) || len(a) == 0 {
		return 1.0
	}

	var dot, normA, normB float64
	for i := range a {
		dot += float64(a[i] * b[i])
		normA += float64(a[i] * a[i])
		normB += float64(b[i] * b[i])
	}

	if normA == 0 || normB == 0 {
		return 1.0
	}

	similarity := dot / (math.Sqrt(normA) * math.Sqrt(normB))
	return 1.0 - similarity
}

// ComputePropertySetDistance computes average pairwise distance between
// two sets of properties. Lower distance = more similar.
func ComputePropertySetDistance(db *sql.DB, propsA, propsB []string) (float64, error) {
	if len(propsA) == 0 || len(propsB) == 0 {
		return 1.0, nil
	}

	// Get embeddings for all properties
	embsA := make([][]float32, 0, len(propsA))
	for _, p := range propsA {
		emb, err := GetPropertyEmbedding(db, p)
		if err != nil {
			continue // Skip OOV properties
		}
		embsA = append(embsA, emb)
	}

	embsB := make([][]float32, 0, len(propsB))
	for _, p := range propsB {
		emb, err := GetPropertyEmbedding(db, p)
		if err != nil {
			continue
		}
		embsB = append(embsB, emb)
	}

	if len(embsA) == 0 || len(embsB) == 0 {
		return 1.0, nil
	}

	// Compute centroid of each set
	centroidA := computeCentroid(embsA)
	centroidB := computeCentroid(embsB)

	return CosineDistance(centroidA, centroidB), nil
}

// computeCentroid computes the average vector of a set of embeddings.
func computeCentroid(embeddings [][]float32) []float32 {
	if len(embeddings) == 0 {
		return nil
	}

	centroid := make([]float32, len(embeddings[0]))
	for _, emb := range embeddings {
		for i, v := range emb {
			centroid[i] += v
		}
	}

	n := float32(len(embeddings))
	for i := range centroid {
		centroid[i] /= n
	}

	return centroid
}
```

### Step 2.4: Run test to verify it passes

Run: `cd /home/msi/projects/metaforge/.worktrees/sprint-zero/api && go test ./internal/embeddings/... -v`
Expected: PASS

### Step 2.5: Commit

```bash
git add api/internal/embeddings/
git commit -m "$(cat <<'EOF'
feat: add embeddings layer for FastText 300d property similarity

- GetPropertyEmbedding reads 1200-byte BLOBs from property_vocabulary
- CosineDistance computes semantic distance between vectors
- ComputePropertySetDistance uses centroid-based set comparison
- Gracefully handles OOV properties
EOF
)"
```

---

## Task 3: Implement 5-Tier Matching Algorithm

**Files:**
- Create: `api/internal/forge/forge.go`
- Create: `api/internal/forge/forge_test.go`

The Metaphor Forge uses a 5-tier ranking system based on property overlap count and semantic distance.

### Step 3.1: Write failing test for tier classification

Create `api/internal/forge/forge_test.go`:

```go
// api/internal/forge/forge_test.go
package forge

import (
	"testing"
)

func TestClassifyTier(t *testing.T) {
	tests := []struct {
		name     string
		distance float64
		overlap  int
		expected Tier
	}{
		{"legendary - high distance, strong overlap", 0.8, 4, TierLegendary},
		{"interesting - high distance, weak overlap", 0.8, 1, TierInteresting},
		{"strong - high distance, moderate overlap", 0.8, 2, TierStrong},
		{"obvious - low distance, strong overlap", 0.3, 3, TierObvious},
		{"unlikely - low distance, weak overlap", 0.3, 1, TierUnlikely},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			tier := ClassifyTier(tt.distance, tt.overlap)
			if tier != tt.expected {
				t.Errorf("ClassifyTier(%v, %d) = %v, want %v",
					tt.distance, tt.overlap, tier, tt.expected)
			}
		})
	}
}

func TestTierString(t *testing.T) {
	tests := []struct {
		tier     Tier
		expected string
	}{
		{TierLegendary, "legendary"},
		{TierInteresting, "interesting"},
		{TierStrong, "strong"},
		{TierObvious, "obvious"},
		{TierUnlikely, "unlikely"},
	}

	for _, tt := range tests {
		if tt.tier.String() != tt.expected {
			t.Errorf("Tier %d String() = %s, want %s", tt.tier, tt.tier.String(), tt.expected)
		}
	}
}

func TestSortByTier(t *testing.T) {
	matches := []Match{
		{SynsetID: "a", Tier: TierUnlikely, OverlapCount: 1},
		{SynsetID: "b", Tier: TierLegendary, OverlapCount: 4},
		{SynsetID: "c", Tier: TierStrong, OverlapCount: 2},
	}

	sorted := SortByTier(matches)

	if sorted[0].SynsetID != "b" {
		t.Errorf("Expected legendary tier first, got %s", sorted[0].SynsetID)
	}
	if sorted[len(sorted)-1].SynsetID != "a" {
		t.Errorf("Expected unlikely tier last, got %s", sorted[len(sorted)-1].SynsetID)
	}
}
```

### Step 3.2: Run test to verify it fails

Run: `cd /home/msi/projects/metaforge/.worktrees/sprint-zero/api && go test ./internal/forge/... -v`
Expected: FAIL - package not found

### Step 3.3: Write forge matching algorithm

Create `api/internal/forge/forge.go`:

```go
// Package forge implements the Metaphor Forge 5-tier matching algorithm.
// It ranks synset matches based on property overlap and semantic distance.
package forge

import "sort"

// Tier represents the quality tier of a metaphor match.
type Tier int

const (
	TierLegendary   Tier = iota // High distance + strong overlap (4+)
	TierInteresting             // High distance + weak overlap (1)
	TierStrong                  // High distance + moderate overlap (2-3)
	TierObvious                 // Low distance + any overlap
	TierUnlikely                // Low distance + weak overlap
)

func (t Tier) String() string {
	return [...]string{"legendary", "interesting", "strong", "obvious", "unlikely"}[t]
}

// Thresholds for tier classification
const (
	HighDistanceThreshold = 0.6 // Semantic distance above which concepts are "far"
	MinOverlap            = 2   // Minimum shared properties for "moderate" overlap
	StrongOverlap         = 4   // Shared properties for "strong" overlap
)

// Match represents a candidate metaphor match.
type Match struct {
	SynsetID         string   `json:"synset_id"`
	Word             string   `json:"word"`
	Definition       string   `json:"definition,omitempty"`
	SharedProperties []string `json:"shared_properties"`
	OverlapCount     int      `json:"overlap_count"`
	Distance         float64  `json:"distance"`
	Tier             Tier     `json:"-"`
	TierName         string   `json:"tier"`
}

// ClassifyTier determines the quality tier based on distance and overlap.
//
// The algorithm rewards "surprising" connections:
// - High distance = concepts are semantically far apart
// - High overlap = concepts share many structural properties
// - Legendary = far apart but share many properties (best metaphors)
func ClassifyTier(distance float64, overlap int) Tier {
	highDistance := distance > HighDistanceThreshold
	strongOverlap := overlap >= StrongOverlap
	moderateOverlap := overlap >= MinOverlap

	switch {
	case highDistance && strongOverlap:
		return TierLegendary
	case highDistance && !moderateOverlap:
		return TierInteresting
	case highDistance && moderateOverlap:
		return TierStrong
	case !highDistance && moderateOverlap:
		return TierObvious
	default:
		return TierUnlikely
	}
}

// SortByTier sorts matches by tier (best first), then by overlap count.
func SortByTier(matches []Match) []Match {
	sorted := make([]Match, len(matches))
	copy(sorted, matches)

	sort.Slice(sorted, func(i, j int) bool {
		// Primary: tier (lower = better)
		if sorted[i].Tier != sorted[j].Tier {
			return sorted[i].Tier < sorted[j].Tier
		}
		// Secondary: overlap count (higher = better)
		if sorted[i].OverlapCount != sorted[j].OverlapCount {
			return sorted[i].OverlapCount > sorted[j].OverlapCount
		}
		// Tertiary: distance (higher = more surprising)
		return sorted[i].Distance > sorted[j].Distance
	})

	return sorted
}
```

### Step 3.4: Run test to verify it passes

Run: `cd /home/msi/projects/metaforge/.worktrees/sprint-zero/api && go test ./internal/forge/... -v`
Expected: PASS

### Step 3.5: Commit

```bash
git add api/internal/forge/
git commit -m "$(cat <<'EOF'
feat: implement 5-tier metaphor matching algorithm

Tiers ranked best to worst:
- Legendary: far apart semantically + 4+ shared properties
- Interesting: far apart + 1 shared property
- Strong: far apart + 2-3 shared properties
- Obvious: close semantically + moderate overlap
- Unlikely: close + weak overlap

Rewards "surprising" metaphors where distant concepts share structure.
EOF
)"
```

---

## Task 4: Build HTTP Handler for /forge/suggest

**Files:**
- Create: `api/internal/handler/handler.go`
- Create: `api/internal/handler/handler_test.go`
- Modify: `api/cmd/metaforge/main.go`

### Step 4.1: Write failing test for handler

Create `api/internal/handler/handler_test.go`:

```go
// api/internal/handler/handler_test.go
package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

const testDBPath = "../../../data-pipeline/output/lexicon_v2.db"

func TestForgeSuggestEndpoint(t *testing.T) {
	h, err := NewForgeHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=candle", nil)
	w := httptest.NewRecorder()

	h.HandleSuggest(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("Failed to parse response: %v", err)
	}

	if resp.Source == "" {
		t.Error("Expected source word in response")
	}
}

func TestForgeSuggestMissingWord(t *testing.T) {
	h, err := NewForgeHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest", nil)
	w := httptest.NewRecorder()

	h.HandleSuggest(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected 400 for missing word, got %d", w.Code)
	}
}

func TestForgeSuggestUnknownWord(t *testing.T) {
	h, err := NewForgeHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=xyzzy12345", nil)
	w := httptest.NewRecorder()

	h.HandleSuggest(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("Expected 404 for unknown word, got %d", w.Code)
	}
}
```

### Step 4.2: Run test to verify it fails

Run: `cd /home/msi/projects/metaforge/.worktrees/sprint-zero/api && go test ./internal/handler/... -v`
Expected: FAIL - package not found

### Step 4.3: Write handler

Create `api/internal/handler/handler.go`:

```go
// Package handler provides HTTP handlers for the Metaforge API.
package handler

import (
	"database/sql"
	"encoding/json"
	"net/http"

	"github.com/snailuj/metaforge/internal/db"
	"github.com/snailuj/metaforge/internal/embeddings"
	"github.com/snailuj/metaforge/internal/forge"
)

// ForgeHandler handles /forge/* endpoints.
type ForgeHandler struct {
	database *sql.DB
}

// NewForgeHandler creates a handler with database connection.
func NewForgeHandler(dbPath string) (*ForgeHandler, error) {
	database, err := db.Open(dbPath)
	if err != nil {
		return nil, err
	}
	return &ForgeHandler{database: database}, nil
}

// Close releases database resources.
func (h *ForgeHandler) Close() error {
	return h.database.Close()
}

// SuggestResponse is the JSON response for /forge/suggest.
type SuggestResponse struct {
	Source      string        `json:"source"`
	SynsetID    string        `json:"synset_id"`
	Definition  string        `json:"definition"`
	Properties  []string      `json:"properties"`
	Suggestions []forge.Match `json:"suggestions"`
}

// HandleSuggest handles GET /forge/suggest?word=<word>
func (h *ForgeHandler) HandleSuggest(w http.ResponseWriter, r *http.Request) {
	word := r.URL.Query().Get("word")
	if word == "" {
		http.Error(w, `{"error": "missing 'word' parameter"}`, http.StatusBadRequest)
		return
	}

	// Look up synset for word
	synsetID, err := db.GetSynsetIDForLemma(h.database, word)
	if err != nil {
		http.Error(w, `{"error": "word not found"}`, http.StatusNotFound)
		return
	}

	// Get source synset with properties
	source, err := db.GetSynset(h.database, synsetID)
	if err != nil {
		http.Error(w, `{"error": "synset lookup failed"}`, http.StatusInternalServerError)
		return
	}

	if len(source.Properties) == 0 {
		http.Error(w, `{"error": "word has no enriched properties"}`, http.StatusNotFound)
		return
	}

	// Find synsets with shared properties
	candidates, err := db.GetSynsetsWithSharedProperties(h.database, synsetID)
	if err != nil {
		http.Error(w, `{"error": "matching failed"}`, http.StatusInternalServerError)
		return
	}

	// Compute distances and classify tiers
	var matches []forge.Match
	for _, c := range candidates {
		// Get target synset details
		target, err := db.GetSynset(h.database, c.SynsetID)
		if err != nil {
			continue
		}

		// Get word for target synset
		targetWord, err := db.GetLemmaForSynset(h.database, c.SynsetID)
		if err != nil {
			targetWord = c.SynsetID // Fallback to ID
		}

		// Compute semantic distance via embeddings
		dist, err := embeddings.ComputePropertySetDistance(
			h.database, source.Properties, target.Properties)
		if err != nil {
			dist = 0.5 // Default for OOV
		}

		tier := forge.ClassifyTier(dist, c.OverlapCount)

		matches = append(matches, forge.Match{
			SynsetID:         c.SynsetID,
			Word:             targetWord,
			Definition:       target.Definition,
			SharedProperties: c.SharedProperties,
			OverlapCount:     c.OverlapCount,
			Distance:         dist,
			Tier:             tier,
			TierName:         tier.String(),
		})
	}

	// Sort by tier and limit results
	sorted := forge.SortByTier(matches)
	if len(sorted) > 50 {
		sorted = sorted[:50]
	}

	resp := SuggestResponse{
		Source:      word,
		SynsetID:    synsetID,
		Definition:  source.Definition,
		Properties:  source.Properties,
		Suggestions: sorted,
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}
```

### Step 4.4: Run test to verify it passes

Run: `cd /home/msi/projects/metaforge/.worktrees/sprint-zero/api && go test ./internal/handler/... -v`
Expected: PASS

### Step 4.5: Commit

```bash
git add api/internal/handler/
git commit -m "$(cat <<'EOF'
feat: add /forge/suggest HTTP handler

- Accepts ?word=<word> parameter
- Returns source word properties + tiered suggestions
- Computes semantic distance via FastText embeddings
- Limits results to top 50 matches
EOF
)"
```

---

## Task 5: Wire Up Main Server

**Files:**
- Modify: `api/cmd/metaforge/main.go`
- Modify: `api/go.mod` (add chi router)

### Step 5.1: Add chi dependency

Run: `cd /home/msi/projects/metaforge/.worktrees/sprint-zero/api && go get github.com/go-chi/chi/v5`

### Step 5.2: Update main.go

Replace `api/cmd/metaforge/main.go`:

```go
// Metaforge API server - Sprint Zero MVP
package main

import (
	"flag"
	"fmt"
	"log"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/snailuj/metaforge/internal/handler"
)

func main() {
	// CLI flags
	dbPath := flag.String("db", "../data-pipeline/output/lexicon_v2.db", "Path to lexicon_v2.db")
	port := flag.String("port", "8080", "Server port")
	flag.Parse()

	// Create handler
	forgeHandler, err := handler.NewForgeHandler(*dbPath)
	if err != nil {
		log.Fatalf("Failed to initialise: %v", err)
	}
	defer forgeHandler.Close()

	// Set up router
	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.SetHeader("Content-Type", "application/json"))

	// Routes
	r.Get("/forge/suggest", forgeHandler.HandleSuggest)
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"status": "ok"}`))
	})

	// Start server
	addr := fmt.Sprintf(":%s", *port)
	fmt.Printf("Metaforge API starting on %s...\n", addr)
	fmt.Printf("  Database: %s\n", *dbPath)
	fmt.Printf("  Try: curl 'http://localhost:%s/forge/suggest?word=candle'\n", *port)
	log.Fatal(http.ListenAndServe(addr, r))
}
```

### Step 5.3: Build and verify

Run: `cd /home/msi/projects/metaforge/.worktrees/sprint-zero/api && go build ./cmd/metaforge`
Expected: Binary builds without errors

### Step 5.4: Commit

```bash
git add api/cmd/metaforge/main.go api/go.mod api/go.sum
git commit -m "$(cat <<'EOF'
feat: wire up main server with chi router

- Add --db and --port CLI flags
- Mount /forge/suggest and /health endpoints
- Add request logging and panic recovery middleware
EOF
)"
```

---

## Task 6: End-to-End Verification

### Step 6.1: Start the API server

```bash
cd /home/msi/projects/metaforge/.worktrees/sprint-zero/api
./metaforge --db ../data-pipeline/output/lexicon_v2.db
```

### Step 6.2: Test health endpoint

```bash
curl http://localhost:8080/health
```

Expected: `{"status": "ok"}`

### Step 6.3: Test forge/suggest endpoint

```bash
curl "http://localhost:8080/forge/suggest?word=candle" | jq .
```

Expected: JSON with source word, properties, and tiered suggestions.

### Step 6.4: Verify tier distribution

Check that results include multiple tiers (legendary, interesting, strong, etc.).

### Step 6.5: Final commit

```bash
git add -A
git commit -m "$(cat <<'EOF'
feat: complete Sprint Zero - Metaphor Forge API

End-to-end verification:
- /forge/suggest returns tiered metaphor suggestions
- Uses lexicon_v2.db with normalised junction table schema
- FastText 300d embeddings for semantic distance
- 5-tier ranking rewards "surprising" connections
EOF
)"
```

---

## Deliverables Checklist

| Deliverable | Status |
|-------------|--------|
| DB layer updated for lexicon_v2.db | ☐ |
| FastText 300d embeddings layer | ☐ |
| 5-tier matching algorithm | ☐ |
| /forge/suggest HTTP endpoint | ☐ |
| Main server with chi router | ☐ |
| End-to-end verification | ☐ |
| All tests passing | ☐ |

---

## Data Source Summary

**lexicon_v2.db** (from Sch2 pipeline):

| Table | Purpose | Row Count |
|-------|---------|-----------|
| synsets | OEWN word senses | 107,519 |
| lemmas | Word → synset mappings | 185,081 |
| relations | Semantic relations | 234,810 |
| property_vocabulary | Curated properties + FastText 300d | 5,066 |
| synset_properties | Synset → property junction | 17,011 |
| enrichment | Enriched synset metadata | 1,967 |
| syntagms | SyntagNet collocations | 87,265 |
| vn_classes | VerbNet verb classes | 609 |

**Key schema change from v1:**
- Properties stored in junction table (synset_properties → property_vocabulary)
- Embeddings stored as 1200-byte BLOBs (FastText 300d)
- No more JSON arrays in enrichment table
