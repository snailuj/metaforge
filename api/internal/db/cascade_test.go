package db

import (
	"database/sql"
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

func TestGetForgeCascadeCandidatesByLemma_AllHaveConcreteness(t *testing.T) {
	// Task 8: the SQL no longer filters by gate threshold. The DB layer now
	// only enforces the missing-concreteness contract (INNER JOIN). Every
	// returned candidate must have a concreteness score on both sides; the
	// gate threshold decision (hard-drop vs soft sigmoid) is made in Go.
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

	// Every returned candidate must have concreteness present on both sides
	// (the INNER JOIN guarantee). The gate delta itself may be anything —
	// the Go scorer decides what to do with sub-threshold rows.
	for _, c := range candidates {
		if _, hasTopic := cache.Concreteness[c.SourceSynsetID]; !hasTopic {
			t.Errorf("candidate %s/%s: topic synset missing concreteness in cache — INNER JOIN contract violated",
				c.SourceSynsetID, c.SynsetID)
		}
		if _, hasVeh := cache.Concreteness[c.SynsetID]; !hasVeh {
			t.Errorf("candidate %s/%s: vehicle synset missing concreteness in cache — INNER JOIN contract violated",
				c.SourceSynsetID, c.SynsetID)
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

func TestCandidateFetch_SurfacesSubThresholdRows(t *testing.T) {
	// Pre-Task-8: candidates with vehicle_c - topic_c < ConcretenessThreshold
	// were filtered out at the SQL layer. After Task 8, they must surface
	// so the Go scorer can decide what to do (gate-drop in hard mode,
	// score with sigmoid penalty in soft mode).
	//
	// Fixture: topic synset concreteness 4.0, two vehicle candidates —
	// one concreteness 5.0 (above-threshold: 5.0-4.0=1.0 >= 1.0) and one
	// concreteness 3.5 (sub-threshold: 3.5-4.0=-0.5 < 1.0). Both must be
	// returned from the DB function so the Go scorer handles gate logic.
	db, err := sql.Open("sqlite3", ":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	_, err = db.Exec(`
		CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT);
		CREATE TABLE lemmas (lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id));
		CREATE TABLE property_vocab_curated (
			vocab_id INTEGER PRIMARY KEY,
			synset_id TEXT NOT NULL,
			lemma TEXT NOT NULL,
			pos TEXT NOT NULL,
			polysemy INTEGER NOT NULL
		);
		CREATE TABLE synset_properties_curated (
			synset_id TEXT NOT NULL,
			vocab_id INTEGER NOT NULL,
			cluster_id INTEGER NOT NULL,
			snap_method TEXT NOT NULL,
			snap_score REAL,
			salience_sum REAL NOT NULL DEFAULT 1.0,
			PRIMARY KEY (synset_id, cluster_id)
		);
		CREATE TABLE cluster_antonyms (
			cluster_id_a INTEGER NOT NULL,
			cluster_id_b INTEGER NOT NULL,
			PRIMARY KEY (cluster_id_a, cluster_id_b)
		);
		CREATE TABLE synset_concreteness (
			synset_id TEXT PRIMARY KEY,
			score REAL,
			source TEXT
		);

		-- Topic: "dread" (abstract, concreteness 4.0)
		INSERT INTO synsets VALUES ('src-dread', 'n', 'a feeling of dread');
		INSERT INTO lemmas VALUES ('dread', 'src-dread');
		INSERT INTO property_vocab_curated VALUES (1, 'v1', 'heavy', 'a', 1);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES
			('src-dread', 1, 1, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('src-dread', 4.0, 'test');

		-- Vehicle A: concreteness 5.0 → delta = +1.0 (at threshold, above gate)
		INSERT INTO synsets VALUES ('tgt-above', 'n', 'something very concrete');
		INSERT INTO lemmas VALUES ('rock', 'tgt-above');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES
			('tgt-above', 1, 1, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('tgt-above', 5.0, 'test');

		-- Vehicle B: concreteness 3.5 → delta = -0.5 (below threshold)
		INSERT INTO synsets VALUES ('tgt-below', 'n', 'something less concrete');
		INSERT INTO lemmas VALUES ('mist', 'tgt-below');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES
			('tgt-below', 1, 1, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('tgt-below', 3.5, 'test');
	`)
	if err != nil {
		t.Fatalf("fixture setup: %v", err)
	}

	candidates, err := GetForgeCascadeCandidatesByLemma(db, "dread", 1.0, 50)
	if err != nil {
		t.Fatalf("GetForgeCascadeCandidatesByLemma: %v", err)
	}

	// Both the above-threshold AND the sub-threshold vehicle must surface.
	// The Go scorer (not SQL) is responsible for gate decisions.
	synsetIDs := make(map[string]bool, len(candidates))
	for _, c := range candidates {
		synsetIDs[c.SynsetID] = true
	}
	if !synsetIDs["tgt-above"] {
		t.Error("above-threshold candidate tgt-above missing from results")
	}
	if !synsetIDs["tgt-below"] {
		t.Error("sub-threshold candidate tgt-below missing from results — SQL CTE is still filtering gate; Task 8 fix not applied")
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
	_ = NewCascadeCandidate(NewCascadeCandidateOpts{
		SynsetID:         "s1",
		Word:             "fire",
		POS:              "n",
		Definition:       "definition",
		SalienceSum:      1.0,
		ContrastCount:    0,
		SharedProps:      nil,
		SourceSynsetID:   "s0",
		SourceDefinition: "src definition",
		SourcePOS:        "n",
		Source:           forge.CandidateSource(""), // invalid
	})
}

func TestNewCascadeCandidate_AcceptsValidSource(t *testing.T) {
	c := NewCascadeCandidate(NewCascadeCandidateOpts{
		SynsetID:         "s1",
		Word:             "fire",
		POS:              "n",
		Definition:       "definition",
		SalienceSum:      1.0,
		ContrastCount:    0,
		SharedProps:      nil,
		SourceSynsetID:   "s0",
		SourceDefinition: "src definition",
		SourcePOS:        "n",
		Source:           forge.SourceCluster,
	})
	if c.Source != forge.SourceCluster {
		t.Errorf("Source: want SourceCluster, got %q", c.Source)
	}
	if c.SynsetID != "s1" {
		t.Errorf("SynsetID: want s1, got %q", c.SynsetID)
	}
}
