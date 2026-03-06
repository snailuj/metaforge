package db

import (
	"database/sql"
	"encoding/binary"
	"math"
	"path/filepath"
	"testing"

	_ "github.com/mattn/go-sqlite3"
)

func setupCuratedTestDB(t *testing.T) *sql.DB {
	t.Helper()
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatal(err)
	}

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
			salience_sum REAL NOT NULL DEFAULT 1.0,
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

		-- Source synset: grief (properties: heavy, isolating, waves)
		INSERT INTO synsets VALUES ('src1', 'n', 'intense sorrow');
		INSERT INTO lemmas VALUES ('grief', 'src1');
		INSERT INTO property_vocab_curated VALUES (1, 'v1', 'heavy', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (2, 'v2', 'isolating', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (3, 'v3', 'waves', 'n', 2);
		INSERT INTO property_vocab_curated VALUES (4, 'v4', 'light', 'a', 3);

		-- All singletons for this fixture
		INSERT INTO vocab_clusters VALUES (1, 1, 1, 1);
		INSERT INTO vocab_clusters VALUES (2, 2, 1, 1);
		INSERT INTO vocab_clusters VALUES (3, 3, 1, 1);
		INSERT INTO vocab_clusters VALUES (4, 4, 1, 1);

		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('src1', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('src1', 2, 2, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('src1', 3, 3, 'exact', NULL);

		-- Target synset: anchor (shares heavy + waves)
		INSERT INTO synsets VALUES ('tgt1', 'n', 'a device for holding');
		INSERT INTO lemmas VALUES ('anchor', 'tgt1');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt1', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt1', 3, 3, 'exact', NULL);

		-- Target synset: balloon (has light, antonym of heavy)
		INSERT INTO synsets VALUES ('tgt2', 'n', 'inflatable bag');
		INSERT INTO lemmas VALUES ('balloon', 'tgt2');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt2', 4, 4, 'exact', NULL);

		CREATE TABLE synset_concreteness (
			synset_id TEXT PRIMARY KEY, score REAL NOT NULL, source TEXT NOT NULL
		);

		-- Antonym: heavy <-> light (vocab-level)
		INSERT INTO property_antonyms VALUES (1, 4);
		INSERT INTO property_antonyms VALUES (4, 1);
		-- Antonym: heavy <-> light (cluster-level)
		INSERT INTO cluster_antonyms VALUES (1, 4);
		INSERT INTO cluster_antonyms VALUES (4, 1);
	`)
	if err != nil {
		t.Fatal(err)
	}

	return db
}

func TestGetForgeMatchesCurated_SharedProperties(t *testing.T) {
	db := setupCuratedTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCurated(db, "src1", 50)
	if err != nil {
		t.Fatal(err)
	}

	// anchor shares 2 properties (heavy, waves)
	var anchor *CuratedMatch
	for i := range matches {
		if matches[i].SynsetID == "tgt1" {
			anchor = &matches[i]
		}
	}
	if anchor == nil {
		t.Fatal("expected anchor in results")
	}
	if anchor.SalienceSum != 2.0 {
		t.Errorf("expected salience_sum 2.0, got %.2f", anchor.SalienceSum)
	}
}

func TestGetForgeMatchesCurated_SalienceSum(t *testing.T) {
	db := setupCuratedTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCurated(db, "src1", 50)
	if err != nil {
		t.Fatal(err)
	}

	var anchor *CuratedMatch
	for i := range matches {
		if matches[i].SynsetID == "tgt1" {
			anchor = &matches[i]
		}
	}
	if anchor == nil {
		t.Fatal("expected anchor in results")
	}
	// tgt1 has 2 properties each with salience_sum=1.0, so total = 2.0
	if anchor.SalienceSum != 2.0 {
		t.Errorf("expected salience_sum 2.0, got %.2f", anchor.SalienceSum)
	}
}

func TestGetForgeMatchesCurated_ContrastCount(t *testing.T) {
	db := setupCuratedTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCurated(db, "src1", 50)
	if err != nil {
		t.Fatal(err)
	}

	// balloon has "light" which is antonym of source's "heavy"
	var balloon *CuratedMatch
	for i := range matches {
		if matches[i].SynsetID == "tgt2" {
			balloon = &matches[i]
		}
	}
	if balloon == nil {
		t.Fatal("expected balloon in results")
	}
	if balloon.ContrastCount != 1 {
		t.Errorf("expected 1 contrast, got %d", balloon.ContrastCount)
	}
}

// --- GetForgeMatchesCuratedByLemma sense alignment tests ---

func setupSenseAlignmentTestDB(t *testing.T) *sql.DB {
	t.Helper()
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatal(err)
	}

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

		CREATE TABLE vocab_clusters (
			vocab_id         INTEGER PRIMARY KEY,
			cluster_id       INTEGER NOT NULL,
			is_representative INTEGER NOT NULL DEFAULT 0,
			is_singleton     INTEGER NOT NULL DEFAULT 0
		);
		CREATE INDEX idx_vc_cluster_sense ON vocab_clusters(cluster_id);

		CREATE TABLE synset_properties_curated (
			synset_id TEXT NOT NULL,
			vocab_id INTEGER NOT NULL,
			cluster_id INTEGER NOT NULL,
			snap_method TEXT NOT NULL,
			snap_score REAL,
			salience_sum REAL NOT NULL DEFAULT 1.0,
			PRIMARY KEY (synset_id, cluster_id)
		);
		CREATE INDEX idx_spc_sense_synset ON synset_properties_curated(synset_id);
		CREATE INDEX idx_spc_sense_vocab ON synset_properties_curated(vocab_id);
		CREATE INDEX idx_spc_sense_cluster ON synset_properties_curated(cluster_id);

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

		CREATE TABLE synset_concreteness (
			synset_id TEXT PRIMARY KEY, score REAL NOT NULL, source TEXT NOT NULL
		);

		-- Source lemma "bank" maps to TWO synsets (polysemous)
		INSERT INTO synsets VALUES ('bank-money', 'n', 'financial institution');
		INSERT INTO synsets VALUES ('bank-river', 'n', 'sloping land beside water');
		INSERT INTO lemmas VALUES ('bank', 'bank-money');
		INSERT INTO lemmas VALUES ('bank', 'bank-river');

		-- Properties for bank-money: valuable, secure (all singletons)
		INSERT INTO property_vocab_curated VALUES (1, 'v1', 'valuable', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (2, 'v2', 'secure', 'a', 1);
		INSERT INTO vocab_clusters VALUES (1, 1, 1, 1);
		INSERT INTO vocab_clusters VALUES (2, 2, 1, 1);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('bank-money', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('bank-money', 2, 2, 'exact', NULL);

		-- Properties for bank-river: wet, flowing (all singletons)
		INSERT INTO property_vocab_curated VALUES (3, 'v3', 'wet', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (4, 'v4', 'flowing', 'a', 1);
		INSERT INTO vocab_clusters VALUES (3, 3, 1, 1);
		INSERT INTO vocab_clusters VALUES (4, 4, 1, 1);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('bank-river', 3, 3, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('bank-river', 4, 4, 'exact', NULL);

		-- Target: vault (shares valuable + secure with bank-money)
		INSERT INTO synsets VALUES ('tgt-vault', 'n', 'secure storage room');
		INSERT INTO lemmas VALUES ('vault', 'tgt-vault');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-vault', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-vault', 2, 2, 'exact', NULL);

		-- Target: stream (shares wet + flowing with bank-river)
		INSERT INTO synsets VALUES ('tgt-stream', 'n', 'small river');
		INSERT INTO lemmas VALUES ('stream', 'tgt-stream');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-stream', 3, 3, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-stream', 4, 4, 'exact', NULL);
	`)
	if err != nil {
		t.Fatal(err)
	}

	return db
}

func TestGetForgeMatchesCuratedByLemma_SenseAlignment(t *testing.T) {
	db := setupSenseAlignmentTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCuratedByLemma(db, "bank", 50)
	if err != nil {
		t.Fatal(err)
	}

	if len(matches) < 2 {
		t.Fatalf("expected at least 2 matches, got %d", len(matches))
	}

	// Find vault and stream matches
	var vault, stream *CuratedMatch
	for i := range matches {
		switch matches[i].Word {
		case "vault":
			vault = &matches[i]
		case "stream":
			stream = &matches[i]
		}
	}

	if vault == nil {
		t.Fatal("expected vault in results")
	}
	if stream == nil {
		t.Fatal("expected stream in results")
	}

	// vault should align to bank-money sense
	if vault.SourceSynsetID != "bank-money" {
		t.Errorf("vault source synset: got %q, want %q", vault.SourceSynsetID, "bank-money")
	}
	if vault.SourceDefinition != "financial institution" {
		t.Errorf("vault source definition: got %q, want %q", vault.SourceDefinition, "financial institution")
	}
	if vault.SourcePOS != "n" {
		t.Errorf("vault source POS: got %q, want %q", vault.SourcePOS, "n")
	}

	// stream should align to bank-river sense
	if stream.SourceSynsetID != "bank-river" {
		t.Errorf("stream source synset: got %q, want %q", stream.SourceSynsetID, "bank-river")
	}
	if stream.SourceDefinition != "sloping land beside water" {
		t.Errorf("stream source definition: got %q, want %q", stream.SourceDefinition, "sloping land beside water")
	}
	if stream.SourcePOS != "n" {
		t.Errorf("stream source POS: got %q, want %q", stream.SourcePOS, "n")
	}

	// Each match should also carry target POS
	if vault.POS != "n" {
		t.Errorf("vault POS: got %q, want %q", vault.POS, "n")
	}
}

func TestGetForgeMatchesCuratedByLemma_NotFound(t *testing.T) {
	db := setupSenseAlignmentTestDB(t)
	defer db.Close()

	_, err := GetForgeMatchesCuratedByLemma(db, "nonexistent", 50)
	if err == nil {
		t.Fatal("expected error for nonexistent lemma")
	}
}

// --- GetSynsetIDForLemma curated preference tests ---

func setupSynsetIDTestDB(t *testing.T) *sql.DB {
	t.Helper()
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatal(err)
	}

	_, err = db.Exec(`
		CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT);
		CREATE TABLE lemmas (lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id));

		-- Legacy tables
		CREATE TABLE property_vocabulary (
			property_id INTEGER PRIMARY KEY,
			text TEXT NOT NULL,
			idf REAL
		);
		CREATE TABLE synset_properties (
			synset_id TEXT NOT NULL,
			property_id INTEGER NOT NULL,
			PRIMARY KEY (synset_id, property_id)
		);

		-- Curated tables
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

		-- Lemma "tyranny" maps to two synsets
		INSERT INTO synsets VALUES ('syn-legacy', 'n', 'cruel government');
		INSERT INTO synsets VALUES ('syn-curated', 'n', 'oppressive rule');
		INSERT INTO lemmas VALUES ('tyranny', 'syn-legacy');
		INSERT INTO lemmas VALUES ('tyranny', 'syn-curated');

		-- syn-legacy has 1 legacy property (but NO curated properties)
		INSERT INTO property_vocabulary VALUES (1, 'oppressive', 1.0);
		INSERT INTO synset_properties VALUES ('syn-legacy', 1);

		-- syn-curated has 3 curated properties (but NO legacy properties)
		INSERT INTO property_vocab_curated VALUES (10, 'v1', 'authoritarian', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (11, 'v2', 'controlling', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (12, 'v3', 'unjust', 'a', 1);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('syn-curated', 10, 10, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('syn-curated', 11, 11, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('syn-curated', 12, 12, 'exact', NULL);
	`)
	if err != nil {
		t.Fatal(err)
	}

	return db
}

