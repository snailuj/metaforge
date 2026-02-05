// api/internal/forge/forge_test.go
package forge

import (
	"testing"
)

func TestClassifyTier(t *testing.T) {
	tests := []struct {
		name     string
		distance float64
		overlap  int
		expected Tier
	}{
		{"legendary - high distance, strong overlap", 0.8, 4, TierLegendary},
		{"interesting - high distance, weak overlap", 0.8, 1, TierInteresting},
		{"strong - high distance, moderate overlap", 0.8, 2, TierStrong},
		{"obvious - low distance, strong overlap", 0.3, 3, TierObvious},
		{"unlikely - low distance, weak overlap", 0.3, 1, TierUnlikely},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			tier := ClassifyTier(tt.distance, tt.overlap)
			if tier != tt.expected {
				t.Errorf("ClassifyTier(%v, %d) = %v, want %v",
					tt.distance, tt.overlap, tier, tt.expected)
			}
		})
	}
}

func TestTierString(t *testing.T) {
	tests := []struct {
		tier     Tier
		expected string
	}{
		{TierLegendary, "legendary"},
		{TierInteresting, "interesting"},
		{TierStrong, "strong"},
		{TierObvious, "obvious"},
		{TierUnlikely, "unlikely"},
	}

	for _, tt := range tests {
		if tt.tier.String() != tt.expected {
			t.Errorf("Tier %d String() = %s, want %s", tt.tier, tt.tier.String(), tt.expected)
		}
	}
}

func TestNormaliseDistances(t *testing.T) {
	// Simulates real data: distances clustered 0.06-0.30
	distances := []float64{0.06, 0.10, 0.15, 0.20, 0.30}

	normalised := NormaliseDistances(distances)

	// Min should map to 0, max to 1
	if normalised[0] != 0 {
		t.Errorf("Min distance should normalise to 0, got %f", normalised[0])
	}
	if normalised[4] != 1 {
		t.Errorf("Max distance should normalise to 1, got %f", normalised[4])
	}

	// Middle values should be proportional
	// 0.15 is (0.15-0.06)/(0.30-0.06) = 0.09/0.24 = 0.375
	expected := 0.375
	if diff := normalised[2] - expected; diff > 0.001 || diff < -0.001 {
		t.Errorf("Mid distance should be ~%f, got %f", expected, normalised[2])
	}

	// Should be monotonically increasing
	for i := 1; i < len(normalised); i++ {
		if normalised[i] < normalised[i-1] {
			t.Errorf("Not monotonic: [%d]=%f < [%d]=%f", i, normalised[i], i-1, normalised[i-1])
		}
	}
}

func TestNormaliseDistancesEdgeCases(t *testing.T) {
	// Single element
	single := NormaliseDistances([]float64{0.5})
	if single[0] != 0.5 {
		t.Errorf("Single element should be unchanged, got %f", single[0])
	}

	// All same distance
	same := NormaliseDistances([]float64{0.2, 0.2, 0.2})
	for i, d := range same {
		if d != 0.2 {
			t.Errorf("Uniform distances should be unchanged, [%d]=%f", i, d)
		}
	}

	// Empty
	empty := NormaliseDistances([]float64{})
	if len(empty) != 0 {
		t.Errorf("Empty input should return empty, got %d", len(empty))
	}
}

func TestSortByTier(t *testing.T) {
	matches := []Match{
		{SynsetID: "a", Tier: TierUnlikely, OverlapCount: 1},
		{SynsetID: "b", Tier: TierLegendary, OverlapCount: 4},
		{SynsetID: "c", Tier: TierStrong, OverlapCount: 2},
	}

	sorted := SortByTier(matches)

	if sorted[0].SynsetID != "b" {
		t.Errorf("Expected legendary tier first, got %s", sorted[0].SynsetID)
	}
	if sorted[len(sorted)-1].SynsetID != "a" {
		t.Errorf("Expected unlikely tier last, got %s", sorted[len(sorted)-1].SynsetID)
	}
}
