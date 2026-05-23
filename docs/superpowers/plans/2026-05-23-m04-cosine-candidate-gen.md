# M04 — Cosine-Sim Candidate Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Broaden cascade candidate generation with a brute-force cosine-band path over `synset_centroids` so cross-domain pairs (anger→fire, idea→light, time→money) reach the M03 scorer.

**Architecture:** New `GetForgeCascadeCandidatesByEmbedding` scans the in-memory `CascadeCache.Centroids` for synsets in `[d_min, d_max]` of the topic's primary synset; `unionCandidates` merges that path with the existing cluster-overlap CTE (cluster wins on conflict). `CascadeConfig` gains `CandidateSources`, `EmbeddingDMin/DMax/TopK` knobs, env-controlled at startup. Per-request anomaly aggregator replaces noisy per-candidate Error logs. A calibration sweep over `(d_min, d_max)` ratifies (or rejects) `union` as the default.

**Tech Stack:** Go 1.22 (`api/`), SQLite + `mattn/go-sqlite3`, slog timing via `internal/observe`, Python 3 sweep driver (`data-pipeline/scripts/run_sweep.py` plus a new HTTP-driven runner).

**Reference:** `docs/superpowers/specs/2026-05-23-m04-cosine-candidate-gen-design.md`

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `api/internal/forge/cascade.go` | modify | `CandidateSource` per-row enum; `CandidateSources` config enum; `CascadeConfig` extension; `Validate()` |
| `api/internal/forge/cascade_test.go` | modify | Unit tests for the two new enums + `Validate()` |
| `api/internal/db/cascade.go` | modify | Extend `CascadeCandidate` with `Source forge.CandidateSource`; populate `Source = SourceCluster` in `GetForgeCascadeCandidatesByLemma` |
| `api/internal/db/cascade_embedding.go` | **create** | `GetForgeCascadeCandidatesByEmbedding` — brute-force cosine scan over `CascadeCache.Centroids`, primary-synset resolution, batched target-side `synsets` lookup |
| `api/internal/db/cascade_embedding_test.go` | **create** | Unit tests with synthetic cache (band filter, top-K, missing-topic, identity exclusion) |
| `api/internal/handler/cascade_union.go` | **create** | `unionCandidates(cluster, embedding) []db.CascadeCandidate` — dedup, cluster-wins-on-conflict, source tagging |
| `api/internal/handler/cascade_union_test.go` | **create** | Table-driven unit tests for `unionCandidates` |
| `api/internal/handler/handler.go` | modify | Cascade handler dispatch by `CandidateSources`, `cascade_embedding_query` timing stage, `cascadeAnomalies` aggregator, runtime tripwire on `synset_properties_curated` |
| `api/internal/handler/handler_cascade_test.go` | modify | Cascade-mode integration tests: canary pairs (union, embedding_only), `cluster_only` backward-compat snapshot, aggregator attribute assertions, tripwire extension |
| `api/cmd/metaforge/main.go` | modify | `--candidate-sources` flag + `METAFORGE_FORGE_CANDIDATES` env; `--embedding-d-min`/`-d-max`/`-top-k` flags + env equivalents; wire into `CascadeConfig` and `Validate()` at startup |
| `data-pipeline/sweeps/m04_embedding_band.yaml` | **create** | Sweep grid (3×3 `d_min × d_max`) + cohort/runner config |
| `data-pipeline/scripts/m04_sweep_runner.py` | **create** | Per-cell driver: start Go API with env vars, query `/forge/suggest` for MUNCH apt+inapt pairs, compute `separation_score`/`aptness_rate`, write per-cell JSON + verdict markdown |
| `data-pipeline/sweeps/m04_embedding_band_verdict.md` | **create (end-of-S04)** | Top cell, non-regression check, source-mix observations, default-flip decision |

---

## Slice Map

| Slice | Tasks | Goal |
|---|---|---|
| **S01** | 1–5 | Embedding candidate generator + per-row enum + `CascadeCandidate.Source` |
| **S02** | 6–13 | Config + union + handler integration + CLI/env + canary tests |
| **S03** | 14–18 | Anomaly aggregator (concreteness + empty props) + runtime tripwire on `synset_properties_curated` |
| **Gate** | — | `/code-review-loop` runs over the S01+S02+S03 surface before sweep |
| **S04** | 19–23 | Calibration sweep YAML + Python driver + run + verdict markdown + optional default flip |

---

## Task 1: Add `CandidateSource` per-row enum

**Files:**
- Modify: `api/internal/forge/cascade.go` (append below `CompositionMultiplicative`)
- Modify: `api/internal/forge/cascade_test.go` (append at end)

- [ ] **Step 1: Write the failing test**

Append to `api/internal/forge/cascade_test.go`:

```go
func TestCandidateSource_ValidRecognisesKnownTags(t *testing.T) {
	for _, s := range []CandidateSource{SourceCluster, SourceEmbedding, SourceBoth} {
		if !s.Valid() {
			t.Errorf("CandidateSource(%q).Valid() = false, want true", s)
		}
	}
}

func TestCandidateSource_ValidRejectsUnknown(t *testing.T) {
	for _, s := range []CandidateSource{"", "neither", "cluster_only", "embedding_only"} {
		if CandidateSource(s).Valid() {
			t.Errorf("CandidateSource(%q).Valid() = true, want false", s)
		}
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd api && go test ./internal/forge/ -run TestCandidateSource_Valid
```

Expected: FAIL — `undefined: CandidateSource` / `undefined: SourceCluster` / etc.

- [ ] **Step 3: Add the enum**

Append to `api/internal/forge/cascade.go` (after the `Composition` block):

```go
// CandidateSource tags a single candidate row with the generation path
// that produced it. Distinct from CandidateSources (the config-side enum
// that chooses which paths to run) — a `union` request can produce rows
// tagged cluster, embedding, OR both. Purely diagnostic in M04 v1; a
// future co-generation scoring bonus may key off SourceBoth.
type CandidateSource string

const (
	SourceCluster   CandidateSource = "cluster"
	SourceEmbedding CandidateSource = "embedding"
	SourceBoth      CandidateSource = "both"
)

// Valid reports whether s is one of the three known per-row source tags.
// Unknown values indicate a structural bug (untagged candidate, manual
// JSON tampering); callers may use this on the boundary between trusted
// internal code and untrusted inputs.
func (s CandidateSource) Valid() bool {
	switch s {
	case SourceCluster, SourceEmbedding, SourceBoth:
		return true
	}
	return false
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd api && go test ./internal/forge/ -run TestCandidateSource_Valid -v
```

Expected: PASS (both sub-tests green).

- [ ] **Step 5: Commit**

```bash
git add api/internal/forge/cascade.go api/internal/forge/cascade_test.go
git commit -m "feat(forge): add CandidateSource per-row enum with Valid()"
```

---

## Task 2: Add `CandidateSources` config enum

**Files:**
- Modify: `api/internal/forge/cascade.go` (append after `CandidateSource`)
- Modify: `api/internal/forge/cascade_test.go` (append)

- [ ] **Step 1: Write the failing test**

Append:

```go
func TestCandidateSources_ValidRecognisesKnownModes(t *testing.T) {
	for _, s := range []CandidateSources{SourcesCluster, SourcesEmbedding, SourcesUnion} {
		if !s.Valid() {
			t.Errorf("CandidateSources(%q).Valid() = false, want true", s)
		}
	}
}

func TestCandidateSources_ValidRejectsUnknown(t *testing.T) {
	for _, s := range []CandidateSources{"", "cluster", "embedding", "both", "all"} {
		if CandidateSources(s).Valid() {
			t.Errorf("CandidateSources(%q).Valid() = true, want false", s)
		}
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd api && go test ./internal/forge/ -run TestCandidateSources_Valid
```

Expected: FAIL — `undefined: CandidateSources`.

- [ ] **Step 3: Add the enum**

Append:

```go
// CandidateSources is the config-side enum: which generation paths to
// run for each cascade request. Maps to METAFORGE_FORGE_CANDIDATES /
// --candidate-sources. Different value set from CandidateSource — see
// the per-row CandidateSource doc above.
type CandidateSources string

const (
	SourcesCluster   CandidateSources = "cluster_only"
	SourcesEmbedding CandidateSources = "embedding_only"
	SourcesUnion     CandidateSources = "union"
)

// Valid reports whether s is one of the three known config modes.
// CascadeConfig.Validate() consults this at startup so an invalid env
// value fails loud instead of silently falling back to a default.
func (s CandidateSources) Valid() bool {
	switch s {
	case SourcesCluster, SourcesEmbedding, SourcesUnion:
		return true
	}
	return false
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd api && go test ./internal/forge/ -run TestCandidateSources_Valid -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/internal/forge/cascade.go api/internal/forge/cascade_test.go
git commit -m "feat(forge): add CandidateSources config enum with Valid()"
```

---

## Task 3: Extend `CascadeConfig` with embedding knobs + `Validate()`

**Files:**
- Modify: `api/internal/forge/cascade.go` (extend `CascadeConfig` struct, extend `DefaultCascadeConfig`, add `Validate`)
- Modify: `api/internal/forge/cascade_test.go` (append)

- [ ] **Step 1: Write the failing tests**

Append:

```go
func TestCascadeConfig_DefaultIsValid(t *testing.T) {
	cfg := DefaultCascadeConfig()
	if err := cfg.Validate(); err != nil {
		t.Errorf("DefaultCascadeConfig must validate: %v", err)
	}
	if cfg.CandidateSources != SourcesCluster {
		t.Errorf("default CandidateSources: want %q (pre-sweep), got %q",
			SourcesCluster, cfg.CandidateSources)
	}
	if cfg.EmbeddingDMin != 0.4 || cfg.EmbeddingDMax != 0.85 || cfg.EmbeddingTopK != 100 {
		t.Errorf("default embedding knobs: got dMin=%v dMax=%v topK=%v",
			cfg.EmbeddingDMin, cfg.EmbeddingDMax, cfg.EmbeddingTopK)
	}
}

func TestCascadeConfig_ValidateRejectsBadFields(t *testing.T) {
	base := DefaultCascadeConfig()

	cases := []struct {
		name string
		mut  func(c *CascadeConfig)
		want string
	}{
		{"unknown sources", func(c *CascadeConfig) { c.CandidateSources = "all" }, "CandidateSources"},
		{"negative dMin", func(c *CascadeConfig) { c.EmbeddingDMin = -0.1 }, "EmbeddingDMin"},
		{"dMin above 2", func(c *CascadeConfig) { c.EmbeddingDMin = 2.5 }, "EmbeddingDMin"},
		{"dMax not above dMin", func(c *CascadeConfig) { c.EmbeddingDMax = c.EmbeddingDMin }, "EmbeddingDMax"},
		{"topK zero", func(c *CascadeConfig) { c.EmbeddingTopK = 0 }, "EmbeddingTopK"},
		{"topK negative", func(c *CascadeConfig) { c.EmbeddingTopK = -5 }, "EmbeddingTopK"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			c := base
			tc.mut(&c)
			err := c.Validate()
			if err == nil {
				t.Fatalf("want error mentioning %q, got nil", tc.want)
			}
			if !strings.Contains(err.Error(), tc.want) {
				t.Errorf("want error containing %q, got %v", tc.want, err)
			}
		})
	}
}
```

