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
