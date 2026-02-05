// api/internal/embeddings/embeddings_test.go
package embeddings

import (
	"database/sql"
	"testing"

	_ "github.com/mattn/go-sqlite3"
)

const testDBPath = "../../../data-pipeline/output/lexicon_v2.db"

func openTestDB(t *testing.T) *sql.DB {
	db, err := sql.Open("sqlite3", testDBPath+"?mode=ro")
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	return db
}

func TestGetPropertyEmbedding(t *testing.T) {
	db := openTestDB(t)
	defer db.Close()

	// Test with a property that has an embedding
	emb, err := GetPropertyEmbedding(db, "warm")
	if err != nil {
		t.Fatalf("Failed to get embedding for 'warm': %v", err)
	}

	if len(emb) != EmbeddingDim {
		t.Errorf("Expected %d dimensions, got %d", EmbeddingDim, len(emb))
	}
}

func TestCosineDistance(t *testing.T) {
	// Identical vectors should have distance 0
	v := []float32{1, 0, 0}
	dist := CosineDistance(v, v)
	if dist != 0 {
		t.Errorf("Expected distance 0 for identical vectors, got %f", dist)
	}

	// Orthogonal vectors should have distance 1
	v1 := []float32{1, 0, 0}
	v2 := []float32{0, 1, 0}
	dist = CosineDistance(v1, v2)
	if dist != 1 {
		t.Errorf("Expected distance 1 for orthogonal vectors, got %f", dist)
	}
}

func TestComputeSynsetDistance(t *testing.T) {
	db := openTestDB(t)
	defer db.Close()

	// Find two synsets that have properties
	var synsetA, synsetB string
	rows, err := db.Query(`
		SELECT DISTINCT synset_id FROM synset_properties LIMIT 2
	`)
	if err != nil {
		t.Fatalf("Failed to query synsets: %v", err)
	}
	defer rows.Close()

	if rows.Next() {
		rows.Scan(&synsetA)
	}
	if rows.Next() {
		rows.Scan(&synsetB)
	}

	if synsetA == "" || synsetB == "" {
		t.Skip("Need at least 2 synsets with properties")
	}

	dist, err := ComputeSynsetDistance(db, synsetA, synsetB)
	if err != nil {
		t.Fatalf("Failed to compute distance: %v", err)
	}

	// Distance should be between 0 and 2
	if dist < 0 || dist > 2 {
		t.Errorf("Distance should be 0-2, got %f", dist)
	}
}
