package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/snailuj/metaforge/internal/thesaurus"
)

func TestLookupEndpoint(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/thesaurus/lookup?word=fire", nil)
	w := httptest.NewRecorder()

	h.HandleLookup(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp thesaurus.LookupResult
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("Failed to parse response: %v", err)
	}

	if resp.Word != "fire" {
		t.Errorf("Expected word='fire', got %q", resp.Word)
	}

	if len(resp.Senses) == 0 {
		t.Error("Expected at least one sense")
	}
}

func TestLookupMissingWord(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/thesaurus/lookup", nil)
	w := httptest.NewRecorder()

	h.HandleLookup(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected 400 for missing word, got %d", w.Code)
	}
}

func TestLookupUnknownWord(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/thesaurus/lookup?word=xyzzy12345", nil)
	w := httptest.NewRecorder()

	h.HandleLookup(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("Expected 404 for unknown word, got %d", w.Code)
	}
}