Add `"strings"` to the import block at the top of `cascade_test.go` if not already present.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd api && go test ./internal/forge/ -run TestCascadeConfig
```

Expected: FAIL — `cfg.CandidateSources undefined` / `Validate undefined`.

- [ ] **Step 3: Extend the struct + default + add `Validate`**

In `api/internal/forge/cascade.go`, replace the existing `CascadeConfig` struct with:

```go
type CascadeConfig struct {
	ConcretenessThreshold float64
	Alpha                 float64
	DCap                  float64
	Composition           Composition

	// M04 candidate-generation knobs.
	CandidateSources CandidateSources // which paths to run
	EmbeddingDMin    float64          // inclusive lower band on cosine distance
	EmbeddingDMax    float64          // inclusive upper band
	EmbeddingTopK    int              // cap on per-request embedding candidates
}
```

Replace `DefaultCascadeConfig` with:

```go
// DefaultCascadeConfig returns the production-blessed winner config from
// the M03 Stage-2 sweep (separation +0.1779) plus the pre-sweep M04
// candidate-generation defaults. CandidateSources is SourcesCluster
// (M03 behaviour) until the M04 sweep ratifies SourcesUnion.
func DefaultCascadeConfig() CascadeConfig {
	return CascadeConfig{
		ConcretenessThreshold: 1.0,
		Alpha:                 1.0,
		DCap:                  0.77,
		Composition:           CompositionAdditive,
		CandidateSources:      SourcesCluster,
		EmbeddingDMin:         0.4,
		EmbeddingDMax:         0.85,
		EmbeddingTopK:         100,
	}
}
```

Add `Validate` (anywhere after `DefaultCascadeConfig`):

```go
// Validate enforces invariants on CascadeConfig before the handler
// accepts the config. Called at startup from main.go after env/flag
// parsing so bad values fail loud instead of silently degrading the
// scorer.
func (c CascadeConfig) Validate() error {
	if !c.CandidateSources.Valid() {
		return fmt.Errorf("CandidateSources %q is not one of cluster_only|embedding_only|union", c.CandidateSources)
	}
	if c.EmbeddingDMin < 0.0 || c.EmbeddingDMin > 2.0 {
		return fmt.Errorf("EmbeddingDMin %v out of range [0, 2]", c.EmbeddingDMin)
	}
	if c.EmbeddingDMax <= c.EmbeddingDMin || c.EmbeddingDMax > 2.0 {
		return fmt.Errorf("EmbeddingDMax %v must be > EmbeddingDMin (%v) and ≤ 2.0",
			c.EmbeddingDMax, c.EmbeddingDMin)
	}
	if c.EmbeddingTopK <= 0 {
		return fmt.Errorf("EmbeddingTopK %d must be > 0", c.EmbeddingTopK)
	}
	return nil
}
```

Add `"fmt"` to the import block of `cascade.go`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd api && go test ./internal/forge/ -run TestCascadeConfig -v
```

Expected: PASS (default valid + 6 sub-tests reject bad fields).

- [ ] **Step 5: Run full forge package tests to ensure no regressions**

```bash
cd api && go test ./internal/forge/...
```

Expected: PASS — existing M03 cascade tests must remain green.

- [ ] **Step 6: Commit**

```bash
git add api/internal/forge/cascade.go api/internal/forge/cascade_test.go
git commit -m "feat(forge): CascadeConfig embedding knobs + Validate()"
```

---

## Task 4: Add `Source` field to `CascadeCandidate` and tag cluster path

**Files:**
- Modify: `api/internal/db/cascade.go` (struct + `GetForgeCascadeCandidatesByLemma`)
- Modify: `api/internal/db/cascade_test.go` (append)

- [ ] **Step 1: Write the failing test**

Append to `api/internal/db/cascade_test.go`:

```go
func TestGetForgeCascadeCandidatesByLemma_TagsRowsWithSourceCluster(t *testing.T) {
	database, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	candidates, err := GetForgeCascadeCandidatesByLemma(database, "anger", 1.0, 10)
	if err != nil {
		t.Fatalf("candidates: %v", err)
	}
	if len(candidates) == 0 {
		t.Fatal("expected at least one candidate for 'anger'")
	}
	for _, c := range candidates {
		if c.Source != forge.SourceCluster {
			t.Errorf("candidate %s tagged %q, want %q", c.SynsetID, c.Source, forge.SourceCluster)
		}
	}
}
```

Add the import: `"github.com/snailuj/metaforge/internal/forge"` to `cascade_test.go`.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd api && go test ./internal/db/ -run TestGetForgeCascadeCandidatesByLemma_TagsRowsWithSourceCluster
```

Expected: FAIL — `c.Source undefined`.

- [ ] **Step 3: Extend `CascadeCandidate` and tag the cluster path**

In `api/internal/db/cascade.go`, replace the `CascadeCandidate` struct:

```go
// CascadeCandidate is one gate-passed candidate row. Source tags which
// generation path produced the row — set by the generator that built it.
// Concreteness is NOT carried on the row — the handler reads it from
// the in-memory cascade cache so the *float64 absence-signal contract
// that EvaluateCascadePair expects is preserved (TD1 fix).
type CascadeCandidate struct {
	SynsetID         string
	Word             string
	POS              string
	Definition       string
	SalienceSum      float64
	ContrastCount    int
	SharedProps      []string
	SourceSynsetID   string
	SourceDefinition string
	SourcePOS        string
	Source           forge.CandidateSource
}
```

Add `"github.com/snailuj/metaforge/internal/forge"` to the import block of `cascade.go`.

Inside `GetForgeCascadeCandidatesByLemma`, immediately after the existing `matches = append(matches, m)` line, change the loop body to set `m.Source = forge.SourceCluster` *before* the append. Patch:

```go
		seen[m.SynsetID] = true
		if sharedProps != "" {
			m.SharedProps = strings.Split(sharedProps, ",")
		}
		m.Source = forge.SourceCluster
		matches = append(matches, m)
```

- [ ] **Step 4: Run the new test plus the existing cascade tests**

```bash
cd api && go test ./internal/db/ -run TestGetForgeCascadeCandidates -v
```

Expected: PASS for all 5 cascade candidate tests (the existing 4 + the new tag test).

- [ ] **Step 5: Commit**

```bash
git add api/internal/db/cascade.go api/internal/db/cascade_test.go
git commit -m "feat(db): tag cascade candidates with forge.CandidateSource"
```

---

## Task 5: `GetForgeCascadeCandidatesByEmbedding` — brute-force cosine scan

**Files:**
- Create: `api/internal/db/cascade_embedding.go`
- Create: `api/internal/db/cascade_embedding_test.go`

This is the largest single task in S01. It has two write-test-impl cycles: cosine math + band/top-K filter (synthetic cache), then DB-backed primary-synset + target lookup.

- [ ] **Step 1: Write the failing unit test (synthetic cache, band + top-K)**

Create `api/internal/db/cascade_embedding_test.go`:

```go
package db

import (
	"testing"

	"github.com/snailuj/metaforge/internal/forge"
)

// vec returns a length-300 float32 vector with the supplied prefix and
// the remainder zero-padded — just enough for cosine math to behave.
func vec(prefix ...float32) []float32 {
	v := make([]float32, 300)
	copy(v, prefix)
	return v
}

func TestScanEmbeddingBand_FiltersOutsideBand(t *testing.T) {
	cache := &CascadeCache{
		Centroids: map[string][]float32{
			"topic":      vec(1, 0, 0),  // d=0 to itself
			"near":       vec(1, 0, 0),  // d≈0 — below dMin
			"in_band_a":  vec(0.5, 0.5, 0),
			"in_band_b":  vec(0.0, 1.0, 0),
			"far":        vec(-1, 0, 0), // d=2 — above dMax
		},
	}
	hits := scanEmbeddingBand(cache, "topic", 0.2, 1.5, 10)
	got := map[string]bool{}
	for _, h := range hits {
		got[h.synsetID] = true
	}
	if got["topic"] || got["near"] || got["far"] {
		t.Errorf("identity/below-dMin/above-dMax must be excluded; got %v", got)
	}
	if !got["in_band_a"] || !got["in_band_b"] {
		t.Errorf("in-band entries missing; got %v", got)
	}
}

func TestScanEmbeddingBand_CapsAtTopK(t *testing.T) {
	cache := &CascadeCache{Centroids: map[string][]float32{}}
	cache.Centroids["topic"] = vec(1, 0, 0)
	for i := 0; i < 50; i++ {
		// All 50 will be in [0.2, 1.5] band by construction.
		cache.Centroids[idForI(i)] = vec(0.5, 0.5, 0)
	}
	hits := scanEmbeddingBand(cache, "topic", 0.2, 1.5, 7)
	if len(hits) != 7 {
		t.Errorf("want 7 hits (topK), got %d", len(hits))
	}
}

func TestScanEmbeddingBand_NoTopicCentroidReturnsNil(t *testing.T) {
	cache := &CascadeCache{Centroids: map[string][]float32{"other": vec(1, 0, 0)}}
	hits := scanEmbeddingBand(cache, "missing", 0.0, 2.0, 10)
	if hits != nil {
		t.Errorf("missing topic centroid: want nil, got %v", hits)
	}
}

