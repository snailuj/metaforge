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

func TestBlobToFloatsWrongSize(t *testing.T) {
	// Blob not exactly EmbeddingDim * 4 bytes should return nil
	result := BlobToFloats([]byte{1, 2, 3})
	if result != nil {
		t.Errorf("Expected nil for wrong-size blob, got %v", result)
	}
}

func TestBlobToFloatsNil(t *testing.T) {
	result := BlobToFloats(nil)
	if result != nil {
		t.Errorf("Expected nil for nil blob, got %v", result)
	}
}

func TestCosineDistanceEmptyVectors(t *testing.T) {
	dist := CosineDistance([]float32{}, []float32{})
	if dist != 1.0 {
		t.Errorf("Expected 1.0 for empty vectors, got %f", dist)
	}
}

func TestCosineDistanceMismatchedLengths(t *testing.T) {
	dist := CosineDistance([]float32{1, 0}, []float32{1})
	if dist != 1.0 {
		t.Errorf("Expected 1.0 for mismatched vectors, got %f", dist)
	}
}

func TestCosineDistanceZeroVector(t *testing.T) {
	zero := []float32{0, 0, 0}
	nonzero := []float32{1, 0, 0}
	dist := CosineDistance(zero, nonzero)
	if dist != 1.0 {
		t.Errorf("Expected 1.0 for zero vector, got %f", dist)
	}
}

func TestCosineDistanceOppositeVectors(t *testing.T) {
	v1 := []float32{1, 0, 0}
	v2 := []float32{-1, 0, 0}
	dist := CosineDistance(v1, v2)
	if dist != 2.0 {
		t.Errorf("Expected 2.0 for opposite vectors, got %f", dist)
	}
}

func TestGetPropertyEmbeddingNotFound(t *testing.T) {
	db := openTestDB(t)
	defer db.Close()

	_, err := GetPropertyEmbedding(db, "xyzzynotaproperty12345")
	if err == nil {
		t.Error("Expected error for nonexistent property")
	}
}

func TestGetPropertyEmbeddingOOV(t *testing.T) {
	db := openTestDB(t)
	defer db.Close()

	// "adducting" exists in property_vocabulary but has NULL embedding (OOV)
	_, err := GetPropertyEmbedding(db, "adducting")
	if err == nil {
		t.Error("Expected error for OOV property with null embedding")
	}
}

func TestBlobToFloatsValidBlob(t *testing.T) {
	// Create a valid 300-dim blob (all zeros)
	blob := make([]byte, EmbeddingDim*4)
	result := BlobToFloats(blob)
	if result == nil {
		t.Fatal("Expected non-nil result for valid-size blob")
	}
	if len(result) != EmbeddingDim {
		t.Errorf("Expected %d floats, got %d", EmbeddingDim, len(result))
	}
}