func TestGetSynsetIDForLemma_PrefersCurated(t *testing.T) {
	db := setupSynsetIDTestDB(t)
	defer db.Close()

	synsetID, err := GetSynsetIDForLemma(db, "tyranny")
	if err != nil {
		t.Fatal(err)
	}

	// Should prefer the synset with most curated properties
	if synsetID != "syn-curated" {
		t.Errorf("expected syn-curated, got %s", synsetID)
	}
}

func TestGetSynsetIDForLemma_FallsBackToLegacy(t *testing.T) {
	// DB with NO curated tables — only legacy
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	_, err = db.Exec(`
		CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT);
		CREATE TABLE lemmas (lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id));
		CREATE TABLE property_vocabulary (
			property_id INTEGER PRIMARY KEY,
			text TEXT NOT NULL,
			idf REAL
		);
		CREATE TABLE synset_properties (
			synset_id TEXT NOT NULL,
			property_id INTEGER NOT NULL,
			PRIMARY KEY (synset_id, property_id)
		);

		INSERT INTO synsets VALUES ('syn1', 'n', 'a thing');
		INSERT INTO lemmas VALUES ('widget', 'syn1');
		INSERT INTO property_vocabulary VALUES (1, 'shiny', 1.0);
		INSERT INTO synset_properties VALUES ('syn1', 1);
	`)
	if err != nil {
		t.Fatal(err)
	}

	synsetID, err := GetSynsetIDForLemma(db, "widget")
	if err != nil {
		t.Fatal(err)
	}

	if synsetID != "syn1" {
		t.Errorf("expected syn1, got %s", synsetID)
	}
}

