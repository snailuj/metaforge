// api/internal/db/db_test.go
package db

import (
	"testing"

	"github.com/snailuj/metaforge/internal/embeddings"
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

func TestGetSynsetsWithSharedProperties(t *testing.T) {
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
		HAVING COUNT(*) >= 5
		LIMIT 1
	`).Scan(&synsetID)
	if err != nil {
		t.Fatalf("No synset with 5+ properties: %v", err)
	}

	matches, err := GetSynsetsWithSharedProperties(db, synsetID, 0.7, 50)
	if err != nil {
		t.Fatalf("Failed to get shared properties: %v", err)
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

func TestGetForgeMatchesReturnsResults(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// Find a synset with 5+ properties and a centroid
	var synsetID string
	err = db.QueryRow(`
		SELECT sp.synset_id
		FROM synset_properties sp
		JOIN synset_centroids sc ON sc.synset_id = sp.synset_id
		GROUP BY sp.synset_id
		HAVING COUNT(*) >= 5
		LIMIT 1
	`).Scan(&synsetID)
	if err != nil {
		t.Skipf("No synset with 5+ properties and centroid: %v", err)
	}

	matches, err := GetForgeMatches(db, synsetID, 0.7, 50)
	if err != nil {
		t.Fatalf("GetForgeMatches failed: %v", err)
	}

	if len(matches) == 0 {
		t.Skip("No matches found")
	}

	for _, m := range matches {
		if m.SynsetID == "" {
			t.Error("Match has empty synset ID")
		}
		if m.Word == "" {
			t.Errorf("Match %s has empty Word", m.SynsetID)
		}
		if m.Definition == "" {
			t.Errorf("Match %s has empty Definition", m.SynsetID)
		}
		if m.TotalScore <= 0 {
			t.Errorf("Match %s has invalid TotalScore: %f", m.SynsetID, m.TotalScore)
		}
	}
}

func TestGetForgeMatchesExactOverlap(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	var synsetID string
	err = db.QueryRow(`
		SELECT sp.synset_id
		FROM synset_properties sp
		JOIN synset_centroids sc ON sc.synset_id = sp.synset_id
		GROUP BY sp.synset_id
		HAVING COUNT(*) >= 5
		LIMIT 1
	`).Scan(&synsetID)
	if err != nil {
		t.Skipf("No synset with 5+ properties and centroid: %v", err)
	}

	matches, err := GetForgeMatches(db, synsetID, 0.7, 50)
	if err != nil {
		t.Fatalf("GetForgeMatches failed: %v", err)
	}

	for _, m := range matches {
		// ExactOverlap should be consistent with SharedProperties length
		if m.ExactOverlap != len(m.SharedProperties) {
			t.Errorf("Match %s: ExactOverlap=%d but len(SharedProperties)=%d",
				m.SynsetID, m.ExactOverlap, len(m.SharedProperties))
		}
	}
}

func TestGetForgeMatchesCentroidsReturned(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	var synsetID string
	err = db.QueryRow(`
		SELECT sp.synset_id
		FROM synset_properties sp
		JOIN synset_centroids sc ON sc.synset_id = sp.synset_id
		GROUP BY sp.synset_id
		HAVING COUNT(*) >= 5
		LIMIT 1
	`).Scan(&synsetID)
	if err != nil {
		t.Skipf("No synset with 5+ properties and centroid: %v", err)
	}

	matches, err := GetForgeMatches(db, synsetID, 0.7, 50)
	if err != nil {
		t.Fatalf("GetForgeMatches failed: %v", err)
	}

	if len(matches) == 0 {
		t.Skip("No matches found")
	}

	for _, m := range matches {
		if len(m.SourceCentroid) != embeddings.EmbeddingDim {
			t.Errorf("Match %s: SourceCentroid has %d dims, expected %d",
				m.SynsetID, len(m.SourceCentroid), embeddings.EmbeddingDim)
		}
		if len(m.TargetCentroid) != embeddings.EmbeddingDim {
			t.Errorf("Match %s: TargetCentroid has %d dims, expected %d",
				m.SynsetID, len(m.TargetCentroid), embeddings.EmbeddingDim)
		}

		// Distance computed from centroids should be valid
		dist := embeddings.CosineDistance(m.SourceCentroid, m.TargetCentroid)
		if dist < 0 || dist > 2 {
			t.Errorf("Match %s: invalid distance %f from centroids", m.SynsetID, dist)
		}
	}
}

func TestGetForgeMatchesLimitRespected(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	var synsetID string
	err = db.QueryRow(`
		SELECT sp.synset_id
		FROM synset_properties sp
		JOIN synset_centroids sc ON sc.synset_id = sp.synset_id
		GROUP BY sp.synset_id
		HAVING COUNT(*) >= 5
		LIMIT 1
	`).Scan(&synsetID)
	if err != nil {
		t.Skipf("No synset with 5+ properties and centroid: %v", err)
	}

	matches, err := GetForgeMatches(db, synsetID, 0.5, 5)
	if err != nil {
		t.Fatalf("GetForgeMatches failed: %v", err)
	}

	if len(matches) > 5 {
		t.Errorf("Expected at most 5 results, got %d", len(matches))
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
