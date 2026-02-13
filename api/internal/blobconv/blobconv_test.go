package blobconv

import (
	"encoding/binary"
	"math"
	"testing"
)

func TestBlobToFloatsNil(t *testing.T) {
	result := BlobToFloats(nil)
	if result != nil {
		t.Errorf("Expected nil for nil blob, got %v", result)
	}
}

func TestBlobToFloatsWrongSize(t *testing.T) {
	result := BlobToFloats([]byte{1, 2, 3})
	if result != nil {
		t.Errorf("Expected nil for wrong-size blob, got %v", result)
	}
}

func TestBlobToFloatsValid(t *testing.T) {
	// Create a valid 300-dim blob with known values
	blob := make([]byte, EmbeddingDim*4)

	// Set first float to 1.5
	binary.LittleEndian.PutUint32(blob[0:4], math.Float32bits(1.5))
	// Set last float to -0.5
	binary.LittleEndian.PutUint32(blob[(EmbeddingDim-1)*4:], math.Float32bits(-0.5))

	result := BlobToFloats(blob)
	if result == nil {
		t.Fatal("Expected non-nil result for valid blob")
	}
	if len(result) != EmbeddingDim {
		t.Errorf("Expected %d floats, got %d", EmbeddingDim, len(result))
	}
	if result[0] != 1.5 {
		t.Errorf("Expected first float 1.5, got %f", result[0])
	}
	if result[EmbeddingDim-1] != -0.5 {
		t.Errorf("Expected last float -0.5, got %f", result[EmbeddingDim-1])
	}
}