// --- LIMIT fix tests ---

func setupLimitTestDB(t *testing.T) *sql.DB {
	t.Helper()
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatal(err)
	}

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

		CREATE TABLE vocab_clusters (
			vocab_id         INTEGER PRIMARY KEY,
			cluster_id       INTEGER NOT NULL,
			is_representative INTEGER NOT NULL DEFAULT 0,
			is_singleton     INTEGER NOT NULL DEFAULT 0
		);
		CREATE INDEX idx_vc_cluster_limit ON vocab_clusters(cluster_id);

		CREATE TABLE synset_properties_curated (
			synset_id TEXT NOT NULL,
			vocab_id INTEGER NOT NULL,
			cluster_id INTEGER NOT NULL,
			snap_method TEXT NOT NULL,
			snap_score REAL,
			salience_sum REAL NOT NULL DEFAULT 1.0,
			PRIMARY KEY (synset_id, cluster_id)
		);
		CREATE INDEX idx_spc_synset2 ON synset_properties_curated(synset_id);
		CREATE INDEX idx_spc_vocab2 ON synset_properties_curated(vocab_id);
		CREATE INDEX idx_spc_cluster2 ON synset_properties_curated(cluster_id);

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

		CREATE TABLE synset_concreteness (
			synset_id TEXT PRIMARY KEY, score REAL NOT NULL, source TEXT NOT NULL
		);

		-- Curated vocab (all singletons)
		INSERT INTO property_vocab_curated VALUES (1, 'v1', 'hot', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (2, 'v2', 'bright', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (3, 'v3', 'loud', 'a', 1);
		INSERT INTO vocab_clusters VALUES (1, 1, 1, 1);
		INSERT INTO vocab_clusters VALUES (2, 2, 1, 1);
		INSERT INTO vocab_clusters VALUES (3, 3, 1, 1);

		-- Source: src (props: hot, bright, loud)
		INSERT INTO synsets VALUES ('src', 'n', 'source concept');
		INSERT INTO lemmas VALUES ('source', 'src');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('src', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('src', 2, 2, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('src', 3, 3, 'exact', NULL);

		-- tgt_a: shares hot+bright+loud (score 3), has 3 lemmas
		INSERT INTO synsets VALUES ('tgt_a', 'n', 'target A');
		INSERT INTO lemmas VALUES ('alpha1', 'tgt_a');
		INSERT INTO lemmas VALUES ('alpha2', 'tgt_a');
		INSERT INTO lemmas VALUES ('alpha3', 'tgt_a');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt_a', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt_a', 2, 2, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt_a', 3, 3, 'exact', NULL);

		-- tgt_b: shares hot+bright (score 2), 1 lemma
		INSERT INTO synsets VALUES ('tgt_b', 'n', 'target B');
		INSERT INTO lemmas VALUES ('beta', 'tgt_b');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt_b', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt_b', 2, 2, 'exact', NULL);

		-- tgt_c: shares hot (score 1), 1 lemma
		INSERT INTO synsets VALUES ('tgt_c', 'n', 'target C');
		INSERT INTO lemmas VALUES ('gamma', 'tgt_c');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt_c', 1, 1, 'exact', NULL);
	`)
	if err != nil {
		t.Fatal(err)
	}

	return db
}

func TestGetForgeMatchesCurated_LimitCountsUniqueSynsets(t *testing.T) {
	db := setupLimitTestDB(t)
	defer db.Close()

	// With limit 3, we should get all 3 unique target synsets.
	// Bug: old query counted lemma-expanded rows, so tgt_a (3 lemmas)
	// consumed the entire limit, leaving tgt_b and tgt_c excluded.
	matches, err := GetForgeMatchesCurated(db, "src", 3)
	if err != nil {
		t.Fatal(err)
	}

	if len(matches) != 3 {
		t.Errorf("expected 3 unique synsets, got %d", len(matches))
		for _, m := range matches {
			t.Logf("  %s (salience_sum=%.2f)", m.SynsetID, m.SalienceSum)
		}
	}
}

// --- Concreteness gate tests for GetForgeMatchesCurated ---

func setupConcretenessTestDB(t *testing.T) *sql.DB {
	t.Helper()
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatal(err)
	}

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

		CREATE TABLE vocab_clusters (
			vocab_id INTEGER PRIMARY KEY,
			cluster_id INTEGER NOT NULL,
			is_representative INTEGER NOT NULL DEFAULT 0,
			is_singleton INTEGER NOT NULL DEFAULT 0
		);
		CREATE INDEX idx_vc_cluster_conc ON vocab_clusters(cluster_id);

		CREATE TABLE synset_properties_curated (
			synset_id TEXT NOT NULL,
			vocab_id INTEGER NOT NULL,
			cluster_id INTEGER NOT NULL,
			snap_method TEXT NOT NULL,
			snap_score REAL,
			salience_sum REAL NOT NULL DEFAULT 1.0,
			PRIMARY KEY (synset_id, cluster_id)
		);
		CREATE INDEX idx_spc_conc_synset ON synset_properties_curated(synset_id);
		CREATE INDEX idx_spc_conc_cluster ON synset_properties_curated(cluster_id);

		CREATE TABLE cluster_antonyms (
			cluster_id_a INTEGER NOT NULL,
			cluster_id_b INTEGER NOT NULL,
			PRIMARY KEY (cluster_id_a, cluster_id_b)
		);

		CREATE TABLE synset_concreteness (
			synset_id TEXT PRIMARY KEY,
			score REAL NOT NULL,
			source TEXT NOT NULL
		);

		-- Vocab (all singletons)
		INSERT INTO property_vocab_curated VALUES (1, 'v1', 'hot', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (2, 'v2', 'destructive', 'a', 1);
		INSERT INTO vocab_clusters VALUES (1, 1, 1, 1);
		INSERT INTO vocab_clusters VALUES (2, 2, 1, 1);

		-- Source: anger (noun, concreteness 1.8)
		INSERT INTO synsets VALUES ('src-anger', 'n', 'strong displeasure');
		INSERT INTO lemmas VALUES ('anger', 'src-anger');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('src-anger', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('src-anger', 2, 2, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('src-anger', 1.8, 'brysbaert');

		-- Target: volcano (noun, concreteness 4.9) — SHOULD PASS gate
		INSERT INTO synsets VALUES ('tgt-volcano', 'n', 'a mountain that erupts');
		INSERT INTO lemmas VALUES ('volcano', 'tgt-volcano');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-volcano', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-volcano', 2, 2, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('tgt-volcano', 4.9, 'brysbaert');

		-- Target: fury (noun, concreteness 1.5) — SHOULD PASS (within 0.5 margin: 1.5+0.5=2.0 >= 1.8)
		INSERT INTO synsets VALUES ('tgt-fury', 'n', 'wild rage');
		INSERT INTO lemmas VALUES ('fury', 'tgt-fury');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-fury', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-fury', 2, 2, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('tgt-fury', 1.5, 'brysbaert');

		-- Target: serenity (noun, concreteness 1.0) — SHOULD FAIL (1.0+0.5=1.5 < 1.8, exceeds margin)
		INSERT INTO synsets VALUES ('tgt-serenity', 'n', 'calm peacefulness');
		INSERT INTO lemmas VALUES ('serenity', 'tgt-serenity');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-serenity', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-serenity', 2, 2, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('tgt-serenity', 1.0, 'brysbaert');

		-- Target: blaze (noun, concreteness 1.8) — SHOULD PASS (equal to source)
		INSERT INTO synsets VALUES ('tgt-blaze', 'n', 'a fierce fire');
		INSERT INTO lemmas VALUES ('blaze', 'tgt-blaze');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-blaze', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-blaze', 2, 2, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('tgt-blaze', 1.8, 'brysbaert');

		-- Target: storm (noun, no concreteness data) — SHOULD PASS (missing = pass through)
		INSERT INTO synsets VALUES ('tgt-storm', 'n', 'violent weather');
		INSERT INTO lemmas VALUES ('storm', 'tgt-storm');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-storm', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-storm', 2, 2, 'exact', NULL);
		-- No synset_concreteness row for storm

		-- Target: erupt (VERB, concreteness 3.0) — SHOULD PASS (POS bypass: candidate is verb)
		INSERT INTO synsets VALUES ('tgt-erupt', 'v', 'to burst forth violently');
		INSERT INTO lemmas VALUES ('erupt', 'tgt-erupt');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-erupt', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-erupt', 2, 2, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('tgt-erupt', 3.0, 'brysbaert');

		-- Target: furious (ADJECTIVE, concreteness 1.2) — SHOULD PASS (POS bypass: candidate is adj)
		INSERT INTO synsets VALUES ('tgt-furious', 'a', 'extremely angry');
		INSERT INTO lemmas VALUES ('furious', 'tgt-furious');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-furious', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score) VALUES ('tgt-furious', 2, 2, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('tgt-furious', 1.2, 'brysbaert');
	`)
	if err != nil {
		t.Fatal(err)
	}

	return db
}

func TestGetForgeMatchesCurated_ConcretenessGateKeepsConcreteVehicle(t *testing.T) {
	db := setupConcretenessTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCurated(db, "src-anger", 50)
	if err != nil {
		t.Fatal(err)
	}

	var found bool
	for _, m := range matches {
		if m.SynsetID == "tgt-volcano" {
			found = true
		}
	}
	if !found {
		t.Error("expected volcano (more concrete than anger) to pass gate")
	}
}

func TestGetForgeMatchesCurated_ConcretenessGateAllowsWithinMargin(t *testing.T) {
	db := setupConcretenessTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCurated(db, "src-anger", 50)
	if err != nil {
		t.Fatal(err)
	}

	var found bool
	for _, m := range matches {
		if m.SynsetID == "tgt-fury" {
			found = true
		}
	}
	if !found {
		t.Error("expected fury (1.5, within 0.5 margin of source 1.8) to pass gate")
	}
}

func TestGetForgeMatchesCurated_ConcretenessGateFiltersExceedsMargin(t *testing.T) {
	db := setupConcretenessTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCurated(db, "src-anger", 50)
	if err != nil {
		t.Fatal(err)
	}

	for _, m := range matches {
		if m.SynsetID == "tgt-serenity" {
			t.Error("expected serenity (1.0, exceeds 0.5 margin below source 1.8) to be filtered")
		}
	}
}

func TestGetForgeMatchesCurated_ConcretenessGateAllowsEqual(t *testing.T) {
	db := setupConcretenessTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCurated(db, "src-anger", 50)
	if err != nil {
		t.Fatal(err)
	}

	var found bool
	for _, m := range matches {
		if m.SynsetID == "tgt-blaze" {
			found = true
		}
	}
	if !found {
		t.Error("expected blaze (equal concreteness to anger) to pass gate")
	}
}

func TestGetForgeMatchesCurated_ConcretenessGateMissingScorePassesThrough(t *testing.T) {
	db := setupConcretenessTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCurated(db, "src-anger", 50)
	if err != nil {
		t.Fatal(err)
	}

	var found bool
	for _, m := range matches {
		if m.SynsetID == "tgt-storm" {
			found = true
		}
	}
	if !found {
		t.Error("expected storm (no concreteness data) to pass through gate")
	}
}

func TestGetForgeMatchesCurated_ConcretenessGatePOSBypassVerb(t *testing.T) {
	db := setupConcretenessTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCurated(db, "src-anger", 50)
	if err != nil {
		t.Fatal(err)
	}

	var found bool
	for _, m := range matches {
		if m.SynsetID == "tgt-erupt" {
			found = true
		}
	}
	if !found {
		t.Error("expected erupt (verb, POS bypass) to pass through gate")
	}
}

func TestGetForgeMatchesCurated_ConcretenessGatePOSBypassAdjective(t *testing.T) {
	db := setupConcretenessTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCurated(db, "src-anger", 50)
	if err != nil {
		t.Fatal(err)
	}

	var found bool
	for _, m := range matches {
		if m.SynsetID == "tgt-furious" {
			found = true
		}
	}
	if !found {
		t.Error("expected furious (adjective, POS bypass) to pass through gate")
	}
}

// --- Concreteness gate tests for GetForgeMatchesCuratedByLemma ---

func setupSenseAlignmentConcretenessTestDB(t *testing.T) *sql.DB {
	t.Helper()
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatal(err)
	}

	_, err = db.Exec(`
		CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT);
		CREATE TABLE lemmas (lemma TEXT, synset_id TEXT, PRIMARY KEY (lemma, synset_id));
		CREATE TABLE property_vocab_curated (
			vocab_id INTEGER PRIMARY KEY, synset_id TEXT NOT NULL,
			lemma TEXT NOT NULL, pos TEXT NOT NULL, polysemy INTEGER NOT NULL
		);
		CREATE TABLE vocab_clusters (
			vocab_id INTEGER PRIMARY KEY, cluster_id INTEGER NOT NULL,
			is_representative INTEGER NOT NULL DEFAULT 0, is_singleton INTEGER NOT NULL DEFAULT 0
		);
		CREATE INDEX idx_vc_cluster_sc ON vocab_clusters(cluster_id);
		CREATE TABLE synset_properties_curated (
			synset_id TEXT NOT NULL, vocab_id INTEGER NOT NULL, cluster_id INTEGER NOT NULL,
			snap_method TEXT NOT NULL, snap_score REAL, salience_sum REAL NOT NULL DEFAULT 1.0,
			PRIMARY KEY (synset_id, cluster_id)
		);
		CREATE INDEX idx_spc_sc_synset ON synset_properties_curated(synset_id);
		CREATE INDEX idx_spc_sc_cluster ON synset_properties_curated(cluster_id);
		CREATE TABLE cluster_antonyms (
			cluster_id_a INTEGER NOT NULL, cluster_id_b INTEGER NOT NULL,
			PRIMARY KEY (cluster_id_a, cluster_id_b)
		);
		CREATE TABLE synset_concreteness (
			synset_id TEXT PRIMARY KEY, score REAL NOT NULL, source TEXT NOT NULL
		);

		-- Source "light" has two senses
		-- light-photon (noun, concrete: 4.5) and light-weight (adjective, abstract: 2.0)
		INSERT INTO synsets VALUES ('light-photon', 'n', 'electromagnetic radiation');
		INSERT INTO synsets VALUES ('light-weight', 'a', 'not heavy');
		INSERT INTO lemmas VALUES ('light', 'light-photon');
		INSERT INTO lemmas VALUES ('light', 'light-weight');
		INSERT INTO synset_concreteness VALUES ('light-photon', 4.5, 'brysbaert');
		INSERT INTO synset_concreteness VALUES ('light-weight', 2.0, 'brysbaert');

		-- Properties (all singletons)
		INSERT INTO property_vocab_curated VALUES (1, 'v1', 'bright', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (2, 'v2', 'warm', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (3, 'v3', 'airy', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (4, 'v4', 'floating', 'a', 1);
		INSERT INTO vocab_clusters VALUES (1, 1, 1, 1);
		INSERT INTO vocab_clusters VALUES (2, 2, 1, 1);
		INSERT INTO vocab_clusters VALUES (3, 3, 1, 1);
		INSERT INTO vocab_clusters VALUES (4, 4, 1, 1);

		-- light-photon has: bright, warm
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('light-photon', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('light-photon', 2, 2, 'exact', NULL);

		-- light-weight has: airy, floating
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('light-weight', 3, 3, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('light-weight', 4, 4, 'exact', NULL);

		-- Target: sun (noun, concrete 4.8, shares bright+warm with light-photon)
		-- Source sense light-photon is noun with 4.5, sun is 4.8 → both nouns, 4.8+0.5>=4.5 → PASS
		INSERT INTO synsets VALUES ('tgt-sun', 'n', 'the star');
		INSERT INTO lemmas VALUES ('sun', 'tgt-sun');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('tgt-sun', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('tgt-sun', 2, 2, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('tgt-sun', 4.8, 'brysbaert');

		-- Target: feather (noun, concrete 4.9, shares airy+floating with light-weight)
		-- Source sense light-weight is adjective → POS bypass, gate doesn't fire → PASS
		INSERT INTO synsets VALUES ('tgt-feather', 'n', 'a plume');
		INSERT INTO lemmas VALUES ('feather', 'tgt-feather');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('tgt-feather', 3, 3, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('tgt-feather', 4, 4, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('tgt-feather', 4.9, 'brysbaert');

		-- Target: mood (noun, abstract 1.5, shares airy+floating with light-weight)
		-- Source sense light-weight is adjective → POS bypass, gate doesn't fire → PASS
		INSERT INTO synsets VALUES ('tgt-mood', 'n', 'emotional state');
		INSERT INTO lemmas VALUES ('mood', 'tgt-mood');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('tgt-mood', 3, 3, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('tgt-mood', 4, 4, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('tgt-mood', 1.5, 'brysbaert');

		-- Target: abstraction (noun, abstract 1.0, shares bright+warm with light-photon)
		-- Source sense light-photon is noun with 4.5, both nouns → gate fires
		-- 1.0+0.5=1.5 < 4.5 → FAIL
		INSERT INTO synsets VALUES ('tgt-abstraction', 'n', 'a general concept');
		INSERT INTO lemmas VALUES ('abstraction', 'tgt-abstraction');
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('tgt-abstraction', 1, 1, 'exact', NULL);
		INSERT INTO synset_properties_curated (synset_id, vocab_id, cluster_id, snap_method, snap_score)
			VALUES ('tgt-abstraction', 2, 2, 'exact', NULL);
		INSERT INTO synset_concreteness VALUES ('tgt-abstraction', 1.0, 'brysbaert');
	`)
	if err != nil {
		t.Fatal(err)
	}

	return db
}

