package db

import (
	"database/sql"
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

		CREATE TABLE synset_properties_curated (
			synset_id TEXT NOT NULL,
			vocab_id INTEGER NOT NULL,
			snap_method TEXT NOT NULL,
			snap_score REAL,
			PRIMARY KEY (synset_id, vocab_id)
		);
		CREATE INDEX idx_spc_synset ON synset_properties_curated(synset_id);
		CREATE INDEX idx_spc_vocab ON synset_properties_curated(vocab_id);

		CREATE TABLE property_antonyms (
			vocab_id_a INTEGER NOT NULL,
			vocab_id_b INTEGER NOT NULL,
			PRIMARY KEY (vocab_id_a, vocab_id_b)
		);

		-- Source synset: grief (properties: heavy, isolating, waves)
		INSERT INTO synsets VALUES ('src1', 'n', 'intense sorrow');
		INSERT INTO lemmas VALUES ('grief', 'src1');
		INSERT INTO property_vocab_curated VALUES (1, 'v1', 'heavy', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (2, 'v2', 'isolating', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (3, 'v3', 'waves', 'n', 2);
		INSERT INTO property_vocab_curated VALUES (4, 'v4', 'light', 'a', 3);

		INSERT INTO synset_properties_curated VALUES ('src1', 1, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('src1', 2, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('src1', 3, 'exact', NULL);

		-- Target synset: anchor (shares heavy + waves)
		INSERT INTO synsets VALUES ('tgt1', 'n', 'a device for holding');
		INSERT INTO lemmas VALUES ('anchor', 'tgt1');
		INSERT INTO synset_properties_curated VALUES ('tgt1', 1, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('tgt1', 3, 'exact', NULL);

		-- Target synset: balloon (has light, antonym of heavy)
		INSERT INTO synsets VALUES ('tgt2', 'n', 'inflatable bag');
		INSERT INTO lemmas VALUES ('balloon', 'tgt2');
		INSERT INTO synset_properties_curated VALUES ('tgt2', 4, 'exact', NULL);

		-- Antonym: heavy <-> light
		INSERT INTO property_antonyms VALUES (1, 4);
		INSERT INTO property_antonyms VALUES (4, 1);
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
	if anchor.SharedCount != 2 {
		t.Errorf("expected 2 shared, got %d", anchor.SharedCount)
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

		CREATE TABLE synset_properties_curated (
			synset_id TEXT NOT NULL,
			vocab_id INTEGER NOT NULL,
			snap_method TEXT NOT NULL,
			snap_score REAL,
			PRIMARY KEY (synset_id, vocab_id)
		);
		CREATE INDEX idx_spc_sense_synset ON synset_properties_curated(synset_id);
		CREATE INDEX idx_spc_sense_vocab ON synset_properties_curated(vocab_id);

		CREATE TABLE property_antonyms (
			vocab_id_a INTEGER NOT NULL,
			vocab_id_b INTEGER NOT NULL,
			PRIMARY KEY (vocab_id_a, vocab_id_b)
		);

		-- Source lemma "bank" maps to TWO synsets (polysemous)
		INSERT INTO synsets VALUES ('bank-money', 'n', 'financial institution');
		INSERT INTO synsets VALUES ('bank-river', 'n', 'sloping land beside water');
		INSERT INTO lemmas VALUES ('bank', 'bank-money');
		INSERT INTO lemmas VALUES ('bank', 'bank-river');

		-- Properties for bank-money: valuable, secure
		INSERT INTO property_vocab_curated VALUES (1, 'v1', 'valuable', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (2, 'v2', 'secure', 'a', 1);
		INSERT INTO synset_properties_curated VALUES ('bank-money', 1, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('bank-money', 2, 'exact', NULL);

		-- Properties for bank-river: wet, flowing
		INSERT INTO property_vocab_curated VALUES (3, 'v3', 'wet', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (4, 'v4', 'flowing', 'a', 1);
		INSERT INTO synset_properties_curated VALUES ('bank-river', 3, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('bank-river', 4, 'exact', NULL);

		-- Target: vault (shares valuable + secure with bank-money)
		INSERT INTO synsets VALUES ('tgt-vault', 'n', 'secure storage room');
		INSERT INTO lemmas VALUES ('vault', 'tgt-vault');
		INSERT INTO synset_properties_curated VALUES ('tgt-vault', 1, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('tgt-vault', 2, 'exact', NULL);

		-- Target: stream (shares wet + flowing with bank-river)
		INSERT INTO synsets VALUES ('tgt-stream', 'n', 'small river');
		INSERT INTO lemmas VALUES ('stream', 'tgt-stream');
		INSERT INTO synset_properties_curated VALUES ('tgt-stream', 3, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('tgt-stream', 4, 'exact', NULL);
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
			snap_method TEXT NOT NULL,
			snap_score REAL,
			PRIMARY KEY (synset_id, vocab_id)
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
		INSERT INTO synset_properties_curated VALUES ('syn-curated', 10, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('syn-curated', 11, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('syn-curated', 12, 'exact', NULL);
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

		CREATE TABLE synset_properties_curated (
			synset_id TEXT NOT NULL,
			vocab_id INTEGER NOT NULL,
			snap_method TEXT NOT NULL,
			snap_score REAL,
			PRIMARY KEY (synset_id, vocab_id)
		);
		CREATE INDEX idx_spc_synset2 ON synset_properties_curated(synset_id);
		CREATE INDEX idx_spc_vocab2 ON synset_properties_curated(vocab_id);

		CREATE TABLE property_antonyms (
			vocab_id_a INTEGER NOT NULL,
			vocab_id_b INTEGER NOT NULL,
			PRIMARY KEY (vocab_id_a, vocab_id_b)
		);

		-- Curated vocab
		INSERT INTO property_vocab_curated VALUES (1, 'v1', 'hot', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (2, 'v2', 'bright', 'a', 1);
		INSERT INTO property_vocab_curated VALUES (3, 'v3', 'loud', 'a', 1);

		-- Source: src (props: hot, bright, loud)
		INSERT INTO synsets VALUES ('src', 'n', 'source concept');
		INSERT INTO lemmas VALUES ('source', 'src');
		INSERT INTO synset_properties_curated VALUES ('src', 1, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('src', 2, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('src', 3, 'exact', NULL);

		-- tgt_a: shares hot+bright+loud (score 3), has 3 lemmas
		INSERT INTO synsets VALUES ('tgt_a', 'n', 'target A');
		INSERT INTO lemmas VALUES ('alpha1', 'tgt_a');
		INSERT INTO lemmas VALUES ('alpha2', 'tgt_a');
		INSERT INTO lemmas VALUES ('alpha3', 'tgt_a');
		INSERT INTO synset_properties_curated VALUES ('tgt_a', 1, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('tgt_a', 2, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('tgt_a', 3, 'exact', NULL);

		-- tgt_b: shares hot+bright (score 2), 1 lemma
		INSERT INTO synsets VALUES ('tgt_b', 'n', 'target B');
		INSERT INTO lemmas VALUES ('beta', 'tgt_b');
		INSERT INTO synset_properties_curated VALUES ('tgt_b', 1, 'exact', NULL);
		INSERT INTO synset_properties_curated VALUES ('tgt_b', 2, 'exact', NULL);

		-- tgt_c: shares hot (score 1), 1 lemma
		INSERT INTO synsets VALUES ('tgt_c', 'n', 'target C');
		INSERT INTO lemmas VALUES ('gamma', 'tgt_c');
		INSERT INTO synset_properties_curated VALUES ('tgt_c', 1, 'exact', NULL);
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
			t.Logf("  %s (shared=%d)", m.SynsetID, m.SharedCount)
		}
	}
}
