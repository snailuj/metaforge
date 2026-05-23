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

func TestMatch_M05Fields_OmitemptyWhenZero(t *testing.T) {
	// Pre-M05 / Gamma=0 wire contract: the two M05 diagnostic fields
	// must NOT appear in the JSON when unset, so legacy consumers see
	// the same JSON shape they always have.
	m := Match{SynsetID: "x", Word: "x", TierName: "strong"}
	b, err := json.Marshal(m)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	s := string(b)
	for _, f := range []string{"type_diversity_bonus", "shared_types_count"} {
		if strings.Contains(s, f) {
			t.Errorf("expected %q omitted when unset, got %s", f, s)
		}
	}
}

func TestMatch_M05Fields_SerialiseWhenSet(t *testing.T) {
	// When the cascade computes M05 diagnostics (Gamma>0 + cluster types
	// available), the wire must surface them so operators tuning Gamma
	// can see the underlying bonus and distinct-type count — not just
	// the lift effect on final_score.
	tb := 0.4
	m := Match{
		SynsetID: "x", Word: "x", TierName: "strong",
		TypeDiversityBonus: &tb,
		SharedTypesCount:   3,
	}
	b, err := json.Marshal(m)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	s := string(b)
	for _, f := range []string{"type_diversity_bonus", "shared_types_count"} {
		if !strings.Contains(s, f) {
			t.Errorf("expected %q present, got %s", f, s)
		}
	}
}

func TestMatch_SourceOmittedFromJSONWhenEmpty(t *testing.T) {
	m := Match{SynsetID: "s1", Word: "fire"}
	out, err := json.Marshal(m)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if strings.Contains(string(out), `"candidate_source"`) {
		t.Errorf("zero Source must be omitted from JSON, got %s", out)
	}
}

func TestMatch_SourceSerialisesWhenSet(t *testing.T) {
	m := Match{SynsetID: "s1", Word: "fire", Source: SourceEmbedding}
	out, err := json.Marshal(m)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if !strings.Contains(string(out), `"candidate_source":"embedding"`) {
		t.Errorf("Source serialisation: got %s", out)
	}
}
