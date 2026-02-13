// api/internal/handler/handler_test.go
package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
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

	// Verify threshold is included in response
	if resp.Threshold != 0.5 {
		t.Errorf("Expected threshold=0.5, got %f", resp.Threshold)
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

func TestForgeSuggestDefaultThresholdAndLimit(t *testing.T) {
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

	// Verify default threshold
	if resp.Threshold != DefaultThreshold {
		t.Errorf("Expected default threshold=%f, got %f", DefaultThreshold, resp.Threshold)
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

	// Should use default threshold for invalid value
	if resp.Threshold != DefaultThreshold {
		t.Errorf("Expected default threshold for invalid input, got %f", resp.Threshold)
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

	// Should use default threshold for non-numeric input
	if resp.Threshold != DefaultThreshold {
		t.Errorf("Expected default threshold=%f, got %f", DefaultThreshold, resp.Threshold)
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

	// Should use default threshold for negative value
	if resp.Threshold != DefaultThreshold {
		t.Errorf("Expected default threshold=%f, got %f", DefaultThreshold, resp.Threshold)
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
