// api/internal/db/db_test.go
package db

import (
	"errors"
	"testing"
)

func TestOpenDatabase(t *testing.T) {
	db, err := Open(testDBPathV2)
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

func TestGetSynsetWithEnrichment(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// Find a synset with properties from synset_properties junction table
	var synsetID string
	err = db.QueryRow(`
		SELECT sp.synset_id
		FROM synset_properties sp
		GROUP BY sp.synset_id
		HAVING COUNT(*) >= 3
		LIMIT 1
	`).Scan(&synsetID)
	if err != nil {
		t.Fatalf("No synset with properties: %v", err)
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

// testDBPathV2 points to the v2 database
const testDBPathV2 = "../../../data-pipeline/output/lexicon_v2.db"

func TestGetForgeMatchesCuratedByLemma_ReturnsErrLemmaNotFound(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	_, err = GetForgeMatchesCuratedByLemma(db, "xyzzynotaword12345", 50)
	if err == nil {
		t.Fatal("Expected error for nonexistent lemma, got nil")
	}
	if !errors.Is(err, ErrLemmaNotFound) {
		t.Errorf("Expected ErrLemmaNotFound, got: %v", err)
	}
}

func TestGetSynsetIDForLemma(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// "fire" should exist and return a synset ID
	synsetID, err := GetSynsetIDForLemma(db, "fire")
	if err != nil {
		t.Fatalf("GetSynsetIDForLemma(fire) failed: %v", err)
	}
	if synsetID == "" {
		t.Error("Expected non-empty synset ID for 'fire'")
	}
}

func TestGetSynsetIDForLemmaNotFound(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	_, err = GetSynsetIDForLemma(db, "xyzzynotaword12345")
	if err == nil {
		t.Error("Expected error for nonexistent lemma")
	}
}

func TestGetLemmaForSynset(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// First get a valid synset ID
	synsetID, err := GetSynsetIDForLemma(db, "fire")
	if err != nil {
		t.Fatalf("GetSynsetIDForLemma(fire) failed: %v", err)
	}

	lemma, err := GetLemmaForSynset(db, synsetID)
	if err != nil {
		t.Fatalf("GetLemmaForSynset(%s) failed: %v", synsetID, err)
	}
	if lemma == "" {
		t.Error("Expected non-empty lemma")
	}
}

func TestGetLemmaForSynsetNotFound(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	_, err = GetLemmaForSynset(db, "999999999")
	if err == nil {
		t.Error("Expected error for nonexistent synset")
	}
}

func TestGetSynsetNotFound(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	_, err = GetSynset(db, "999999999")
	if err == nil {
		t.Error("Expected error for nonexistent synset ID")
	}
}

func TestGetSynsetsNotFound(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// Nonexistent synset ID should return error
	_, err = GetSynset(db, "nonexistent99999")
	if err == nil {
		t.Error("Expected error for nonexistent synset ID")
	}
}

func TestGetSynsetsNoProperties(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// Find a synset with no properties
	var synsetID string
	err = db.QueryRow(`
		SELECT s.synset_id
		FROM synsets s
		WHERE NOT EXISTS (
			SELECT 1 FROM synset_properties sp
			WHERE sp.synset_id = s.synset_id
		)
		LIMIT 1
	`).Scan(&synsetID)
	if err != nil {
		t.Skipf("No synset without properties found: %v", err)
	}

	synset, err := GetSynset(db, synsetID)
	if err != nil {
		t.Fatalf("GetSynset failed: %v", err)
	}

	// Synset should have no properties
	if len(synset.Properties) != 0 {
		t.Errorf("Expected 0 properties for synset %s, got %d", synsetID, len(synset.Properties))
	}
}
