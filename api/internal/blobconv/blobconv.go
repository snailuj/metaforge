// Package blobconv provides conversion between SQLite BLOB storage
// and float32 slices for FastText embeddings.
package blobconv

import (
	"encoding/binary"
	"math"
)

// EmbeddingDim is the FastText embedding dimension (300d).
const EmbeddingDim = 300

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
