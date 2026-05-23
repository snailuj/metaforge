package db

import (
	"testing"
)

// vec returns a length-300 float32 vector with the supplied prefix and
// the remainder zero-padded — just enough for cosine math to behave.
func vec(prefix ...float32) []float32 {
	v := make([]float32, 300)
	copy(v, prefix)
	return v
}

func TestScanEmbeddingBand_FiltersOutsideBand(t *testing.T) {
	cache := &CascadeCache{
		Centroids: map[string][]float32{
			"topic":     vec(1, 0, 0), // d=0 to itself
			"near":      vec(1, 0, 0), // d≈0 — below dMin
			"in_band_a": vec(0.5, 0.5, 0),
			"in_band_b": vec(0.0, 1.0, 0),
			"far":       vec(-1, 0, 0), // d=2 — above dMax
		},
	}
	hits := scanEmbeddingBand(cache, "topic", 0.2, 1.5, 10)
	got := map[string]bool{}
	for _, h := range hits {
		got[h.synsetID] = true
	}
	if got["topic"] || got["near"] || got["far"] {
		t.Errorf("identity/below-dMin/above-dMax must be excluded; got %v", got)
	}
	if !got["in_band_a"] || !got["in_band_b"] {
		t.Errorf("in-band entries missing; got %v", got)
	}
}

func TestScanEmbeddingBand_CapsAtTopK(t *testing.T) {
	cache := &CascadeCache{Centroids: map[string][]float32{}}
	cache.Centroids["topic"] = vec(1, 0, 0)
	for i := 0; i < 50; i++ {
		// All 50 will be in [0.2, 1.5] band by construction.
		cache.Centroids[idForI(i)] = vec(0.5, 0.5, 0)
	}
	hits := scanEmbeddingBand(cache, "topic", 0.2, 1.5, 7)
	if len(hits) != 7 {
		t.Errorf("want 7 hits (topK), got %d", len(hits))
	}
}

func TestScanEmbeddingBand_NoTopicCentroidReturnsNil(t *testing.T) {
	cache := &CascadeCache{Centroids: map[string][]float32{"other": vec(1, 0, 0)}}
	hits := scanEmbeddingBand(cache, "missing", 0.0, 2.0, 10)
	if hits != nil {
		t.Errorf("missing topic centroid: want nil, got %v", hits)
	}
}

func idForI(i int) string {
	return "c-" + string(rune('a'+i%26)) + string(rune('a'+(i/26)%26))
}