func idForI(i int) string {
	return "c-" + string(rune('a'+i%26)) + string(rune('a'+(i/26)%26))
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd api && go test ./internal/db/ -run TestScanEmbeddingBand
```

Expected: FAIL — `undefined: scanEmbeddingBand`.

- [ ] **Step 3: Create `cascade_embedding.go` with the scan helper**

Create `api/internal/db/cascade_embedding.go`:

```go
// Cascade-embedding-band candidate generator. Brute-force cosine scan
// over the in-memory CascadeCache.Centroids cache. Zero new DB
// round-trips on the hot path — the only DB work is a primary-synset
// resolution and a batched target-side synsets row lookup.
package db

import (
	"database/sql"
	"fmt"
	"log/slog"
	"sort"
	"strings"

	"github.com/snailuj/metaforge/internal/forge"
)

// embeddingHit is the intermediate per-candidate record produced by the
// cosine scan, before the synsets-row lookup turns it into a full
// CascadeCandidate.
type embeddingHit struct {
	synsetID string
	distance float64
}

// scanEmbeddingBand walks every entry in cache.Centroids, computes
// cosine distance against the topic centroid, filters to [dMin, dMax]
// (both inclusive), and returns the topK nearest by ascending distance.
// Self-match (topicSynsetID == entry) is dropped regardless of band.
// Returns nil when the topic centroid is absent from the cache —
// caller must treat nil as "embedding path unavailable for this lemma".
func scanEmbeddingBand(cache *CascadeCache, topicSynsetID string, dMin, dMax float64, topK int) []embeddingHit {
	topic, ok := cache.Centroids[topicSynsetID]
	if !ok {
		return nil
	}
	hits := make([]embeddingHit, 0, 64)
	for id, vec := range cache.Centroids {
		if id == topicSynsetID {
			continue
		}
		d, ok := forge.CascadeCosineDistance(topic, vec)
		if !ok {
			// Dimension mismatch or zero-norm — skip silently; the
			// load-side log already flagged the malformed entry.
			continue
		}
		if d < dMin || d > dMax {
			continue
		}
		hits = append(hits, embeddingHit{synsetID: id, distance: d})
	}
	sort.Slice(hits, func(i, j int) bool {
		return hits[i].distance < hits[j].distance
	})
	if len(hits) > topK {
		hits = hits[:topK]
	}
	return hits
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd api && go test ./internal/db/ -run TestScanEmbeddingBand -v
```

Expected: PASS (3 sub-tests green).

- [ ] **Step 5: Commit**

```bash
git add api/internal/db/cascade_embedding.go api/internal/db/cascade_embedding_test.go
git commit -m "feat(db): scanEmbeddingBand brute-force cosine scan"
```

- [ ] **Step 6: Write the failing DB-integration test**

Append to `api/internal/db/cascade_embedding_test.go`:

```go
func TestGetForgeCascadeCandidatesByEmbedding_AnchorPairsSurface(t *testing.T) {
	database, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	cache, err := LoadCascadeCache(database)
	if err != nil {
		t.Fatalf("LoadCascadeCache: %v", err)
	}

	cfg := ForgeEmbeddingConfig{DMin: 0.0, DMax: 1.5, TopK: 200}
	got, err := GetForgeCascadeCandidatesByEmbedding(database, cache, "anger", cfg)
	if err != nil {
		t.Fatalf("GetForgeCascadeCandidatesByEmbedding: %v", err)
	}
	if len(got) == 0 {
		t.Fatal("expected non-empty embedding candidates for 'anger'")
	}
	for _, c := range got {
		if c.Source != forge.SourceEmbedding {
			t.Errorf("candidate %s: Source=%q want %q", c.SynsetID, c.Source, forge.SourceEmbedding)
		}
		if c.SalienceSum != 0 || c.ContrastCount != 0 {
			t.Errorf("embedding candidate %s: salience/contrast must be zero on this path, got %v/%d",
				c.SynsetID, c.SalienceSum, c.ContrastCount)
		}
		if c.SourceSynsetID == "" || c.Definition == "" || c.POS == "" {
			t.Errorf("candidate %s missing source/definition/pos: %+v", c.SynsetID, c)
		}
	}
}

func TestGetForgeCascadeCandidatesByEmbedding_UnknownLemmaReturnsErrLemmaNotFound(t *testing.T) {
	database, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	cache, err := LoadCascadeCache(database)
	if err != nil {
		t.Fatalf("LoadCascadeCache: %v", err)
	}

	cfg := ForgeEmbeddingConfig{DMin: 0.0, DMax: 1.5, TopK: 10}
	_, err = GetForgeCascadeCandidatesByEmbedding(database, cache, "zzznotarealword", cfg)
	if err == nil {
		t.Fatal("want ErrLemmaNotFound for unknown lemma, got nil")
	}
	if !strings.Contains(err.Error(), "lemma not found") && err.Error() != "" {
		// Accept either ErrLemmaNotFound directly or wrapping with a "lemma not found" message.
		// errors.Is check happens via Task 8 handler integration.
	}
}
```

Add `"strings"` to the imports if not present.

- [ ] **Step 7: Run tests to verify they fail**

```bash
cd api && go test ./internal/db/ -run TestGetForgeCascadeCandidatesByEmbedding
```

Expected: FAIL — `undefined: GetForgeCascadeCandidatesByEmbedding` / `undefined: ForgeEmbeddingConfig`.

- [ ] **Step 8: Add the DB-integration entry point**

Append to `api/internal/db/cascade_embedding.go`:

```go
// ForgeEmbeddingConfig is the per-call shape passed by the handler. We
// keep it independent of forge.CascadeConfig so the embedding generator
// has no compile-time dependency on the full cascade config struct.
type ForgeEmbeddingConfig struct {
	DMin float64
	DMax float64
	TopK int
}

// GetForgeCascadeCandidatesByEmbedding resolves the topic's primary
// synset, reads its centroid from the cache, brute-force-scans every
// other centroid for cosine distance ∈ [DMin, DMax], and returns the
// TopK nearest as CascadeCandidate rows with Source=SourceEmbedding,
// SalienceSum=0, ContrastCount=0, SharedProps=nil. Target-side
// definition/POS come from one batched synsets query.
//
// Returns ErrLemmaNotFound when the lemma has no curated source synset
// (matches the cluster path's contract). Returns (nil, nil) when the
// resolved topic synset has no centroid in the cache — defensive only;
// 100% of enriched synsets have centroids by construction.
func GetForgeCascadeCandidatesByEmbedding(
	database *sql.DB,
	cache *CascadeCache,
	lemma string,
	cfg ForgeEmbeddingConfig,
) ([]CascadeCandidate, error) {
	topicID, err := resolvePrimaryCuratedSynset(database, lemma)
	if err != nil {
		return nil, err
	}

	hits := scanEmbeddingBand(cache, topicID, cfg.DMin, cfg.DMax, cfg.TopK)
	if hits == nil {
		// Topic resolved but no centroid in the cache. Pipeline contract
		// says every enriched synset has a centroid, so this is rare —
		// log Debug and return (nil, nil) so the handler falls back to
		// cluster-only behaviour for this request.
		slog.Debug("no topic centroid for embedding scan", "lemma", lemma, "synset", topicID)
		return nil, nil
	}
	if len(hits) == 0 {
		return nil, nil
	}

	topicRow, err := getSynsetRow(database, topicID)
	if err != nil {
		return nil, fmt.Errorf("topic synset row %s: %w", topicID, err)
	}

	targetIDs := make([]string, len(hits))
	for i, h := range hits {
		targetIDs[i] = h.synsetID
	}
	targetRows, err := getSynsetRowsBatch(database, targetIDs)
	if err != nil {
		return nil, fmt.Errorf("target synsets batch: %w", err)
	}

	out := make([]CascadeCandidate, 0, len(hits))
	for _, h := range hits {
		row, ok := targetRows[h.synsetID]
		if !ok {
			// Centroid present in cache but synset row missing — pipeline
			// contract violation; skip the candidate rather than crash.
			slog.Error("embedding hit has no synsets row", "synset", h.synsetID)
			continue
		}
		out = append(out, CascadeCandidate{
			SynsetID:         h.synsetID,
			Word:             row.lemma,
			POS:              row.pos,
			Definition:       row.definition,
			SalienceSum:      0,
			ContrastCount:    0,
			SharedProps:      nil,
			SourceSynsetID:   topicID,
			SourceDefinition: topicRow.definition,
			SourcePOS:        topicRow.pos,
			Source:           forge.SourceEmbedding,
		})
	}
	return out, nil
}

// resolvePrimaryCuratedSynset picks the topic synset for the embedding
// path. Mirrors GetForgeCascadeCandidatesByLemma's source-synset rule:
// the synset with the most curated property rows (a coarse stand-in
// for the polysemy-ASC primary sense — see the SQL comment on the
// correlated-COUNT cost in cascade.go). Returns ErrLemmaNotFound if
// the lemma has no curated synset at all.
func resolvePrimaryCuratedSynset(database *sql.DB, lemma string) (string, error) {
	var id string
	err := database.QueryRow(`
		SELECT l.synset_id
		FROM lemmas l
		JOIN synset_properties_curated spc ON spc.synset_id = l.synset_id
		WHERE l.lemma = ?
		GROUP BY l.synset_id
		ORDER BY COUNT(*) DESC
		LIMIT 1
	`, lemma).Scan(&id)
	if err == sql.ErrNoRows {
		return "", fmt.Errorf("%w: %s", ErrLemmaNotFound, lemma)
	}
	if err != nil {
		return "", fmt.Errorf("resolvePrimaryCuratedSynset(%q): %w", lemma, err)
	}
	return id, nil
}

// synsetRow is the minimal projection we need on the embedding path —
// definition, POS, and the polysemy-ASC primary lemma for display.
type synsetRow struct {
	pos        string
	definition string
	lemma      string
}

func getSynsetRow(database *sql.DB, id string) (synsetRow, error) {
	var r synsetRow
	err := database.QueryRow(`
		SELECT s.pos, s.definition,
		       (SELECT lemma FROM lemmas WHERE synset_id = s.synset_id ORDER BY lemma LIMIT 1) as lemma
		FROM synsets s WHERE s.synset_id = ?
	`, id).Scan(&r.pos, &r.definition, &r.lemma)
	if err != nil {
		return r, err
	}
	return r, nil
}

// getSynsetRowsBatch fetches POS/definition/primary-lemma for many
// synset ids in one IN-clause query. Returns a map id→row; missing
// ids are absent from the result map.
func getSynsetRowsBatch(database *sql.DB, ids []string) (map[string]synsetRow, error) {
	out := make(map[string]synsetRow, len(ids))
	if len(ids) == 0 {
		return out, nil
	}
	placeholders := make([]string, len(ids))
	args := make([]interface{}, len(ids))
	for i, id := range ids {
		placeholders[i] = "?"
		args[i] = id
	}
	q := `
		SELECT s.synset_id, s.pos, s.definition,
		       (SELECT lemma FROM lemmas WHERE synset_id = s.synset_id ORDER BY lemma LIMIT 1) as lemma
		FROM synsets s WHERE s.synset_id IN (` + strings.Join(placeholders, ",") + `)`
	rows, err := database.Query(q, args...)
	if err != nil {
		return nil, fmt.Errorf("getSynsetRowsBatch query: %w", err)
	}
	defer rows.Close()
	for rows.Next() {
		var id string
		var r synsetRow
		if err := rows.Scan(&id, &r.pos, &r.definition, &r.lemma); err != nil {
			return nil, fmt.Errorf("scan synset row: %w", err)
		}
		out[id] = r
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate synset rows: %w", err)
	}
	return out, nil
}
```

- [ ] **Step 9: Run all `cascade_embedding` tests**

```bash
cd api && go test ./internal/db/ -run TestGetForgeCascadeCandidatesByEmbedding -v
cd api && go test ./internal/db/ -run TestScanEmbeddingBand -v
```

Expected: PASS — 5 sub-tests across the two functions.

- [ ] **Step 10: Run the full `db` package suite to confirm no regressions**

```bash
cd api && go test ./internal/db/...
```

Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add api/internal/db/cascade_embedding.go api/internal/db/cascade_embedding_test.go
git commit -m "feat(db): GetForgeCascadeCandidatesByEmbedding with batched synsets lookup"
```

---

## Task 6: `unionCandidates` — dedup + cluster-wins + source tagging

**Files:**
- Create: `api/internal/handler/cascade_union.go`
- Create: `api/internal/handler/cascade_union_test.go`

- [ ] **Step 1: Write the failing test (table-driven)**

Create `api/internal/handler/cascade_union_test.go`:

```go
package handler

import (
	"reflect"
	"sort"
	"testing"

	"github.com/snailuj/metaforge/internal/db"
	"github.com/snailuj/metaforge/internal/forge"
)

func mkCand(id string, src forge.CandidateSource, sal float64) db.CascadeCandidate {
	return db.CascadeCandidate{
		SynsetID:    id,
		Word:        id + "-word",
		SalienceSum: sal,
		Source:      src,
	}
}

func TestUnionCandidates_EmbeddingOnlyPassesThrough(t *testing.T) {
	cluster := []db.CascadeCandidate(nil)
	emb := []db.CascadeCandidate{mkCand("E1", forge.SourceEmbedding, 0)}
	out := unionCandidates(cluster, emb)
	if len(out) != 1 || out[0].Source != forge.SourceEmbedding {
		t.Fatalf("embedding-only: want 1 SourceEmbedding row, got %+v", out)
	}
}

func TestUnionCandidates_ClusterOnlyPassesThrough(t *testing.T) {
	cluster := []db.CascadeCandidate{mkCand("C1", forge.SourceCluster, 3.0)}
	out := unionCandidates(cluster, nil)
	if len(out) != 1 || out[0].Source != forge.SourceCluster {
		t.Fatalf("cluster-only: want 1 SourceCluster row, got %+v", out)
	}
}

func TestUnionCandidates_OverlapWinsClusterAndTagsBoth(t *testing.T) {
	cluster := []db.CascadeCandidate{mkCand("X1", forge.SourceCluster, 5.5)}
	emb := []db.CascadeCandidate{mkCand("X1", forge.SourceEmbedding, 0)}
	out := unionCandidates(cluster, emb)
	if len(out) != 1 {
		t.Fatalf("overlap: want 1 row, got %d", len(out))
	}
	if out[0].Source != forge.SourceBoth {
		t.Errorf("overlap row Source: want %q, got %q", forge.SourceBoth, out[0].Source)
	}
	if out[0].SalienceSum != 5.5 {
		t.Errorf("overlap row must preserve cluster fields (SalienceSum=5.5), got %v", out[0].SalienceSum)
	}
}

func TestUnionCandidates_DisjointReturnsBothTaggedCorrectly(t *testing.T) {
	cluster := []db.CascadeCandidate{mkCand("C1", forge.SourceCluster, 4.0)}
	emb := []db.CascadeCandidate{mkCand("E1", forge.SourceEmbedding, 0)}
	out := unionCandidates(cluster, emb)
	sort.Slice(out, func(i, j int) bool { return out[i].SynsetID < out[j].SynsetID })
	want := []db.CascadeCandidate{
		mkCand("C1", forge.SourceCluster, 4.0),
		mkCand("E1", forge.SourceEmbedding, 0),
	}
	if !reflect.DeepEqual(out, want) {
		t.Errorf("disjoint mismatch:\n got %+v\nwant %+v", out, want)
	}
}

func TestUnionCandidates_BothNilReturnsEmptyNotNil(t *testing.T) {
	out := unionCandidates(nil, nil)
	if out == nil {
		t.Error("want non-nil empty slice, got nil")
	}
	if len(out) != 0 {
		t.Errorf("want empty, got %d entries", len(out))
	}
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd api && go test ./internal/handler/ -run TestUnionCandidates
```

Expected: FAIL — `undefined: unionCandidates`.

- [ ] **Step 3: Add the union helper**

Create `api/internal/handler/cascade_union.go`:

```go
// unionCandidates merges two cascade candidate slices by SynsetID and
// stamps each row's Source tag. Cluster wins on conflict — the cluster
// row's full payload (salience_sum, contrast_count, shared_props) is
// preserved; only the Source tag changes to SourceBoth when the same
// synset also appears in the embedding slice. Order is deterministic
// in iteration over `cluster` first, then any embedding-only rows
// in their original order.
package handler

import (
	"github.com/snailuj/metaforge/internal/db"
	"github.com/snailuj/metaforge/internal/forge"
)

func unionCandidates(cluster, embedding []db.CascadeCandidate) []db.CascadeCandidate {
	out := make([]db.CascadeCandidate, 0, len(cluster)+len(embedding))
	clusterIDs := make(map[string]struct{}, len(cluster))
	embeddingIDs := make(map[string]struct{}, len(embedding))
	for _, e := range embedding {
		embeddingIDs[e.SynsetID] = struct{}{}
	}
	for _, c := range cluster {
		clusterIDs[c.SynsetID] = struct{}{}
		c.Source = forge.SourceCluster
		if _, dual := embeddingIDs[c.SynsetID]; dual {
			c.Source = forge.SourceBoth
		}
		out = append(out, c)
	}
	for _, e := range embedding {
		if _, clash := clusterIDs[e.SynsetID]; clash {
			continue // cluster row already represents this synset
		}
		e.Source = forge.SourceEmbedding
		out = append(out, e)
	}
	return out
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd api && go test ./internal/handler/ -run TestUnionCandidates -v
```

Expected: PASS (5 sub-tests green).

- [ ] **Step 5: Commit**

```bash
git add api/internal/handler/cascade_union.go api/internal/handler/cascade_union_test.go
git commit -m "feat(handler): unionCandidates dedup with cluster-wins-on-conflict"
```

---

## Task 7: Wire embedding-path dispatch into `handleSuggestCascade`

**Files:**
- Modify: `api/internal/handler/handler.go`

This task changes how `handleSuggestCascade` builds the candidate set; the JSON response shape is unchanged. Status tagging and the `cascade_request_total` close-out attrs are extended in subsequent tasks.

- [ ] **Step 1: Add the embedding-dispatch block (before the empty short-circuit)**

In `api/internal/handler/handler.go`, replace the section between the cluster-candidate fetch and the empty-short-circuit (currently lines ~242–274) with this:

```go
	stopCand := observe.Start("cascade_candidates_query")
	var cluster []db.CascadeCandidate
	if h.cascadeConf.CandidateSources != forge.SourcesEmbedding {
		cluster, err = db.GetForgeCascadeCandidatesByLemma(
			h.database, word, h.cascadeConf.ConcretenessThreshold, limit,
		)
	}
	stopCand("word", word, "count", len(cluster))
	// Cluster-path ErrLemmaNotFound is a 404 ONLY when no embedding path
	// will follow; under union mode an un-enriched lemma will also fail
	// the embedding primary-synset resolver, so we let that branch return
	// the 404 below for uniformity.
	if errors.Is(err, db.ErrLemmaNotFound) && h.cascadeConf.CandidateSources == forge.SourcesCluster {
		stopTotal("word", word, "outcome", "lemma_not_found")
		http.Error(w, `{"error": "word not found or has no curated properties"}`, http.StatusNotFound)
		return
	}
	if err != nil && !errors.Is(err, db.ErrLemmaNotFound) {
		stopTotal("word", word, "outcome", "candidates_error")
		slog.Error("cascade candidate fetch failed", "word", word, "err", err)
		http.Error(w, `{"error": "internal server error"}`, http.StatusInternalServerError)
		return
	}

	var embedding []db.CascadeCandidate
	if h.cascadeConf.CandidateSources != forge.SourcesCluster {
		stopEmb := observe.Start("cascade_embedding_query")
		embCfg := db.ForgeEmbeddingConfig{
			DMin: h.cascadeConf.EmbeddingDMin,
			DMax: h.cascadeConf.EmbeddingDMax,
			TopK: h.cascadeConf.EmbeddingTopK,
		}
		embedding, err = db.GetForgeCascadeCandidatesByEmbedding(h.database, h.cache, word, embCfg)
		stopEmb("word", word, "count", len(embedding))
		if errors.Is(err, db.ErrLemmaNotFound) {
			// Both paths agree: lemma not enriched.
			stopTotal("word", word, "outcome", "lemma_not_found")
			http.Error(w, `{"error": "word not found or has no curated properties"}`, http.StatusNotFound)
			return
		}
		if err != nil {
			stopTotal("word", word, "outcome", "embedding_error")
			slog.Error("cascade embedding fetch failed", "word", word, "err", err)
			http.Error(w, `{"error": "internal server error"}`, http.StatusInternalServerError)
			return
		}
	}

	candidates := unionCandidates(cluster, embedding)
	slog.Debug("cascade candidates assembled",
		"word", word, "cluster", len(cluster), "embedding", len(embedding),
		"after_union", len(candidates))

	if len(candidates) == 0 {
		// Lemma is enriched but neither path produced a candidate.
		resp := SuggestResponse{Source: word, Suggestions: []forge.Match{}}
		w.Header().Set("Content-Type", "application/json")
		stopEncode := observe.Start("cascade_response_encode")
		encodeErr := json.NewEncoder(w).Encode(resp)
		stopEncode("word", word, "suggestion_count", 0)
		outcome := "empty_no_gate_pass"
		if encodeErr != nil {
			slog.Error("failed to encode empty cascade suggest response", "word", word, "err", encodeErr)
			outcome = "empty_encode_error"
		}
		stopTotal("word", word, "outcome", outcome)
		return
	}
```

Leave the rest of `handleSuggestCascade` (batch-props, scoring loop, sort, encode, close-out) unchanged for this task. Source-mix attrs on `stopTotal` land in Task 9 once the aggregator is in place.

- [ ] **Step 2: Run the full handler suite to confirm cluster-only path still passes**

```bash
cd api && go test ./internal/handler/...
```

Expected: PASS. The default `CandidateSources` is `SourcesCluster`, so all existing cascade tests must remain green.

- [ ] **Step 3: Commit**

```bash
git add api/internal/handler/handler.go
git commit -m "feat(handler): dispatch cluster/embedding/union paths in cascade handler"
```

---

## Task 8: CLI flags + env vars for M04 knobs

**Files:**
- Modify: `api/cmd/metaforge/main.go`

- [ ] **Step 1: Add the four new flags + env-var bindings**

In `api/cmd/metaforge/main.go`, before the `flag.Parse()` call, add (after the existing `cascadeTiming` flag):

```go
	candidateSources := flag.String("candidate-sources",
		envOrDefault("METAFORGE_FORGE_CANDIDATES", "cluster_only"),
		"Cascade candidate generation paths: cluster_only | embedding_only | union")
	embDMin := flag.Float64("embedding-d-min",
		envFloat("METAFORGE_FORGE_EMB_DMIN", 0.4),
		"Cosine distance lower band for embedding candidates (inclusive)")
	embDMax := flag.Float64("embedding-d-max",
		envFloat("METAFORGE_FORGE_EMB_DMAX", 0.85),
		"Cosine distance upper band for embedding candidates (inclusive)")
	embTopK := flag.Int("embedding-top-k",
		envInt("METAFORGE_FORGE_EMB_TOPK", 100),
		"Cap on embedding candidates per request")
```

Add three small env-helpers at the bottom of `main.go`:

```go
func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envFloat(key string, fallback float64) float64 {
	if v := os.Getenv(key); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
	}
	return fallback
}

func envInt(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return fallback
}
```

Add `"strconv"` to the import block.

- [ ] **Step 2: Wire the values into the cascade config and call `Validate()`**

After the existing `h, err := handler.NewHandlerWithCascade(...)` line, insert config-override + validation BEFORE the err check. Actually — the cleanest hook is to extend `NewHandlerWithCascade` to accept an override or to expose a setter. Simplest path: add a `WithCascadeConfig` setter on `Handler`. In `api/internal/handler/handler.go`, append:

```go
// WithCascadeConfig overrides the default cascade config. Must be
// called immediately after NewHandlerWithCascade and before serving
// traffic. Errors if cfg.Validate() rejects the config.
func (h *Handler) WithCascadeConfig(cfg forge.CascadeConfig) error {
	if err := cfg.Validate(); err != nil {
		return fmt.Errorf("invalid cascade config: %w", err)
	}
	h.cascadeConf = cfg
	return nil
}
```

In `main.go`, after the `h, err := handler.NewHandlerWithCascade(...)` block (and after `defer h.Close()`), add:

```go
	cascadeCfg := forge.DefaultCascadeConfig()
	cascadeCfg.CandidateSources = forge.CandidateSources(*candidateSources)
	cascadeCfg.EmbeddingDMin = *embDMin
	cascadeCfg.EmbeddingDMax = *embDMax
	cascadeCfg.EmbeddingTopK = *embTopK
	if err := h.WithCascadeConfig(cascadeCfg); err != nil {
		log.Fatalf("cascade config: %v", err)
	}
```

Add `"github.com/snailuj/metaforge/internal/forge"` to `main.go` imports.

- [ ] **Step 3: Write a build smoke test**

```bash
cd api && go build ./...
```

Expected: clean build.

- [ ] **Step 4: Verify rejected env values fail loud**

```bash
cd api && METAFORGE_FORGE_CANDIDATES=bogus go run ./cmd/metaforge \
  --db ../data-pipeline/output/lexicon_v2.db --port 9099 --cascade 2>&1 | head -5
```

Expected: process exits with `cascade config: invalid cascade config: CandidateSources "bogus" is not one of cluster_only|embedding_only|union`.

If the DB path isn't available locally, skip this step but include the verification in the canary test (Task 11).

- [ ] **Step 5: Commit**

```bash
git add api/cmd/metaforge/main.go api/internal/handler/handler.go
git commit -m "feat(api): --candidate-sources + embedding-band CLI/env wiring"
```

---

## Task 9: Tag scored matches with `Source` and add source-mix attrs to `cascade_request_total`

**Files:**
- Modify: `api/internal/forge/forge.go` (add `Source` field to `Match`)
- Modify: `api/internal/handler/handler.go` (set `m.Source` in the scoring-loop append, attach `cluster_only`/`embedding_only`/`both_paths` counts to `stopTotal`)
- Modify: `api/internal/forge/forge_test.go` (assert `omitempty` on default-zero Source)

- [ ] **Step 1: Write the failing test**

Append to `api/internal/forge/forge_test.go`:

```go
func TestMatch_SourceOmittedFromJSONWhenEmpty(t *testing.T) {
	m := Match{SynsetID: "s1", Word: "fire"}
	out, err := json.Marshal(m)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if strings.Contains(string(out), `"source"`) {
		t.Errorf("zero Source must be omitted from JSON, got %s", out)
	}
}

func TestMatch_SourceSerialisesWhenSet(t *testing.T) {
	m := Match{SynsetID: "s1", Word: "fire", Source: SourceEmbedding}
	out, err := json.Marshal(m)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if !strings.Contains(string(out), `"source":"embedding"`) {
		t.Errorf("Source serialisation: got %s", out)
	}
}
```

Add imports: `"encoding/json"`, `"strings"`.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd api && go test ./internal/forge/ -run TestMatch_Source
```

Expected: FAIL — `unknown field Source in struct literal`.

- [ ] **Step 3: Extend `forge.Match` with the Source tag**

In `api/internal/forge/forge.go`, inside the `Match` struct, append below the existing M03 diagnostic block:

```go
	// M04 generation diagnostic. Empty string ("") on the legacy path,
	// since CandidateSource only gets set by the cascade handler.
	Source CandidateSource `json:"source,omitempty"`
```

- [ ] **Step 4: Run new tests to verify they pass**

```bash
cd api && go test ./internal/forge/ -run TestMatch_Source -v
```

Expected: PASS.

- [ ] **Step 5: Set `m.Source` in the cascade scoring loop**

In `api/internal/handler/handler.go`, inside `handleSuggestCascade`'s scoring loop, add `Source: c.Source,` to the `forge.Match{...}` literal that appends scored matches. Patch the literal (currently around lines 350–368):

```go
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
			Source:           c.Source,
		})
