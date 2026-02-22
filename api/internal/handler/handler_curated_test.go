package handler

import (
	"database/sql"
	"encoding/binary"
	"encoding/json"
	"math"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"

	_ "github.com/mattn/go-sqlite3"

	"github.com/snailuj/metaforge/internal/forge"
)

// makeLemmaBlob creates a 300d embedding BLOB from given float32 values (rest zero-filled).
func makeLemmaBlob(vals ...float32) []byte {
	buf := make([]byte, 300*4)
	for i := 0; i < len(vals) && i < 300; i++ {
		binary.LittleEndian.PutUint32(buf[i*4:], math.Float32bits(vals[i]))
	}
	return buf
}

// setupCrossDomainTestDB creates a test DB with:
//   - Source lemma "anger" with properties: intense, consuming, destructive
//   - Candidate "fury" sharing all 3 props, with embedding close to anger
//   - Candidate "fire" sharing 2 props (consuming, destructive), with distant embedding
func setupCrossDomainTestDB(t *testing.T) *sql.DB {
	t.Helper()
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	database, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatal(err)
	}

	_, err = database.Exec(`
		CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT);
		CREATE TABLE lemmas (lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id));
		CREATE TABLE frequencies (lemma TEXT PRIMARY KEY, familiarity REAL);

		CREATE TABLE property_vocab_curated (
			vocab_id INTEGER PRIMARY KEY,
			synset_id TEXT NOT NULL,
			lemma TEXT NOT NULL,
			pos TEXT NOT NULL,
			polysemy INTEGER NOT NULL
		);

		CREATE TABLE vocab_clusters (
			vocab_id         INTEGER PRIMARY KEY,
			cluster_id       INTEGER NOT NULL,
			is_representative INTEGER NOT NULL DEFAULT 0,
			is_singleton     INTEGER NOT NULL DEFAULT 0
		);
		CREATE INDEX idx_vc_cluster ON vocab_clusters(cluster_id);

		CREATE TABLE synset_properties_curated (
			synset_id TEXT NOT NULL,
			vocab_id INTEGER NOT NULL,
			cluster_id INTEGER NOT NULL,
			snap_method TEXT NOT NULL,
			snap_score REAL,
			PRIMARY KEY (synset_id, cluster_id)
		);
		CREATE INDEX idx_spc_synset ON synset_properties_curated(synset_id);
		CREATE INDEX idx_spc_vocab ON synset_properties_curated(vocab_id);
		CREATE INDEX idx_spc_cluster ON synset_properties_curated(cluster_id);

		CREATE TABLE property_antonyms (
			vocab_id_a INTEGER NOT NULL,
			vocab_id_b INTEGER NOT NULL,
			PRIMARY KEY (vocab_id_a, vocab_id_b)
		);

		CREATE TABLE cluster_antonyms (
			cluster_id_a INTEGER NOT NULL,
			cluster_id_b INTEGER NOT NULL,
			PRIMARY KEY (cluster_id_a, cluster_id_b)
		);

		CREATE TABLE lemma_embeddings (
			lemma TEXT PRIMARY KEY,
			embedding BLOB NOT NULL
		);

		-- Properties (all singletons)
		INSERT INTO property_vocab_curated VALUES (1, 'v1', 'intense', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (2, 'v2', 'consuming', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (3, 'v3', 'destructive', 'a', 1);
		INSERT INTO vocab_clusters VALUES (1, 1, 1, 1);
		INSERT INTO vocab_clusters VALUES (2, 2, 1, 1);
		INSERT INTO vocab_clusters VALUES (3, 3, 1, 1);

		-- Source: anger (3 props: intense, consuming, destructive)
		INSERT INTO synsets VALUES ('syn-anger', 'n', 'strong displeasure');
		INSERT INTO lemmas VALUES ('anger', 'syn-anger');
		INSERT INTO synset_properties_curated VALUES ('syn-anger', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('syn-anger', 2, 2, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('syn-anger', 3, 3, 'exact', NULL);

		-- Candidate: fury (3 props — same as anger, synonym)
		INSERT INTO synsets VALUES ('syn-fury', 'n', 'wild anger');
		INSERT INTO lemmas VALUES ('fury', 'syn-fury');
		INSERT INTO synset_properties_curated VALUES ('syn-fury', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('syn-fury', 2, 2, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('syn-fury', 3, 3, 'exact', NULL);

		-- Candidate: fire (2 props: consuming, destructive — cross-domain)
		INSERT INTO synsets VALUES ('syn-fire', 'n', 'combustion');
		INSERT INTO lemmas VALUES ('fire', 'syn-fire');
		INSERT INTO synset_properties_curated VALUES ('syn-fire', 2, 2, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('syn-fire', 3, 3, 'exact', NULL);
	`)
	if err != nil {
		t.Fatal(err)
	}

	// Lemma embeddings: anger and fury are close; fire is distant
	// anger = (1, 0, 0, ...) fury = (0.95, 0.05, 0, ...) → distance ≈ 0.002
	// fire  = (0, 1, 0, ...)                              → distance ≈ 1.0
	angerEmb := makeLemmaBlob(1.0, 0.0, 0.0)
	furyEmb := makeLemmaBlob(0.95, 0.05, 0.0)
	fireEmb := makeLemmaBlob(0.0, 1.0, 0.0)

	_, err = database.Exec(`INSERT INTO lemma_embeddings VALUES ('anger', ?)`, angerEmb)
	if err != nil {
		t.Fatal(err)
	}
	_, err = database.Exec(`INSERT INTO lemma_embeddings VALUES ('fury', ?)`, furyEmb)
	if err != nil {
		t.Fatal(err)
	}
	_, err = database.Exec(`INSERT INTO lemma_embeddings VALUES ('fire', ?)`, fireEmb)
	if err != nil {
		t.Fatal(err)
	}

	return database
}