func TestGetForgeMatchesCuratedByLemma_ConcretenessGatePassesConcrete(t *testing.T) {
	db := setupSenseAlignmentConcretenessTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCuratedByLemma(db, "light", 50)
	if err != nil {
		t.Fatal(err)
	}

	var foundSun, foundFeather bool
	for _, m := range matches {
		if m.Word == "sun" {
			foundSun = true
		}
		if m.Word == "feather" {
			foundFeather = true
		}
	}
	if !foundSun {
		t.Error("expected sun to pass concreteness gate (noun source, within margin)")
	}
	if !foundFeather {
		t.Error("expected feather to pass concreteness gate (adjective source, POS bypass)")
	}
}

func TestGetForgeMatchesCuratedByLemma_ConcretenessGateFiltersAbstract(t *testing.T) {
	db := setupSenseAlignmentConcretenessTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCuratedByLemma(db, "light", 50)
	if err != nil {
		t.Fatal(err)
	}

	for _, m := range matches {
		if m.Word == "abstraction" {
			t.Error("expected abstraction (1.0+0.5=1.5 < source noun 4.5) to be filtered")
		}
	}
}

func TestGetForgeMatchesCuratedByLemma_ConcretenessGateAdjectiveSourceBypass(t *testing.T) {
	db := setupSenseAlignmentConcretenessTestDB(t)
	defer db.Close()

	matches, err := GetForgeMatchesCuratedByLemma(db, "light", 50)
	if err != nil {
		t.Fatal(err)
	}

	// mood matches light-weight (adjective source) → POS bypass, should pass
	var found bool
	for _, m := range matches {
		if m.Word == "mood" {
			found = true
		}
	}
	if !found {
		t.Error("expected mood to pass gate (source sense light-weight is adjective, POS bypass)")
	}
}