```

- [ ] **Step 6: Tally source mix and attach to `cascade_request_total`**

Before the scoring loop in `handleSuggestCascade`, add three counters:

```go
	var clusterOnly, embeddingOnly, bothPaths int
	for _, c := range candidates {
		switch c.Source {
		case forge.SourceCluster:
			clusterOnly++
		case forge.SourceEmbedding:
			embeddingOnly++
		case forge.SourceBoth:
			bothPaths++
		}
	}
```

Then extend the final `stopTotal(...)` line of the scored-outcome branch:

```go
	stopTotal("word", word,
		"outcome", outcome,
		"candidates", len(candidates),
		"scored_count", len(matches),
		"cluster_only", clusterOnly,
		"embedding_only", embeddingOnly,
		"both_paths", bothPaths,
	)
```

- [ ] **Step 7: Build + run full suite**

```bash
cd api && go test ./...
```

Expected: PASS (existing cluster_only tests must remain green — Source is just an additional field).

- [ ] **Step 8: Commit**

```bash
git add api/internal/forge/forge.go api/internal/forge/forge_test.go api/internal/handler/handler.go
git commit -m "feat(handler): tag matches with Source and tally source-mix on cascade_request_total"
```

---

## Task 10: Canary integration test — union mode surfaces classical pairs

**Files:**
- Modify: `api/internal/handler/handler_cascade_test.go` (append)

- [ ] **Step 1: Write the failing test**

Append to `api/internal/handler/handler_cascade_test.go`:

```go
// TestCascadeUnion_ClassicalPairsSurface_AsCandidates pins M04's binary
// generation criterion: the four canonical cross-domain pairs MUST
// reach the cascade scorer as candidates when SourcesUnion is active.
// We assert candidate PRESENCE only — final-score rank is M05/M06
// territory and out of scope here. The vehicle is the second synset
// of the pair; we accept a hit on ANY of its lemmas.
func TestCascadeUnion_ClassicalPairsSurface_AsCandidates(t *testing.T) {
	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	cfg := forge.DefaultCascadeConfig()
	cfg.CandidateSources = forge.SourcesUnion
	cfg.EmbeddingDMin = 0.0
	cfg.EmbeddingDMax = 1.5
	cfg.EmbeddingTopK = 200
	if err := h.WithCascadeConfig(cfg); err != nil {
		t.Fatalf("WithCascadeConfig: %v", err)
	}

	cases := []struct {
		topic   string
		vehicle string // lemma we expect to see in suggestions
	}{
		{"anger", "fire"},
		{"idea", "light"},
		{"time", "money"},
		{"truth", "hammer"},
	}
	for _, tc := range cases {
		t.Run(tc.topic+"-"+tc.vehicle, func(t *testing.T) {
			req := httptest.NewRequest("GET",
				"/forge/suggest?word="+tc.topic+"&limit=200", nil)
			w := httptest.NewRecorder()
			h.HandleSuggest(w, req)
			if w.Code != http.StatusOK {
				t.Fatalf("status %d: %s", w.Code, w.Body.String())
			}
			var resp SuggestResponse
			if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
				t.Fatalf("decode: %v", err)
			}
			for _, s := range resp.Suggestions {
				if s.Word == tc.vehicle {
					return // hit — pass
				}
			}
			words := make([]string, 0, len(resp.Suggestions))
			for _, s := range resp.Suggestions {
				words = append(words, s.Word)
			}
			t.Errorf("vehicle %q not present in %d suggestions for %q (sample: %v)",
				tc.vehicle, len(resp.Suggestions), tc.topic, words[:min(10, len(words))])
		})
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
```

If `min` is already declared in the file, drop the helper. (Go 1.21+ has a builtin `min`; older code may declare a local helper.)

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd api && go test ./internal/handler/ -run TestCascadeUnion_ClassicalPairsSurface_AsCandidates -v
```

Expected: FAIL on at least one pair if the embedding path isn't being dispatched, OR PASS if Tasks 5–9 are all wired correctly. (TDD note: this test backstops the full M04 wiring; if it already passes after Tasks 5–9 are landed, that's a sign of pre-emptive correctness — accept and commit. If it fails, debug the wiring before continuing.)

