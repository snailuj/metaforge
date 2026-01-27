// api/internal/db/db_test.go
package db

import (
	"testing"
)

func TestOpenDatabase(t *testing.T) {
	db, err := Open("../../../data-pipeline/output/lexicon.db")
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
	db, err := Open("../../../data-pipeline/output/lexicon.db")
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// Use an actual synset from the enrichment table
	synset, err := GetSynset(db, "oewn-00002452-n")
	if err != nil {
		t.Fatalf("Failed to get synset: %v", err)
	}

	if synset.ID != "oewn-00002452-n" {
		t.Errorf("Expected oewn-00002452-n, got %s", synset.ID)
	}

	if len(synset.Properties) == 0 {
		t.Error("Expected properties from enrichment")
	}
}

func TestGetSynsetsWithSharedProperties(t *testing.T) {
	db, err := Open("../../../data-pipeline/output/lexicon.db")
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	matches, err := GetSynsetsWithSharedProperties(db, "oewn-00002452-n")
	if err != nil {
		t.Fatalf("Failed to get shared properties: %v", err)
	}

	if len(matches) == 0 {
		t.Error("Expected at least one match")
	}

	// Verify structure
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
