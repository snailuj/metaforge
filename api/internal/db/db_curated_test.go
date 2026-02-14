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