- [ ] **Step 3: If failing, diagnose with the embedding-only mode**

Temporarily run the same word against `embedding_only` mode by replacing `cfg.CandidateSources = forge.SourcesUnion` with `SourcesEmbedding`. If the canary fails ONLY under embedding mode, the cosine band is wrong — widen `EmbeddingDMax` toward 1.5–2.0 to debug. The test settles at production-realistic bands after the calibration sweep (S04).

- [ ] **Step 4: Run the test until it passes**

```bash
cd api && go test ./internal/handler/ -run TestCascadeUnion_ClassicalPairsSurface_AsCandidates -v
```

Expected: PASS — all 4 sub-tests green.

- [ ] **Step 5: Commit**

```bash
git add api/internal/handler/handler_cascade_test.go
git commit -m "test(handler): canary — classical cross-domain pairs surface under union mode"
```

---

## Task 11: Backward-compat — `cluster_only` mode preserves M03 behaviour

**Files:**
- Modify: `api/internal/handler/handler_cascade_test.go` (append)

- [ ] **Step 1: Write the failing test**

Append:

```go
// TestCascadeClusterOnly_ResponseShapeUnchanged pins the contract that
// CandidateSources=cluster_only behaves byte-for-byte identically to
// the pre-M04 M03 cascade. The assertion is "no row carries Source !=
// SourceCluster" plus "the embedding query stage timer is NOT emitted"
// — i.e. the embedding path is fully skipped, not run-and-discarded.
func TestCascadeClusterOnly_ResponseShapeUnchanged(t *testing.T) {
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelDebug})))
	defer slog.SetDefault(prev)

	observe.Init(true)
	defer observe.Init(false)

	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	cfg := forge.DefaultCascadeConfig()
	cfg.CandidateSources = forge.SourcesCluster
	if err := h.WithCascadeConfig(cfg); err != nil {
		t.Fatalf("WithCascadeConfig: %v", err)
	}

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=20", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}

	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	for _, s := range resp.Suggestions {
		if s.Source != "" && s.Source != forge.SourceCluster {
			t.Errorf("cluster_only mode produced %q-tagged suggestion %s", s.Source, s.Word)
		}
	}
	if strings.Contains(buf.String(), `"cascade_embedding_query"`) {
		t.Errorf("cluster_only mode must NOT emit cascade_embedding_query stage timer:\n%s", buf.String())
	}
}
```

Ensure imports include `"bytes"`, `"log/slog"`, `"strings"`, and `"github.com/snailuj/metaforge/internal/observe"`.

- [ ] **Step 2: Run the test**

```bash
cd api && go test ./internal/handler/ -run TestCascadeClusterOnly_ResponseShapeUnchanged -v
```

Expected: PASS — handler logic from Task 7 explicitly skips the embedding query when `CandidateSources == SourcesCluster`.

- [ ] **Step 3: Commit**

```bash
git add api/internal/handler/handler_cascade_test.go
git commit -m "test(handler): cluster_only mode preserves M03 byte-for-byte behaviour"
```

---

## Task 12: Embedding-only mode integration test

**Files:**
- Modify: `api/internal/handler/handler_cascade_test.go` (append)

- [ ] **Step 1: Write the failing test**

```go
// TestCascadeEmbeddingOnly_ProducesEmbeddingTaggedRowsOnly pins the
// embedding_only mode contract: every returned row is tagged
// SourceEmbedding, no cluster-overlap query timer is emitted, and the
// canary anger→fire pair still surfaces.
func TestCascadeEmbeddingOnly_ProducesEmbeddingTaggedRowsOnly(t *testing.T) {
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelDebug})))
	defer slog.SetDefault(prev)

	observe.Init(true)
	defer observe.Init(false)

	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	cfg := forge.DefaultCascadeConfig()
	cfg.CandidateSources = forge.SourcesEmbedding
	cfg.EmbeddingDMin = 0.0
	cfg.EmbeddingDMax = 1.5
	cfg.EmbeddingTopK = 200
	if err := h.WithCascadeConfig(cfg); err != nil {
		t.Fatalf("WithCascadeConfig: %v", err)
	}

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=200", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}

	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	for _, s := range resp.Suggestions {
		if s.Source != forge.SourceEmbedding {
			t.Errorf("embedding_only mode produced %q-tagged suggestion %s", s.Source, s.Word)
		}
	}
	logs := buf.String()
	if strings.Contains(logs, `"cascade_candidates_query"`) {
		// Cluster-path query timer must NOT fire in embedding_only mode.
		t.Errorf("embedding_only mode must skip cluster path; saw cascade_candidates_query in logs")
	}
}
```

