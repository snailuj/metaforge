package db

import (
	"errors"
	"strings"
	"testing"

	_ "github.com/mattn/go-sqlite3"
	"github.com/snailuj/metaforge/internal/forge"
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

func TestGetForgeCascadeCandidatesByLemma_AllPassConcretenessGate(t *testing.T) {
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

func TestGetForgeCascadeCandidatesByLemma_HighlyConcreteLemmaDoesNotError(t *testing.T) {
	database, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	// 'cat' is highly concrete (~4.9 on Brysbaert). With threshold=1.0 and
	// max concreteness ~5.0, very few vehicles can satisfy
	// (vehicle - topic) >= 1.0. We don't assert zero candidates (the test
	// DB might still surface a handful) — we just assert the function
	// returns without error and doesn't fall into the ErrLemmaNotFound
	// branch (cat IS enriched). Gate correctness is verified by the
	// anger cross-check test against the cache.
	candidates, err := GetForgeCascadeCandidatesByLemma(database, "cat", 1.0, 20)
	if err != nil {
		t.Fatalf("GetForgeCascadeCandidatesByLemma: %v", err)
	}
	t.Logf("cat returned %d gate-passed candidates", len(candidates))
}

func TestGetForgeCascadeCandidatesByLemma_LimitReturnsDistinctCandidates(t *testing.T) {
	// PR1.1 regression test: a broad-coverage lemma like 'anger' must
	// produce close to `limit` distinct synsets, not be truncated to
	// ~half by per-target lemma duplicates.
	database, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	candidates, err := GetForgeCascadeCandidatesByLemma(database, "anger", 1.0, 50)
	if err != nil {
		t.Fatalf("GetForgeCascadeCandidatesByLemma: %v", err)
	}
	t.Logf("anger limit=50 returned %d distinct candidates", len(candidates))
	if len(candidates) < 40 {
		t.Errorf("expected at least 40 distinct candidates for 'anger' limit=50, got %d "+
			"(pre-fix baseline was 23 due to lemma row-amplification before LIMIT)", len(candidates))
	}
	seen := make(map[string]bool)
	for _, c := range candidates {
		if seen[c.SynsetID] {
			t.Errorf("duplicate synset in candidates: %s", c.SynsetID)
		}
		seen[c.SynsetID] = true
	}
}

func TestGetForgeCascadeCandidatesByLemma_UnknownLemmaReturnsErrLemmaNotFound(t *testing.T) {
	database, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	_, err = GetForgeCascadeCandidatesByLemma(database, "zzznotarealword", 1.0, 20)
	if !errors.Is(err, ErrLemmaNotFound) {
		t.Errorf("expected ErrLemmaNotFound for unknown lemma, got %v", err)
	}
}

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

func TestNewCascadeCandidate_PanicsOnInvalidSource(t *testing.T) {
	defer func() {
		r := recover()
		if r == nil {
			t.Fatal("expected panic for invalid Source, got none")
		}
		msg, _ := r.(string)
		if !strings.Contains(msg, "invalid Source") {
			t.Errorf("panic message missing expected phrase: %v", r)
		}
	}()
	_ = NewCascadeCandidate(
		"s1", "fire", "n", "definition",
		1.0, 0, nil,
		"s0", "src definition", "n",
		forge.CandidateSource(""), // invalid
	)
}

func TestNewCascadeCandidate_AcceptsValidSource(t *testing.T) {
	c := NewCascadeCandidate(
		"s1", "fire", "n", "definition",
		1.0, 0, nil,
		"s0", "src definition", "n",
		forge.SourceCluster,
	)
	if c.Source != forge.SourceCluster {
		t.Errorf("Source: want SourceCluster, got %q", c.Source)
	}
	if c.SynsetID != "s1" {
		t.Errorf("SynsetID: want s1, got %q", c.SynsetID)
	}
}
