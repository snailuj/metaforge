// api/internal/handler/handler_test.go
package handler

import (
	"database/sql"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	_ "github.com/mattn/go-sqlite3"
)

const testDBPath = "../../../data-pipeline/output/lexicon_v2.db"

func TestForgeSuggestEndpoint(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	// Use "fire" which has 33 properties in lexicon_v2.db
	req := httptest.NewRequest("GET", "/forge/suggest?word=fire", nil)
	w := httptest.NewRecorder()

	h.HandleSuggest(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("Failed to parse response: %v", err)
	}

	if resp.Source == "" {
		t.Error("Expected source word in response")
	}
}

func TestForgeSuggestWithThreshold(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	// Test with custom threshold
	req := httptest.NewRequest("GET", "/forge/suggest?word=fire&threshold=0.5", nil)
	w := httptest.NewRecorder()

	h.HandleSuggest(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("Failed to parse response: %v", err)
	}

	// Threshold was removed from the curated API — just verify response parsed
	if resp.Source == "" {
		t.Error("Expected source word in response")
	}
}

func TestForgeSuggestWithLimit(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=fire&limit=5", nil)
	w := httptest.NewRecorder()

	h.HandleSuggest(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("Failed to parse response: %v", err)
	}

	if len(resp.Suggestions) > 5 {
		t.Errorf("Expected <= 5 suggestions with limit=5, got %d", len(resp.Suggestions))
	}
}

func TestForgeSuggestMissingWord(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest", nil)
	w := httptest.NewRecorder()

	h.HandleSuggest(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected 400 for missing word, got %d", w.Code)
	}
}

func TestForgeSuggestUnknownWord(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=xyzzy12345", nil)
	w := httptest.NewRecorder()

	h.HandleSuggest(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("Expected 404 for unknown word, got %d", w.Code)
	}
}

func TestForgeSuggestDefaultLimitAndLimit(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	// No threshold or limit params - should use defaults
	req := httptest.NewRequest("GET", "/forge/suggest?word=fire", nil)
	w := httptest.NewRecorder()

	h.HandleSuggest(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("Failed to parse response: %v", err)
	}

	// Verify limit is applied (max 50 suggestions by default)
	if len(resp.Suggestions) > DefaultLimit {
		t.Errorf("Expected <= %d suggestions by default, got %d", DefaultLimit, len(resp.Suggestions))
	}
}

func TestForgeSuggestInvalidThreshold(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	// Invalid threshold (>1) should fall back to default
	req := httptest.NewRequest("GET", "/forge/suggest?word=fire&threshold=1.5", nil)
	w := httptest.NewRecorder()

	h.HandleSuggest(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("Failed to parse response: %v", err)
	}

	// Threshold was removed from curated API — just verify response parsed
	if resp.Source == "" {
		t.Error("Expected source word in response")
	}
}

func TestForgeSuggestInvalidLimit(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	// Invalid limit (>200) should fall back to default
	req := httptest.NewRequest("GET", "/forge/suggest?word=fire&limit=500", nil)
	w := httptest.NewRecorder()

	h.HandleSuggest(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("Failed to parse response: %v", err)
	}

	// Suggestions should be capped at default limit
	if len(resp.Suggestions) > DefaultLimit {
		t.Errorf("Expected <= %d suggestions for invalid limit, got %d", DefaultLimit, len(resp.Suggestions))
	}
}

func TestForgeSuggestNonNumericThreshold(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	// Non-numeric threshold should fall back to default
	req := httptest.NewRequest("GET", "/forge/suggest?word=fire&threshold=abc", nil)
	w := httptest.NewRecorder()

	h.HandleSuggest(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("Failed to parse response: %v", err)
	}

	// Threshold was removed from curated API — just verify response parsed
	if resp.Source == "" {
		t.Error("Expected source word in response")
	}
}

func TestForgeSuggestNonNumericLimit(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	// Non-numeric limit should fall back to default
	req := httptest.NewRequest("GET", "/forge/suggest?word=fire&limit=abc", nil)
	w := httptest.NewRecorder()

	h.HandleSuggest(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("Failed to parse response: %v", err)
	}

	// Should use default limit for non-numeric input
	if len(resp.Suggestions) > DefaultLimit {
		t.Errorf("Expected <= %d suggestions (default), got %d", DefaultLimit, len(resp.Suggestions))
	}
}

func TestForgeSuggestNegativeThreshold(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	// Negative threshold should fall back to default
	req := httptest.NewRequest("GET", "/forge/suggest?word=fire&threshold=-0.5", nil)
	w := httptest.NewRecorder()

	h.HandleSuggest(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("Failed to parse response: %v", err)
	}

	// Threshold was removed from curated API — just verify response parsed
	if resp.Source == "" {
		t.Error("Expected source word in response")
	}
}