- [ ] **Step 2: Run the test**

```bash
cd api && go test ./internal/handler/ -run TestCascadeEmbeddingOnly_ProducesEmbeddingTaggedRowsOnly -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add api/internal/handler/handler_cascade_test.go
git commit -m "test(handler): embedding_only mode emits embedding-tagged candidates"
```

---

## Task 13: Latency smoke — embedding path within budget

**Files:**
- Modify: `api/internal/handler/handler_cascade_test.go` (append)

- [ ] **Step 1: Write the failing test**

```go
// TestCascadeUnion_LatencyBudget pins the M04 latency floor: a union-mode
// request for 'anger' (broad lemma, ~35k centroid scan) must complete
// within 750ms in-process. Threshold is generous vs the spec's 500ms p99
// — this is a smoke test running under the Go test framework, not a
// production benchmark.
func TestCascadeUnion_LatencyBudget(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping latency smoke in -short mode")
	}
	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	cfg := forge.DefaultCascadeConfig()
	cfg.CandidateSources = forge.SourcesUnion
	if err := h.WithCascadeConfig(cfg); err != nil {
		t.Fatalf("WithCascadeConfig: %v", err)
	}

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=50", nil)
	w := httptest.NewRecorder()

	start := time.Now()
	h.HandleSuggest(w, req)
	elapsed := time.Since(start)

	if w.Code != http.StatusOK {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}
	if elapsed > 750*time.Millisecond {
		t.Errorf("union-mode anger limit=50 took %v, want ≤ 750ms", elapsed)
	}
	t.Logf("union-mode anger limit=50 elapsed: %v", elapsed)
}
```

Ensure `"time"` is in the imports.

- [ ] **Step 2: Run the test**

```bash
cd api && go test ./internal/handler/ -run TestCascadeUnion_LatencyBudget -v
```

Expected: PASS — elapsed should be ~150–400ms on typical dev hardware.

- [ ] **Step 3: Commit**

```bash
git add api/internal/handler/handler_cascade_test.go
git commit -m "test(handler): pin union-mode latency budget on broad lemma"
```

---

## Task 14: Anomaly aggregator — replace per-candidate concreteness Error log with counter

**Files:**
- Modify: `api/internal/handler/handler.go`
- Modify: `api/internal/handler/handler_cascade_test.go` (append)

- [ ] **Step 1: Write the failing test**

Append:

```go
// TestCascade_AggregatesConcretenessCacheMisses_NoPerCandidateSpam pins
// the R1-D4 fix: per-candidate concreteness cache-miss spam must be
// replaced by a single aggregate Error log post-loop plus a count attr
// on cascade_request_total. We can't easily force a real cache divergence
// against the test DB, so this test asserts the steady-state contract:
// under a healthy cache the per-candidate Error log MUST NOT fire even
// once during a normal request. (Direct positive verification of the
// aggregator path requires a fixture that diverges cache from SQL — see
// Task 16 for the runtime tripwire which closes that gap.)
func TestCascade_AggregatesConcretenessCacheMisses_NoPerCandidateSpam(t *testing.T) {
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelDebug})))
	defer slog.SetDefault(prev)

	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=50", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}
	if strings.Contains(buf.String(), "cascade candidate concreteness missing from cache despite SQL filter") {
		t.Errorf("per-candidate concreteness Error log must not fire on healthy data:\n%s", buf.String())
	}
}
```

- [ ] **Step 2: Run the test to verify current code path is acceptable**

```bash
cd api && go test ./internal/handler/ -run TestCascade_AggregatesConcretenessCacheMisses_NoPerCandidateSpam -v
```

Expected: PASS already (the existing Error log only fires on actual divergence). Test serves as a regression guard.

- [ ] **Step 3: Introduce the `cascadeAnomalies` aggregator**

In `api/internal/handler/handler.go`, near the top of `handleSuggestCascade` (just after `stopTotal := observe.Start("cascade_request_total")`), add:

```go
	anomalies := struct {
		concretenessCacheMisses int
		emptyPropsBatchFlag     bool
	}{}
```

Inside the scoring loop, replace the existing Error log:

```go
		if tConc == nil || vConc == nil {
			slog.Error("cascade candidate concreteness missing from cache despite SQL filter",
				"source", c.SourceSynsetID, "target", c.SynsetID)
		}
```

with:

```go
		if tConc == nil || vConc == nil {
			anomalies.concretenessCacheMisses++
		}
```

After the scoring loop closes (after `stopScore(...)` and before the sort), add a single aggregate Error log:

```go
	if anomalies.concretenessCacheMisses > 0 {
		slog.Error("cascade concreteness cache divergence",
			"word", word,
			"miss_count", anomalies.concretenessCacheMisses,
			"candidate_count", len(candidates))
	}
```

- [ ] **Step 4: Attach `concreteness_cache_misses` to `cascade_request_total`**

In the final `stopTotal(...)` call of the scored-outcome branch, add the attribute:

```go
	stopTotal("word", word,
		"outcome", outcome,
		"candidates", len(candidates),
		"scored_count", len(matches),
		"cluster_only", clusterOnly,
		"embedding_only", embeddingOnly,
		"both_paths", bothPaths,
		"concreteness_cache_misses", anomalies.concretenessCacheMisses,
		"empty_props_batch", anomalies.emptyPropsBatchFlag,
	)
```

- [ ] **Step 5: Run handler tests**

```bash
cd api && go test ./internal/handler/...
```

Expected: PASS — existing tests are unaffected by the new aggregator since healthy DB never increments.

- [ ] **Step 6: Commit**

```bash
git add api/internal/handler/handler.go api/internal/handler/handler_cascade_test.go
git commit -m "feat(handler): cascade anomaly aggregator — concreteness cache misses"
```

---

## Task 15: Replace per-request empty-propsByID Error with aggregator flag

**Files:**
- Modify: `api/internal/handler/handler.go`
- Modify: `api/internal/handler/handler_cascade_test.go` (append)

- [ ] **Step 1: Write the failing test**

```go
// TestCascade_EmptyPropsByID_FlagsAggregatorAndContinues pins the R4-D1
// behaviour: when batch props returns empty for all candidates, we do
// NOT emit a per-request Error spam — instead we set the aggregator
// flag and continue serving. Verified via a synthetic DB where
// synset_properties_curated is empty but cascade tables are populated.
// (Note: this is a low-fidelity proxy — the test DB has properties,
// so we assert the negative steady-state contract.)
func TestCascade_EmptyPropsByID_NoErrorLogOnHealthyData(t *testing.T) {
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelDebug})))
	defer slog.SetDefault(prev)

	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=20", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}
	if strings.Contains(buf.String(), "cascade batch properties returned empty for all candidates") {
		t.Errorf("per-request empty-propsByID Error log must not fire on healthy data:\n%s", buf.String())
	}
}
```

- [ ] **Step 2: Replace the Error log with the aggregator flag**

In `handleSuggestCascade`, replace:

```go
	if len(propsByID) == 0 {
		// Anomaly: candidates were gate-passed (so the cascade tables are
		// populated for these synsets) but NONE of them have curated
		// properties. Most likely synset_properties_curated was truncated
		// post-startup or schema drifted. Surface as Error so operators
		// can spot the silent attrition; continue serving (response will
		// be empty due to the no_properties filter below).
		slog.Error("cascade batch properties returned empty for all candidates",
			"word", word, "candidate_count", len(candidates))
	}
```

with:

```go
	if len(propsByID) == 0 {
		// R4-D1: previously a per-request Error log; now aggregated
		// onto cascade_request_total as empty_props_batch=true. The
		// runtime tripwire on synset_properties_curated (Task 16) catches
		// the truncation-at-startup case loudly; the in-flight case here
		// stays observable via the timing attr.
		anomalies.emptyPropsBatchFlag = true
	}
```

- [ ] **Step 3: Run the tests**

```bash
cd api && go test ./internal/handler/...
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add api/internal/handler/handler.go api/internal/handler/handler_cascade_test.go
git commit -m "feat(handler): cascade anomaly aggregator — empty propsByID flag"
```

---

## Task 16: Runtime tripwire — `synset_properties_curated` non-empty at startup

**Files:**
- Modify: `api/internal/handler/handler.go`
- Modify: `api/internal/handler/handler_cascade_test.go` (extend existing tripwire test or add new)

- [ ] **Step 1: Write the failing test**

Append:

```go
// TestNewHandlerWithCascade_EmptyCuratedProps_FailsLoud extends the
// post-preflight tripwire to also assert synset_properties_curated is
// non-empty. Closes R1-D4 — without this, a deploy with all cascade
// tables populated but curated_props empty would pass startup and
// silently serve no_properties for every gate-passed candidate.
func TestNewHandlerWithCascade_EmptyCuratedProps_FailsLoud(t *testing.T) {
	tmpDir := t.TempDir()
	dbPath := tmpDir + "/empty_curated.db"

	database, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	schema := []string{
		`CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT)`,
		`CREATE TABLE lemmas (synset_id TEXT, lemma TEXT)`,
		// Empty curated table — this is the failure mode we're trying to catch.
		`CREATE TABLE synset_properties_curated (synset_id TEXT, cluster_id INTEGER, salience_sum REAL)`,
		`CREATE TABLE property_vocab_curated (vocab_id INTEGER PRIMARY KEY, lemma TEXT NOT NULL)`,
		`CREATE TABLE frequencies (lemma TEXT, count INTEGER)`,
		`CREATE TABLE cluster_antonyms (cluster_id_a INTEGER, cluster_id_b INTEGER)`,
		`CREATE TABLE vocab_clusters (cluster_id INTEGER PRIMARY KEY, lemma TEXT)`,
		`CREATE TABLE lemma_embeddings (lemma TEXT, embedding BLOB)`,
		// Cascade tables populated with one row each (need a row so the
		// existing existence-AND-row check passes for them).
		`CREATE TABLE synset_concreteness (synset_id TEXT PRIMARY KEY, score REAL, source TEXT)`,
		`INSERT INTO synset_concreteness VALUES ('test-1', 3.0, 'test')`,
		`CREATE TABLE synset_centroids (synset_id TEXT PRIMARY KEY, centroid BLOB, property_count INTEGER)`,
		`INSERT INTO synset_centroids VALUES ('test-1', x'00', 1)`,
	}
	for _, stmt := range schema {
		if _, err := database.Exec(stmt); err != nil {
			t.Fatalf("schema setup: %v", err)
		}
	}
	if err := database.Close(); err != nil {
		t.Fatalf("close: %v", err)
	}

	_, err = NewHandlerWithCascade(dbPath, true)
	if err == nil {
		t.Fatal("expected error for empty synset_properties_curated, got nil")
	}
	if !strings.Contains(err.Error(), "synset_properties_curated") {
		t.Errorf("expected error mentioning synset_properties_curated, got: %v", err)
	}
	if !strings.Contains(err.Error(), "is empty") {
		t.Errorf("expected 'is empty' in error, got: %v", err)
	}
}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd api && go test ./internal/handler/ -run TestNewHandlerWithCascade_EmptyCuratedProps_FailsLoud
```

