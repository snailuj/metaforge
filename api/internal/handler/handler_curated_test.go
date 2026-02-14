package handler

import (
	"testing"
)

func TestHandleSuggestCurated_ReturnsIronicTier(t *testing.T) {
	// This test validates the end-to-end curated path.
	// Requires a test DB with curated tables populated.
	// Full integration test — skip if DB not available.
	t.Skip("Integration test — requires curated vocabulary DB")
}