func TestHandleSuggest_CrossDomainBoost(t *testing.T) {
	database := setupCrossDomainTestDB(t)
	defer database.Close()

	h := &Handler{database: database}

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger", nil)
	w := httptest.NewRecorder()

	h.HandleSuggest(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp SuggestResponse
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("decode failed: %v", err)
	}

	if len(resp.Suggestions) < 2 {
		t.Fatalf("expected at least 2 suggestions, got %d", len(resp.Suggestions))
	}

	// Find fire and fury in results
	var fireSuggestion, furySuggestion *forge.Match
	for i := range resp.Suggestions {
		switch resp.Suggestions[i].Word {
		case "fire":
			fireSuggestion = &resp.Suggestions[i]
		case "fury":
			furySuggestion = &resp.Suggestions[i]
		}
	}

	if fireSuggestion == nil {
		t.Fatal("expected 'fire' in suggestions")
	}
	if furySuggestion == nil {
		t.Fatal("expected 'fury' in suggestions")
	}

	// Fire should have higher domain_distance than fury
	if fireSuggestion.DomainDistance <= furySuggestion.DomainDistance {
		t.Errorf("fire domain_distance (%.4f) should be > fury domain_distance (%.4f)",
			fireSuggestion.DomainDistance, furySuggestion.DomainDistance)
	}

	// Fire has 2 props but high distance; fury has 3 props but low distance
	// composite = overlap × (1 + Alpha × distance)
	// fire: 2 × (1 + 1.0 × ~1.0) ≈ 4.0
	// fury: 3 × (1 + 1.0 × ~0.002) ≈ 3.006
	// Fire should have higher composite_score
	if fireSuggestion.CompositeScore <= furySuggestion.CompositeScore {
		t.Errorf("fire composite_score (%.4f) should be > fury composite_score (%.4f)",
			fireSuggestion.CompositeScore, furySuggestion.CompositeScore)
	}
}

func TestHandleSuggest_NoEmbeddingsGraceful(t *testing.T) {
	// DB without lemma_embeddings table — should still work, composite = overlap
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	database, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatal(err)
	}
	defer database.Close()

	_, err = database.Exec(`
		CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT);
		CREATE TABLE lemmas (lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id));
		CREATE TABLE frequencies (lemma TEXT PRIMARY KEY, familiarity REAL);

		CREATE TABLE property_vocab_curated (
			vocab_id INTEGER PRIMARY KEY,
			synset_id TEXT NOT NULL,
			lemma TEXT NOT NULL,
			pos TEXT NOT NULL,
			polysemy INTEGER NOT NULL
		);

		CREATE TABLE vocab_clusters (
			vocab_id         INTEGER PRIMARY KEY,
			cluster_id       INTEGER NOT NULL,
			is_representative INTEGER NOT NULL DEFAULT 0,
			is_singleton     INTEGER NOT NULL DEFAULT 0
		);

		CREATE TABLE synset_properties_curated (
			synset_id TEXT NOT NULL,
			vocab_id INTEGER NOT NULL,
			cluster_id INTEGER NOT NULL,
			snap_method TEXT NOT NULL,
			snap_score REAL,
			PRIMARY KEY (synset_id, cluster_id)
		);
		CREATE INDEX idx_spc_synset2 ON synset_properties_curated(synset_id);
		CREATE INDEX idx_spc_vocab2 ON synset_properties_curated(vocab_id);

		CREATE TABLE property_antonyms (
			vocab_id_a INTEGER NOT NULL,
			vocab_id_b INTEGER NOT NULL,
			PRIMARY KEY (vocab_id_a, vocab_id_b)
		);

		CREATE TABLE cluster_antonyms (
			cluster_id_a INTEGER NOT NULL,
			cluster_id_b INTEGER NOT NULL,
			PRIMARY KEY (cluster_id_a, cluster_id_b)
		);

		INSERT INTO property_vocab_curated VALUES (1, 'v1', 'hot', 'a', 1);
		INSERT INTO vocab_clusters VALUES (1, 1, 1, 1);
		INSERT INTO synsets VALUES ('src', 'n', 'source');
		INSERT INTO lemmas VALUES ('sun', 'src');
		INSERT INTO synset_properties_curated VALUES ('src', 1, 1, 'exact', NULL);

		INSERT INTO synsets VALUES ('tgt', 'n', 'target');
		INSERT INTO lemmas VALUES ('star', 'tgt');
		INSERT INTO synset_properties_curated VALUES ('tgt', 1, 1, 'exact', NULL);
	`)
	if err != nil {
		t.Fatal(err)
	}

	h := &Handler{database: database}

	req := httptest.NewRequest("GET", "/forge/suggest?word=sun", nil)
	w := httptest.NewRecorder()

	h.HandleSuggest(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp SuggestResponse
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("decode failed: %v", err)
	}

	if len(resp.Suggestions) == 0 {
		t.Fatal("expected at least 1 suggestion")
	}

	// Without embeddings, domain_distance should be 0, composite = overlap
	s := resp.Suggestions[0]
	if s.DomainDistance != 0.0 {
		t.Errorf("expected domain_distance 0 without embeddings, got %.4f", s.DomainDistance)
	}
	if s.CompositeScore != float64(s.OverlapCount) {
		t.Errorf("expected composite_score = overlap_count (%.0f), got %.4f",
			float64(s.OverlapCount), s.CompositeScore)
	}
}