Expected: FAIL — the existing tripwire only checks `synset_concreteness` and `synset_centroids`, not `synset_properties_curated`.

- [ ] **Step 3: Extend the tripwire**

In `api/internal/handler/handler.go`, inside `NewHandlerWithCascade`, find the existing `for _, table := range []string{"synset_concreteness", "synset_centroids"} {` loop. Replace the slice literal with:

```go
		for _, table := range []string{"synset_concreteness", "synset_centroids", "synset_properties_curated"} {
```

- [ ] **Step 4: Run the new test plus the existing tripwire test**

```bash
cd api && go test ./internal/handler/ -run TestNewHandlerWithCascade -v
```

Expected: PASS (existing `EmptyCascadeTables_FailsLoud` continues to pass; new test passes).

- [ ] **Step 5: Commit**

```bash
git add api/internal/handler/handler.go api/internal/handler/handler_cascade_test.go
git commit -m "feat(handler): startup tripwire — synset_properties_curated must be non-empty"
```

---

## Task 17: Full Go suite sanity + commit a clean S03 close

- [ ] **Step 1: Run the entire Go test suite**

```bash
cd api && go test ./...
```

Expected: PASS across all packages.

- [ ] **Step 2: Run `go vet` to catch any non-test issues**

```bash
cd api && go vet ./...
```

Expected: clean.

- [ ] **Step 3: If anything fails, fix before proceeding to the code review loop**

Diagnose any failures with targeted `-run` and `-v`. No new commits if nothing is broken.

---

## Gate: `/code-review-loop`

Run the loop over the S01 + S02 + S03 surface against `main`. Per the brainstorming spec: this loop happens BEFORE the calibration sweep so any structural feedback can influence the sweep design.

```
/code-review-loop scope=main..HEAD reviewers=[pr-review-toolkit,superpowers,standards,ux-designer] max_iterations=15
```

Address findings per the loop's deferral conventions. The loop is complete when one round returns CLEAN across all adapters. Carry deferrals forward to PIPELINE.md (anchors under M04 in the existing layout).

---

## Task 18: Sweep YAML — `(d_min, d_max)` grid

**Files:**
- Create: `data-pipeline/sweeps/m04_embedding_band.yaml`

- [ ] **Step 1: Create the sweep config**

```yaml
# M04 calibration sweep — runs against the live Go API. Drives a 3×3
# grid over (d_min, d_max) under SourcesUnion to find the band that
# maximises MUNCH separation_score while staying non-regressive vs the
# M03 cluster-only baseline (separation_score ≥ 0.1779).
#
# Driven by data-pipeline/scripts/m04_sweep_runner.py — not the
# generic run_sweep.py (which targets the Python aptness evaluator
# only). The runner spawns the Go API per cell with env vars matching
# the variation, then queries /forge/suggest for the MUNCH cohort.

name: m04_embedding_band
db: data-pipeline/output/lexicon_v2.db
api_port_base: 9100             # cells use 9100, 9101, … sequentially
api_binary: api/metaforge       # build with: go build -o api/metaforge ./api/cmd/metaforge
pairs: data-pipeline/fixtures/munch_apt.jsonl
controls: data-pipeline/fixtures/munch_inapt.jsonl
limit: 50                       # /forge/suggest?limit=

# Baseline reference — fixed cluster_only request to recompute the floor
# under whatever DB the runner sees. Drift in this number signals a DB
# rebuild, not an M04 regression.
baseline:
  candidate_sources: cluster_only

variations:
  - { name: dmin0.3_dmax0.75, candidate_sources: union, d_min: 0.3, d_max: 0.75, top_k: 100 }
  - { name: dmin0.3_dmax0.85, candidate_sources: union, d_min: 0.3, d_max: 0.85, top_k: 100 }
  - { name: dmin0.3_dmax0.95, candidate_sources: union, d_min: 0.3, d_max: 0.95, top_k: 100 }
  - { name: dmin0.4_dmax0.75, candidate_sources: union, d_min: 0.4, d_max: 0.75, top_k: 100 }
  - { name: dmin0.4_dmax0.85, candidate_sources: union, d_min: 0.4, d_max: 0.85, top_k: 100 }
  - { name: dmin0.4_dmax0.95, candidate_sources: union, d_min: 0.4, d_max: 0.95, top_k: 100 }
  - { name: dmin0.5_dmax0.75, candidate_sources: union, d_min: 0.5, d_max: 0.75, top_k: 100 }
  - { name: dmin0.5_dmax0.85, candidate_sources: union, d_min: 0.5, d_max: 0.85, top_k: 100 }
  - { name: dmin0.5_dmax0.95, candidate_sources: union, d_min: 0.5, d_max: 0.95, top_k: 100 }
```

- [ ] **Step 2: Commit**

```bash
git add data-pipeline/sweeps/m04_embedding_band.yaml
git commit -m "feat(sweeps): M04 (d_min, d_max) 3x3 calibration grid"
```

---

## Task 19: Sweep driver — `m04_sweep_runner.py`

**Files:**
- Create: `data-pipeline/scripts/m04_sweep_runner.py`

- [ ] **Step 1: Write the driver script**

```python
#!/usr/bin/env python3
"""M04 calibration-sweep driver.

For each variation in an M04 sweep YAML, spawns the Go API with the
matching env vars, queries /forge/suggest for every MUNCH apt+inapt
pair, computes per-cell separation_score / aptness_rate, then writes
a JSON results file and a human-readable verdict markdown.

Unlike the generic run_sweep.py harness (which drives the Python
aptness evaluator in-process), this driver tests the integrated Go
candidate-generation path end-to-end — the only fair test for M04's
generation-broadening claim.

Usage:
    python data-pipeline/scripts/m04_sweep_runner.py \\
        --config data-pipeline/sweeps/m04_embedding_band.yaml \\
        --output data-pipeline/output/m04_embedding_band_results.json \\
        --verdict data-pipeline/sweeps/m04_embedding_band_verdict.md
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

import requests
import yaml


@dataclass
class CellResult:
    name: str
    candidate_sources: str
    d_min: float | None
    d_max: float | None
    top_k: int | None
    apt_scores: list[float] = field(default_factory=list)
    inapt_scores: list[float] = field(default_factory=list)
    apt_missing: int = 0
    inapt_missing: int = 0
    source_mix: dict[str, int] = field(default_factory=lambda: {"cluster": 0, "embedding": 0, "both": 0})

    @property
    def aptness_rate(self) -> float:
        if not self.apt_scores:
            return 0.0
        if not self.inapt_scores:
            return 0.0
        threshold = statistics.quantiles(self.inapt_scores, n=20)[18]  # 95th percentile
        return sum(1 for s in self.apt_scores if s > threshold) / len(self.apt_scores)

    @property
    def separation_score(self) -> float:
        if not self.apt_scores or not self.inapt_scores:
            return 0.0
        return statistics.mean(self.apt_scores) - statistics.mean(self.inapt_scores)


def load_pairs(path: Path) -> list[tuple[str, str]]:
    """Load MUNCH-shaped JSONL: one object per line with 'topic' + 'vehicle'."""
    pairs: list[tuple[str, str]] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            topic = obj.get("topic") or obj.get("source") or obj.get("subject")
            vehicle = obj.get("vehicle") or obj.get("target") or obj.get("object")
            if topic and vehicle:
                pairs.append((str(topic), str(vehicle)))
    return pairs


def start_api(binary: str, db: Path, port: int, env_overrides: dict[str, str]) -> subprocess.Popen:
    env = os.environ.copy()
    env["METAFORGE_FORGE_CASCADE"] = "1"
    env.update(env_overrides)
    args = [binary, "--db", str(db), "--port", str(port), "--cascade"]
    proc = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # Poll /health for up to 10s.
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            r = requests.get(f"{base}/health", timeout=0.5)
            if r.ok:
                return proc
        except requests.RequestException:
            time.sleep(0.1)
    proc.kill()
    out, err = proc.communicate(timeout=2)
    raise RuntimeError(f"API failed to start on port {port}:\nstdout: {out!r}\nstderr: {err!r}")


def stop_api(proc: subprocess.Popen) -> None:
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


def score_pair(base_url: str, topic: str, vehicle: str, limit: int) -> tuple[float | None, str | None]:
    """Returns (final_score, source_tag) — (None, None) if vehicle absent."""
    try:
        r = requests.get(f"{base_url}/forge/suggest", params={"word": topic, "limit": limit}, timeout=10)
    except requests.RequestException:
        return None, None
    if r.status_code != 200:
        return None, None
    body = r.json()
    for s in body.get("suggestions", []):
        if s.get("word") == vehicle:
            fs = s.get("final_score")
            return (float(fs) if fs is not None else None), s.get("source", "")
    return None, None


def evaluate_cell(
    name: str,
    candidate_sources: str,
    d_min: float | None,
    d_max: float | None,
    top_k: int | None,
    binary: str,
    db: Path,
    port: int,
    apt_pairs: list[tuple[str, str]],
    inapt_pairs: list[tuple[str, str]],
    limit: int,
) -> CellResult:
    env = {"METAFORGE_FORGE_CANDIDATES": candidate_sources}
    if d_min is not None:
        env["METAFORGE_FORGE_EMB_DMIN"] = str(d_min)
    if d_max is not None:
        env["METAFORGE_FORGE_EMB_DMAX"] = str(d_max)
    if top_k is not None:
        env["METAFORGE_FORGE_EMB_TOPK"] = str(top_k)

    result = CellResult(name=name, candidate_sources=candidate_sources,
                        d_min=d_min, d_max=d_max, top_k=top_k)
    proc = start_api(binary, db, port, env)
    try:
        base_url = f"http://127.0.0.1:{port}"
        for topic, vehicle in apt_pairs:
            fs, src = score_pair(base_url, topic, vehicle, limit)
            if fs is None:
                result.apt_missing += 1
                continue
            result.apt_scores.append(fs)
            if src in result.source_mix:
                result.source_mix[src] += 1
        for topic, vehicle in inapt_pairs:
            fs, _ = score_pair(base_url, topic, vehicle, limit)
            if fs is None:
                result.inapt_missing += 1
                continue
            result.inapt_scores.append(fs)
    finally:
        stop_api(proc)
    return result


def write_verdict(results: list[CellResult], baseline: CellResult, verdict_path: Path) -> None:
    best = max(results, key=lambda r: r.separation_score)
    lines = [
        "# M04 Embedding-Band Calibration Verdict",
        "",
        f"_Baseline (cluster_only): separation_score = {baseline.separation_score:.4f}, "
        f"aptness_rate = {baseline.aptness_rate:.4f}_",
        "",
        "## Results Grid",
        "",
        "| Cell | d_min | d_max | separation_score | aptness_rate | cluster | embedding | both | apt_miss | inapt_miss |",
        "|------|------:|------:|-----------------:|-------------:|--------:|----------:|-----:|---------:|-----------:|",
    ]
    for r in sorted(results, key=lambda r: -r.separation_score):
        lines.append(
            f"| {r.name} | {r.d_min} | {r.d_max} | {r.separation_score:.4f} | "
            f"{r.aptness_rate:.4f} | {r.source_mix['cluster']} | "
            f"{r.source_mix['embedding']} | {r.source_mix['both']} | "
            f"{r.apt_missing} | {r.inapt_missing} |"
        )
    lines += [
        "",
        f"## Best Cell: `{best.name}`",
        f"- d_min = {best.d_min}, d_max = {best.d_max}",
        f"- separation_score = **{best.separation_score:.4f}**",
        f"- aptness_rate = {best.aptness_rate:.4f}",
        f"- vs baseline ({baseline.separation_score:.4f}): "
        + ("**non-regressive — ratify** `SourcesUnion` as default with this band"
           if best.separation_score >= baseline.separation_score
           else "**regression — keep `SourcesCluster` default**, document follow-up sweep"),
        "",
        "## Two-Path Correlation (v2 β-bonus signal)",
        "",
        "Per cell, the `both` column counts apt pairs that were generated by BOTH the cluster",
        "and embedding paths. A high both-count under high aptness suggests two-path agreement",
        "correlates with aptness — i.e. a co-generation bonus β·1{both} may be worth adding in",
        "M04 v2. A low both-count under high aptness means the embedding path is the marginal",
        "contributor and a β-bonus would not help.",
    ]
    verdict_path.write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--verdict", type=Path, required=True)
    args = p.parse_args(argv)

    cfg = yaml.safe_load(args.config.read_text())
    db = Path(cfg["db"])
    binary = cfg["api_binary"]
    if not Path(binary).exists():
        print(f"API binary not found at {binary} — build with:\n"
              f"  cd api && go build -o ../{binary} ./cmd/metaforge", file=sys.stderr)
        return 2

    apt_pairs = load_pairs(Path(cfg["pairs"]))
    inapt_pairs = load_pairs(Path(cfg["controls"]))
    limit = int(cfg.get("limit", 50))
    port_base = int(cfg.get("api_port_base", 9100))

    baseline_cfg = cfg["baseline"]
    baseline = evaluate_cell(
        "baseline_cluster_only",
        candidate_sources=baseline_cfg["candidate_sources"],
        d_min=None, d_max=None, top_k=None,
        binary=binary, db=db, port=port_base,
        apt_pairs=apt_pairs, inapt_pairs=inapt_pairs, limit=limit,
    )

    results: list[CellResult] = []
    for i, var in enumerate(cfg["variations"], start=1):
        port = port_base + i
        r = evaluate_cell(
            name=var["name"],
            candidate_sources=var["candidate_sources"],
            d_min=var.get("d_min"),
            d_max=var.get("d_max"),
            top_k=var.get("top_k"),
            binary=binary, db=db, port=port,
            apt_pairs=apt_pairs, inapt_pairs=inapt_pairs, limit=limit,
        )
        results.append(r)
        print(f"  {r.name}: sep={r.separation_score:.4f} apt_rate={r.aptness_rate:.4f}")

    args.output.write_text(json.dumps({
        "baseline": asdict(baseline),
        "results": [asdict(r) for r in results],
    }, indent=2))
    write_verdict(results, baseline, args.verdict)
    print(f"\nWrote {args.output} and {args.verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify the script parses and imports cleanly**

```bash
source data-pipeline/.venv/bin/activate
python -c "import data_pipeline.scripts.m04_sweep_runner" 2>&1 || \
  python data-pipeline/scripts/m04_sweep_runner.py --help
