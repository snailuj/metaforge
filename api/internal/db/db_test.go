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

	matches, err := GetSynsetsWithSharedProperties(db, "oewn-00002452-n", 0.7, 50)
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
		if m.TotalScore <= 0 {
			t.Errorf("Match %s has invalid TotalScore: %f", m.SynsetID, m.TotalScore)
		}
	}
}

// testDBPathV2 points to the v2 database with similarity tables
const testDBPathV2 = "../../../data-pipeline/output/lexicon_v2.db"

func TestGetSynsetsWithSimilarProperties(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// Find a synset with properties
	var synsetID string
	err = db.QueryRow(`
		SELECT sp.synset_id
		FROM synset_properties sp
		GROUP BY sp.synset_id
		HAVING COUNT(*) >= 3
		LIMIT 1
	`).Scan(&synsetID)
	if err != nil {
		t.Fatalf("No synset with 3+ properties: %v", err)
	}

	// Test with default threshold
	matches, err := GetSynsetsWithSharedProperties(db, synsetID, 0.7, 50)
	if err != nil {
		t.Fatalf("Failed to get similar properties: %v", err)
	}

	if len(matches) == 0 {
		t.Log("No matches found - this may be expected if properties are unique")
	}

	// Verify structure
	for _, m := range matches {
		if m.SynsetID == "" {
			t.Error("Match has empty synset ID")
		}
		if m.TotalScore <= 0 {
			t.Errorf("Match %s has invalid score: %f", m.SynsetID, m.TotalScore)
		}
	}
}

func TestGetSynsetsThresholdEffectsResults(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	var synsetID string
	err = db.QueryRow(`
		SELECT sp.synset_id
		FROM synset_properties sp
		GROUP BY sp.synset_id
		HAVING COUNT(*) >= 5
		LIMIT 1
	`).Scan(&synsetID)
	if err != nil {
		t.Skipf("No synset with 5+ properties: %v", err)
	}

	// Lower threshold should give more results
	lowThreshold, _ := GetSynsetsWithSharedProperties(db, synsetID, 0.5, 100)
	highThreshold, _ := GetSynsetsWithSharedProperties(db, synsetID, 0.8, 100)

	if len(lowThreshold) < len(highThreshold) {
		t.Errorf("Lower threshold should give more results: got %d (0.5) vs %d (0.8)",
			len(lowThreshold), len(highThreshold))
	}
}

func TestGetSynsetsLimitParameter(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	var synsetID string
	err = db.QueryRow(`
		SELECT sp.synset_id
		FROM synset_properties sp
		GROUP BY sp.synset_id
		HAVING COUNT(*) >= 5
		LIMIT 1
	`).Scan(&synsetID)
	if err != nil {
		t.Skipf("No synset with 5+ properties: %v", err)
	}

	// Verify limit is respected
	matches, err := GetSynsetsWithSharedProperties(db, synsetID, 0.5, 10)
	if err != nil {
		t.Fatalf("Failed to get matches: %v", err)
	}

	if len(matches) > 10 {
		t.Errorf("Expected at most 10 results, got %d", len(matches))
	}
}

func TestGetSynsetsResultsAreSortedByScore(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	var synsetID string
	err = db.QueryRow(`
		SELECT sp.synset_id
		FROM synset_properties sp
		GROUP BY sp.synset_id
		HAVING COUNT(*) >= 5
		LIMIT 1
	`).Scan(&synsetID)
	if err != nil {
		t.Skipf("No synset with 5+ properties: %v", err)
	}

	matches, err := GetSynsetsWithSharedProperties(db, synsetID, 0.5, 50)
	if err != nil {
		t.Fatalf("Failed to get matches: %v", err)
	}

	// Verify descending order by TotalScore
	for i := 1; i < len(matches); i++ {
		if matches[i].TotalScore > matches[i-1].TotalScore {
			t.Errorf("Results not sorted: match[%d].TotalScore (%f) > match[%d].TotalScore (%f)",
				i, matches[i].TotalScore, i-1, matches[i-1].TotalScore)
		}
	}
}