// --- Lemma embedding tests ---

// --- GetConcretenessStats tests ---

func TestGetConcretenessStats(t *testing.T) {
	db := setupConcretenessTestDB(t)
	defer db.Close()

	scored, total, err := GetConcretenessStats(db)
	if err != nil {
		t.Fatal(err)
	}

	// setupConcretenessTestDB has 8 synsets total (1 source + 7 targets)
	// 7 have concreteness scores (all except tgt-storm)
	if scored != 7 {
		t.Errorf("expected 7 scored, got %d", scored)
	}
	if total != 8 {
		t.Errorf("expected 8 total synsets, got %d", total)
	}
}

func TestGetConcretenessStats_EmptyDB(t *testing.T) {
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")
	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	_, err = db.Exec(`
		CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT);
		CREATE TABLE synset_concreteness (synset_id TEXT PRIMARY KEY, score REAL NOT NULL, source TEXT NOT NULL);
	`)
	if err != nil {
		t.Fatal(err)
	}

	scored, total, err := GetConcretenessStats(db)
	if err != nil {
		t.Fatal(err)
	}
	if scored != 0 {
		t.Errorf("expected 0 scored, got %d", scored)
	}
	if total != 0 {
		t.Errorf("expected 0 total, got %d", total)
	}
}

// makeLemmaEmbeddingBlob creates a 300-dimensional embedding BLOB from the
// given float32 values. Remaining dimensions are zero-filled.
func makeLemmaEmbeddingBlob(vals ...float32) []byte {
	buf := make([]byte, 300*4) // 300 floats * 4 bytes
	for i := 0; i < len(vals) && i < 300; i++ {
		binary.LittleEndian.PutUint32(buf[i*4:], math.Float32bits(vals[i]))
	}
	return buf
}

