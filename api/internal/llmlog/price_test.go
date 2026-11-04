package llmlog

import (
	"math"
	"testing"
)

func near(a, b float64) bool { return math.Abs(a-b) < 1e-12 }

func TestCostHaikuShortPrompt(t *testing.T) {
	u := Usage{InputTokens: 1_000_000, OutputTokens: 1_000_000, CacheReadTokens: 1_000_000, CacheWriteTokens: 1_000_000}
	got, known := Cost("claude-haiku-5-5", u)
	if !known {
		t.Fatal("haiku 5.5 should be priced")
	}
	// The prompt is 3M tokens, over the 100K line, so the long rate card applies.
	want := 0.50 + 2.50 + 0.05 + 0.625
	if !near(got, want) {
		t.Fatalf("cost = %v, want %v", got, want)
	}
}

func TestCostHaikuUnderLongPromptLine(t *testing.T) {
	u := Usage{InputTokens: 2_000, OutputTokens: 4_000, CacheReadTokens: 1_000, CacheWriteTokens: 500}
	got, _ := Cost("claude-haiku-5-5", u)
	want := (2_000*0.10 + 4_000*0.50 + 1_000*0.01 + 500*0.125) / 1e6
	if !near(got, want) {
		t.Fatalf("cost = %v, want %v", got, want)
	}
}

func TestCostOpusCacheReadRate(t *testing.T) {
	got, known := Cost("claude-opus-5-5", Usage{CacheReadTokens: 1_000_000})
	if !known || !near(got, 0.20) {
		t.Fatalf("cost = %v known=%v, want 0.20 true", got, known)
	}
}

// An unknown model is priced at the dearest card so the weekly cap errs
// towards stopping early, never towards overspending.
func TestCostUnknownModelUsesDearestRate(t *testing.T) {
	got, known := Cost("claude-something-new", Usage{InputTokens: 1_000_000, OutputTokens: 1_000_000})
	if known {
		t.Fatal("unknown model reported as known")
	}
	if !near(got, 10+50) {
		t.Fatalf("cost = %v, want 60", got)
	}
}