func TestForgeSuggestZeroLimit(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	// Zero limit should fall back to default
	req := httptest.NewRequest("GET", "/forge/suggest?word=fire&limit=0", nil)
	w := httptest.NewRecorder()

	h.HandleSuggest(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("Failed to parse response: %v", err)
	}

	// Should use default limit for zero value
	if len(resp.Suggestions) > DefaultLimit {
		t.Errorf("Expected <= %d suggestions (default), got %d", DefaultLimit, len(resp.Suggestions))
	}
}

// --- Autocomplete endpoint tests ---

func TestAutocompleteEndpoint(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/thesaurus/autocomplete?prefix=fir", nil)
	w := httptest.NewRecorder()

	h.HandleAutocomplete(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp AutocompleteResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("Failed to parse response: %v", err)
	}

	if len(resp.Suggestions) == 0 {
		t.Fatal("expected at least one suggestion for prefix 'fir'")
	}

	// Check that suggestions have required fields
	for i, s := range resp.Suggestions {
		if s.Word == "" {
			t.Errorf("suggestion[%d] has empty Word", i)
		}
		if s.Definition == "" {
			t.Errorf("suggestion[%d] has empty Definition", i)
		}
		if s.SenseCount < 1 {
			t.Errorf("suggestion[%d] has SenseCount < 1: %d", i, s.SenseCount)
		}
	}
}

func TestAutocompleteEndpointMissingPrefix(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/thesaurus/autocomplete", nil)
	w := httptest.NewRecorder()

	h.HandleAutocomplete(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected 400 for missing prefix, got %d", w.Code)
	}
}

func TestAutocompleteEndpointShortPrefix(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/thesaurus/autocomplete?prefix=a", nil)
	w := httptest.NewRecorder()

	h.HandleAutocomplete(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected 400 for single-char prefix, got %d", w.Code)
	}
}

func TestAutocompleteEndpointNoMatch(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/thesaurus/autocomplete?prefix=xyzzyplugh", nil)
	w := httptest.NewRecorder()

	h.HandleAutocomplete(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200 for no-match prefix (empty array, not 404), got %d", w.Code)
	}

	var resp AutocompleteResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("Failed to parse response: %v", err)
	}

	if len(resp.Suggestions) != 0 {
		t.Errorf("Expected empty suggestions for no-match prefix, got %d", len(resp.Suggestions))
	}
}

func TestAutocompleteEndpointLimit(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/thesaurus/autocomplete?prefix=fi&limit=3", nil)
	w := httptest.NewRecorder()

	h.HandleAutocomplete(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp AutocompleteResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("Failed to parse response: %v", err)
	}

	if len(resp.Suggestions) > 3 {
		t.Errorf("Expected at most 3 suggestions with limit=3, got %d", len(resp.Suggestions))
	}
}

func TestAutocompleteEndpointLimitCap(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	// Limit > 50 should be capped at 50
	req := httptest.NewRequest("GET", "/thesaurus/autocomplete?prefix=fi&limit=999", nil)
	w := httptest.NewRecorder()

	h.HandleAutocomplete(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp AutocompleteResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("Failed to parse response: %v", err)
	}

	if len(resp.Suggestions) > 50 {
		t.Errorf("Expected at most 50 suggestions (cap), got %d", len(resp.Suggestions))
	}
}

func TestNewHandler_RejectsDBMissingFrequencies(t *testing.T) {
	// Create a temp DB with every required table EXCEPT frequencies.
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "test.db")
	database, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatalf("failed to create temp DB: %v", err)
	}
	// All required tables EXCEPT frequencies.
	for _, tbl := range []string{
		"synsets", "lemmas", "synset_properties_curated", "property_vocab_curated",
		"cluster_antonyms", "vocab_clusters", "lemma_embeddings",
	} {
		if _, err := database.Exec("CREATE TABLE " + tbl + " (id INTEGER)"); err != nil {
			t.Fatalf("failed to create table %s: %v", tbl, err)
		}
	}
	database.Close()

	_, err = NewHandler(dbPath)
	if err == nil {
		t.Fatal("expected error when frequencies table is missing, got nil")
	}
	if !strings.Contains(err.Error(), "frequencies") {
		t.Errorf("error should mention 'frequencies', got: %v", err)
	}

	// Clean up
	os.Remove(dbPath)
}

func TestNewHandler_RejectsDBMissingClusterAntonyms(t *testing.T) {
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "test.db")
	database, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatalf("failed to create temp DB: %v", err)
	}
	// All required tables EXCEPT cluster_antonyms.
	for _, tbl := range []string{
		"synsets", "lemmas", "synset_properties_curated", "property_vocab_curated",
		"frequencies", "vocab_clusters", "lemma_embeddings",
	} {
		if _, err := database.Exec("CREATE TABLE " + tbl + " (id INTEGER)"); err != nil {
			t.Fatalf("failed to create table %s: %v", tbl, err)
		}
	}
	database.Close()

	_, err = NewHandler(dbPath)
	if err == nil {
		t.Fatal("expected error when cluster_antonyms table is missing, got nil")
	}
	if !strings.Contains(err.Error(), "cluster_antonyms") {
		t.Errorf("error should mention 'cluster_antonyms', got: %v", err)
	}
}