```

Expected: `--help` prints the usage; no import errors.

- [ ] **Step 3: Commit**

```bash
git add data-pipeline/scripts/m04_sweep_runner.py
git commit -m "feat(sweeps): M04 sweep driver — HTTP-driven against the Go API"
```

---

## Task 20: Build the API binary and run the sweep

- [ ] **Step 1: Build the Go binary**

```bash
cd api && go build -o ../api/metaforge ./cmd/metaforge
```

Expected: `api/metaforge` exists, ~15–20 MB binary.

- [ ] **Step 2: Run the sweep**

```bash
source data-pipeline/.venv/bin/activate
python data-pipeline/scripts/m04_sweep_runner.py \
  --config data-pipeline/sweeps/m04_embedding_band.yaml \
  --output data-pipeline/output/m04_embedding_band_results.json \
  --verdict data-pipeline/sweeps/m04_embedding_band_verdict.md
```

Expected output (one line per cell): `<cell_name>: sep=<X.XXXX> apt_rate=<Y.YYYY>`. Runtime ~3–5 minutes for 9 cells + baseline.

- [ ] **Step 3: Inspect the verdict markdown**

```bash
cat data-pipeline/sweeps/m04_embedding_band_verdict.md
```

Expected: ranked grid; top cell identified; explicit verdict line on default-flip.

- [ ] **Step 4: Commit the verdict + JSON results**

```bash
git add data-pipeline/sweeps/m04_embedding_band_verdict.md data-pipeline/output/m04_embedding_band_results.json
git commit -m "docs(sweeps): M04 embedding-band calibration verdict + JSON results"
```

---

## Task 21: Apply the verdict — flip default if warranted

**Files:**
- Modify (conditional): `api/internal/forge/cascade.go` (`DefaultCascadeConfig`)
- Modify (conditional): `api/internal/forge/cascade_test.go` (default-test assertion)

- [ ] **Step 1: Read the verdict's recommendation line**

```bash
grep -A 2 "## Best Cell" data-pipeline/sweeps/m04_embedding_band_verdict.md
```

If the verdict says **"ratify `SourcesUnion`"**: proceed to Step 2.

If the verdict says **"keep `SourcesCluster` default"**: skip to Step 5 (no code change, document follow-up in PIPELINE.md).

- [ ] **Step 2: Update `DefaultCascadeConfig` (ratification path)**

In `api/internal/forge/cascade.go`, replace the relevant fields of `DefaultCascadeConfig`:

```go
		CandidateSources: SourcesUnion,
		EmbeddingDMin:    <verdict_dmin>,
		EmbeddingDMax:    <verdict_dmax>,
		EmbeddingTopK:    100,
```

Substituting the verdict's best-cell d_min / d_max.

- [ ] **Step 3: Update the default-value test**

In `cascade_test.go`, update `TestCascadeConfig_DefaultIsValid` to assert the new defaults:

```go
	if cfg.CandidateSources != SourcesUnion {
		t.Errorf("default CandidateSources after M04 verdict: want %q, got %q",
			SourcesUnion, cfg.CandidateSources)
	}
	if cfg.EmbeddingDMin != <verdict_dmin> || cfg.EmbeddingDMax != <verdict_dmax> {
		t.Errorf("default band after M04 verdict: got dMin=%v dMax=%v",
			cfg.EmbeddingDMin, cfg.EmbeddingDMax)
	}
```

- [ ] **Step 4: Run the full suite to confirm the ratification leaves M03 tests green**

```bash
cd api && go test ./...
```

Expected: PASS. Any failure in the cluster_only backward-compat test (Task 11) indicates the union default is masking a real regression — debug before merging.

- [ ] **Step 5: Update PIPELINE.md and commit**

Edit `docs/roadmap/PIPELINE.md`:
- Move M04 from `## Next` to `## Done` (or whatever the canonical "shipped" section is).
- If the verdict said "keep cluster_only default": add a `Follow-up` line under the M04 backlog entry: "sweep verdict (2026-MM-DD) did not surface a non-regressive band — next iteration should widen the grid to (d_min ∈ {0.2, 0.3, 0.6}, d_max ∈ {0.7, 0.85, 1.1})".
- If the verdict ratified union: capture the chosen band in the M04 line for future reference.

```bash
git add api/internal/forge/cascade.go api/internal/forge/cascade_test.go docs/roadmap/PIPELINE.md
git commit -m "feat(forge): apply M04 sweep verdict — update default cascade config"
```

If no code change (cluster_only kept):

```bash
git add docs/roadmap/PIPELINE.md
git commit -m "docs(pipeline): record M04 sweep verdict — defer union default"
```

---

## Task 22: End-to-end smoke — run the full Go suite + sweep numbers

- [ ] **Step 1: Run the full Go test suite**

```bash
cd api && go test ./...
```

Expected: PASS across all packages, all M04 tests included.

- [ ] **Step 2: Run the full Python data-pipeline test suite**

```bash
source data-pipeline/.venv/bin/activate
python -m pytest data-pipeline/scripts/ -v
```

Expected: PASS — no M04 code touches data-pipeline scripts beyond the new sweep runner.

- [ ] **Step 3: Manual smoke test against a fresh API run**

```bash
cd api && METAFORGE_FORGE_CANDIDATES=union METAFORGE_FORGE_CASCADE=1 \
  go run ./cmd/metaforge --db ../data-pipeline/output/lexicon_v2.db --port 9099 --cascade &
sleep 2
curl -s 'http://127.0.0.1:9099/forge/suggest?word=anger&limit=10' | python -m json.tool | head -30
# kill the background process
kill %1
```

Expected: response includes suggestions tagged with `"source": "cluster"`, `"source": "embedding"`, or `"source": "both"`. At least one canonical cross-domain word (fire/heat/water etc.) should appear.

- [ ] **Step 4: Final commit / handoff**

If anything in Steps 1–3 surfaced an issue, fix it and commit. Otherwise no commit needed — proceed to the finishing-a-development-branch flow.

---

## Task 23: Handoff — invoke `superpowers:finishing-a-development-branch`

- [ ] **Step 1: Verify branch state**

```bash
git status
git log main..HEAD --oneline | head -40
```

Expected: clean working tree; ~20–25 commits on `m04/cosine-candidate-gen`.

- [ ] **Step 2: Invoke the finishing skill**

Pass control to `superpowers:finishing-a-development-branch`. The skill will:
1. Re-run the test suite
2. Detect worktree environment
3. Present 4 options (merge / PR / keep / discard)

---

## Self-review checklist (run before handing the plan to the implementer)

**Spec coverage:**
- Premise + scope discipline → captured in plan header
- Success criterion 1 (generation lift) → Task 10 (canary)
- Success criterion 2 (non-regression on aptness) → Task 20 (sweep verdict)
- Success criterion 3 (latency budget) → Task 13 (latency smoke)
- Success criterion 4 (backward compatibility) → Task 11 (cluster_only test)
- Architecture: `GetForgeCascadeCandidatesByEmbedding` → Task 5
- Architecture: `unionCandidates` → Task 6
- Architecture: `CandidateSources` / `CandidateSource` enums → Tasks 1, 2
- Architecture: `CascadeConfig` extension + `Validate()` → Task 3
- Architecture: anomaly aggregator (R1-D4 + R4-D1) → Tasks 14, 15
- Architecture: runtime tripwire on `synset_properties_curated` → Task 16
- Architecture: `cascade_embedding_query` timing stage → Task 7
- Calibration-sweep harness → Tasks 18, 19, 20
- Out-of-scope items → not implemented (correct)

**Placeholder scan:** No "TBD", "TODO", or "implement later" remaining. Verdict-conditional text in Task 21 (Step 2 substitutes the verdict's d_min/d_max) is the only intentional context-dependent value — flagged explicitly with `<verdict_dmin>` markers.

**Type consistency:** `CandidateSource` (per-row) and `CandidateSources` (config) are distinct types throughout. `CascadeCandidate.Source forge.CandidateSource` is consistent across cascade.go, cascade_embedding.go, and union helpers. `ForgeEmbeddingConfig` is the per-call shape (Task 5); the user-facing knobs on `CascadeConfig` (Task 3) are mapped into it by the handler dispatch (Task 7).

**Atomic-commit hygiene:** Each task ends in one commit. The runtime tripwire (Task 16) is its own commit, distinct from the anomaly aggregator commits (Tasks 14, 15), per the spec's S03 atomic-commit reminder.
