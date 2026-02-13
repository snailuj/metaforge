// Package embeddings provides FastText 300d embedding operations
// for property-based semantic similarity using centroid comparison.
package embeddings

import (
	"database/sql"
	"fmt"
	"math"

	"github.com/snailuj/metaforge/internal/blobconv"
)

// EmbeddingDim is the FastText embedding dimension (300d).
const EmbeddingDim = blobconv.EmbeddingDim

// GetPropertyEmbedding retrieves the FastText 300d embedding for a property.
func GetPropertyEmbedding(db *sql.DB, property string) ([]float32, error) {
	var blob []byte
	err := db.QueryRow(`
		SELECT embedding FROM property_vocabulary WHERE text = ?
	`, property).Scan(&blob)

	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("property not found: %s", property)
	}
	if err != nil {
		return nil, err
	}
	if blob == nil {
		return nil, fmt.Errorf("property has no embedding (OOV): %s", property)
	}

	return BlobToFloats(blob), nil
}

// BlobToFloats converts a byte slice to float32 slice (little-endian).
// Returns nil if the blob is not exactly EmbeddingDim * 4 bytes.
// Delegates to blobconv.BlobToFloats.
func BlobToFloats(blob []byte) []float32 {
	return blobconv.BlobToFloats(blob)
}

// CosineDistance computes 1 - cosine_similarity between two vectors.
// Returns 0 for identical vectors, 1 for orthogonal, 2 for opposite.
func CosineDistance(a, b []float32) float64 {
	if len(a) != len(b) || len(a) == 0 {
		return 1.0
	}

	var dot, normA, normB float64
	for i := range a {
		dot += float64(a[i]) * float64(b[i])
		normA += float64(a[i]) * float64(a[i])
		normB += float64(b[i]) * float64(b[i])
	}

	if normA == 0 || normB == 0 {
		return 1.0
	}

	similarity := dot / (math.Sqrt(normA) * math.Sqrt(normB))
	return 1.0 - similarity
}

