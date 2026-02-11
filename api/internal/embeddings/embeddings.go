// Package embeddings provides FastText 300d embedding operations
// for property-based semantic similarity using centroid comparison.
package embeddings

import (
	"database/sql"
	"encoding/binary"
	"fmt"
	"log/slog"
	"math"
)

// EmbeddingDim is the FastText embedding dimension (300d)
const EmbeddingDim = 300

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
func BlobToFloats(blob []byte) []float32 {
	if len(blob) != EmbeddingDim*4 {
		return nil
	}
	vec := make([]float32, EmbeddingDim)
	for i := 0; i < EmbeddingDim; i++ {
		bits := binary.LittleEndian.Uint32(blob[i*4 : (i+1)*4])
		vec[i] = math.Float32frombits(bits)
	}
	return vec
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

// ComputeSynsetDistance computes semantic distance between two synsets
// using centroid comparison of their property embeddings.
//
// Returns cosine distance (0 = identical, 1 = orthogonal, 2 = opposite).
func ComputeSynsetDistance(db *sql.DB, synsetA, synsetB string) (float64, error) {
	embsA, err := getSynsetPropertyEmbeddings(db, synsetA)
	if err != nil {
		return 1.0, err
	}

	embsB, err := getSynsetPropertyEmbeddings(db, synsetB)
	if err != nil {
		return 1.0, err
	}

	if len(embsA) == 0 || len(embsB) == 0 {
		return 1.0, nil // No embeddings to compare
	}

	centroidA := computeCentroid(embsA)
	centroidB := computeCentroid(embsB)

	return CosineDistance(centroidA, centroidB), nil
}

// getSynsetPropertyEmbeddings returns all property embeddings for a synset.
func getSynsetPropertyEmbeddings(db *sql.DB, synsetID string) ([][]float32, error) {
	rows, err := db.Query(`
		SELECT pv.embedding
		FROM synset_properties sp
		JOIN property_vocabulary pv ON pv.property_id = sp.property_id
		WHERE sp.synset_id = ? AND pv.embedding IS NOT NULL
	`, synsetID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var embeddings [][]float32
	for rows.Next() {
		var blob []byte
		if err := rows.Scan(&blob); err != nil {
			slog.Warn("scan embedding blob failed", "synset", synsetID, "err", err)
			continue
		}
		if vec := BlobToFloats(blob); vec != nil {
			embeddings = append(embeddings, vec)
		}
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating property embeddings for %s: %w", synsetID, err)
	}

	return embeddings, nil
}

// computeCentroid computes the average vector of a set of embeddings.
func computeCentroid(embeddings [][]float32) []float32 {
	if len(embeddings) == 0 {
		return nil
	}

	centroid := make([]float32, len(embeddings[0]))
	for _, emb := range embeddings {
		for i, v := range emb {
			centroid[i] += v
		}
	}

	n := float32(len(embeddings))
	for i := range centroid {
		centroid[i] /= n
	}

	return centroid
}