func setupLemmaEmbeddingTestDB(t *testing.T) *sql.DB {
	t.Helper()
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatal(err)
	}

	_, err = db.Exec(`CREATE TABLE lemma_embeddings (lemma TEXT PRIMARY KEY, embedding BLOB NOT NULL)`)
	if err != nil {
		t.Fatal(err)
	}

	return db
}

func TestGetLemmaEmbedding(t *testing.T) {
	db := setupLemmaEmbeddingTestDB(t)
	defer db.Close()

	blob := makeLemmaEmbeddingBlob(0.1, 0.2, 0.3)
	_, err := db.Exec(`INSERT INTO lemma_embeddings VALUES (?, ?)`, "anger", blob)
	if err != nil {
		t.Fatal(err)
	}

	vec, err := GetLemmaEmbedding(db, "anger")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if vec == nil {
		t.Fatal("expected non-nil embedding")
	}
	if len(vec) != 300 {
		t.Fatalf("expected 300 floats, got %d", len(vec))
	}

	// Verify the first three values match what we inserted
	const epsilon = 1e-6
	if diff := vec[0] - 0.1; diff < -epsilon || diff > epsilon {
		t.Errorf("vec[0]: got %f, want 0.1", vec[0])
	}
	if diff := vec[1] - 0.2; diff < -epsilon || diff > epsilon {
		t.Errorf("vec[1]: got %f, want 0.2", vec[1])
	}
	if diff := vec[2] - 0.3; diff < -epsilon || diff > epsilon {
		t.Errorf("vec[2]: got %f, want 0.3", vec[2])
	}

	// Remaining dimensions should be zero
	if vec[3] != 0 {
		t.Errorf("vec[3]: got %f, want 0", vec[3])
	}
}

