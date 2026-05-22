package handler

import (
	"database/sql"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/snailuj/metaforge/internal/forge"

	_ "github.com/mattn/go-sqlite3"
)

// setupLegacyEmbeddingErrorDB returns an in-memory DB where
// GetForgeMatchesCuratedByLemma succeeds (one candidate for source "bank")
// but the lemma_embeddings table has a wrong column shape, so
// GetLemmaEmbedding raises a real DB error ("no such column: embedding").
// This is the surface D8 hardens — pre-fix the legacy handler swallowed
// the error and returned 200 with silently-degraded composite scores.
func setupLegacyEmbeddingErrorDB(t *testing.T) *sql.DB {
	t.Helper()
	database, err := sql.Open("sqlite3", ":memory:")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := database.Exec(`
		CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT);
		CREATE TABLE lemmas (lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id));
		CREATE TABLE property_vocab_curated (
			vocab_id INTEGER PRIMARY KEY,
			synset_id TEXT NOT NULL,
			lemma TEXT NOT NULL,
			pos TEXT NOT NULL,
			polysemy INTEGER NOT NULL
		);
		CREATE TABLE vocab_clusters (
			vocab_id INTEGER PRIMARY KEY,
			cluster_id INTEGER NOT NULL,
			is_representative INTEGER NOT NULL DEFAULT 0,
			is_singleton INTEGER NOT NULL DEFAULT 0
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
		CREATE TABLE frequencies (lemma TEXT PRIMARY KEY, frequency REAL);
		-- Wrong column shape: real schema has 'embedding' BLOB. This
		-- triggers a "no such column: embedding" error on SELECT.
		CREATE TABLE lemma_embeddings (lemma TEXT PRIMARY KEY, vector_garbled BLOB);

		INSERT INTO synsets VALUES ('bank-money', 'n', 'financial institution');
		INSERT INTO synsets VALUES ('tgt-vault', 'n', 'secure storage room');
		INSERT INTO lemmas VALUES ('bank', 'bank-money');
		INSERT INTO lemmas VALUES ('vault', 'tgt-vault');
		INSERT INTO property_vocab_curated VALUES (1, 'v1', 'valuable', 'a', 1);
		INSERT INTO vocab_clusters VALUES (1, 1, 1, 1);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('bank-money', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('tgt-vault', 1, 1, 'exact', NULL);
	`); err != nil {
		t.Fatal(err)
	}
	return database
}

func TestHandleSuggestLegacy_RealEmbeddingErrorReturns500(t *testing.T) {
	// D8 regression test: the legacy /forge/suggest path must escalate a
	// real lemma-embedding DB error to a 500 rather than the pre-fix
	// behaviour of slog.Warn + continue with silently-degraded
	// composite scores.
	database := setupLegacyEmbeddingErrorDB(t)
	defer database.Close()

	h := &Handler{
		database:    database,
		useCascade:  false,
		cascadeConf: forge.DefaultCascadeConfig(),
	}

	req := httptest.NewRequest("GET", "/forge/suggest?word=bank&limit=5", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500 on real embedding DB error, got %d: %s", w.Code, w.Body.String())
	}
}
