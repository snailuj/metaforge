// api/internal/forge/forge_test.go
package forge

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestTierString(t *testing.T) {
	tests := []struct {
		tier     Tier
		expected string
	}{
		{TierLegendary, "legendary"},
		{TierComplex, "complex"},
		{TierIronic, "ironic"},
		{TierStrong, "strong"},
		{TierUnlikely, "unlikely"},
	}

	for _, tt := range tests {
		if tt.tier.String() != tt.expected {
			t.Errorf("Tier %d String() = %s, want %s", tt.tier, tt.tier.String(), tt.expected)
		}
	}
}

func TestTierStringOutOfRange(t *testing.T) {
	// Out-of-range tier should return "unknown", not panic
	result := Tier(99).String()
	if result != "unknown" {
		t.Errorf("Tier(99).String() = %q, want %q", result, "unknown")
	}

	// Negative value
	result = Tier(-1).String()
	if result != "unknown" {
		t.Errorf("Tier(-1).String() = %q, want %q", result, "unknown")
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

func TestMatch_CascadeFieldsOmitemptyWhenAbsent(t *testing.T) {
	m := Match{SynsetID: "x", Word: "x", TierName: "strong"}
	b, _ := json.Marshal(m)
	s := string(b)
	for _, f := range []string{"final_score", "cascade_status", "gate_passed", "ortony_score", "cosine_distance", "re_rank_bonus"} {
		if strings.Contains(s, f) {
			t.Errorf("expected %q omitted, got %s", f, s)
		}
	}
}

func TestMatch_CascadeFieldsSerialiseWhenSet(t *testing.T) {
	score, ortony, bonus := 0.42, 0.30, 0.16
	m := Match{
		SynsetID: "x", Word: "x", TierName: "strong",
		FinalScore: &score, CascadeStatus: "scored",
		GatePassed: true, OrtonyScore: &ortony, ReRankBonus: &bonus,
	}
	b, _ := json.Marshal(m)
	s := string(b)
	for _, f := range []string{"final_score", "cascade_status", "gate_passed", "ortony_score", "re_rank_bonus"} {
		if !strings.Contains(s, f) {
			t.Errorf("expected %q present, got %s", f, s)
		}
	}
}