func TestGetLemmaEmbedding_Missing(t *testing.T) {
	db := setupLemmaEmbeddingTestDB(t)
	defer db.Close()

	vec, err := GetLemmaEmbedding(db, "nonexistent")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if vec != nil {
		t.Errorf("expected nil for missing lemma, got %v", vec)
	}
}

func TestGetLemmaEmbedding_NoTable(t *testing.T) {
	// DB without lemma_embeddings table
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	// Create a dummy table so the DB file is valid, but no lemma_embeddings
	_, err = db.Exec(`CREATE TABLE synsets (synset_id TEXT PRIMARY KEY)`)
	if err != nil {
		t.Fatal(err)
	}

	vec, err := GetLemmaEmbedding(db, "anger")
	if err != nil {
		t.Fatalf("expected graceful degradation, got error: %v", err)
	}
	if vec != nil {
		t.Errorf("expected nil for missing table, got %v", vec)
	}
}

func TestGetLemmaEmbeddingsBatch(t *testing.T) {
	db := setupLemmaEmbeddingTestDB(t)
	defer db.Close()

	// Insert embeddings for anger, fire, hope
	angerBlob := makeLemmaEmbeddingBlob(0.1, 0.2, 0.3)
	fireBlob := makeLemmaEmbeddingBlob(0.4, 0.5, 0.6)
	hopeBlob := makeLemmaEmbeddingBlob(0.7, 0.8, 0.9)

	_, err := db.Exec(`INSERT INTO lemma_embeddings VALUES (?, ?)`, "anger", angerBlob)
	if err != nil {
		t.Fatal(err)
	}
	_, err = db.Exec(`INSERT INTO lemma_embeddings VALUES (?, ?)`, "fire", fireBlob)
	if err != nil {
		t.Fatal(err)
	}
	_, err = db.Exec(`INSERT INTO lemma_embeddings VALUES (?, ?)`, "hope", hopeBlob)
	if err != nil {
		t.Fatal(err)
	}

	result, err := GetLemmaEmbeddingsBatch(db, []string{"anger", "fire", "missing"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// anger and fire should be present
	if _, ok := result["anger"]; !ok {
		t.Error("expected 'anger' in result map")
	}
	if _, ok := result["fire"]; !ok {
		t.Error("expected 'fire' in result map")
	}

	// missing should be absent
	if _, ok := result["missing"]; ok {
		t.Error("expected 'missing' to be absent from result map")
	}

	// Verify values
	const epsilon = 1e-6
	if diff := result["anger"][0] - 0.1; diff < -epsilon || diff > epsilon {
		t.Errorf("anger[0]: got %f, want 0.1", result["anger"][0])
	}
	if diff := result["fire"][0] - 0.4; diff < -epsilon || diff > epsilon {
		t.Errorf("fire[0]: got %f, want 0.4", result["fire"][0])
	}

	// Verify dimension count
	if len(result["anger"]) != 300 {
		t.Errorf("anger embedding: expected 300 floats, got %d", len(result["anger"]))
	}
}
