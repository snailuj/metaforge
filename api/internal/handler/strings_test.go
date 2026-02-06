package handler

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestStringsEndpoint(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	stringsDir := "../../../strings"
	h.SetStringsDir(stringsDir)

	req := httptest.NewRequest("GET", "/strings/v1/ui.ftl", nil)
	w := httptest.NewRecorder()

	h.HandleStrings(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected 200, got %d: %s", w.Code, w.Body.String())
	}

	body := w.Body.String()
	if !strings.Contains(body, "search-placeholder") {
		t.Error("Expected body to contain 'search-placeholder'")
	}

	ct := w.Header().Get("Content-Type")
	if ct != "text/plain; charset=utf-8" {
		t.Errorf("Expected Content-Type text/plain, got %q", ct)
	}

	cc := w.Header().Get("Cache-Control")
	if !strings.Contains(cc, "immutable") {
		t.Errorf("Expected Cache-Control to contain 'immutable', got %q", cc)
	}
}

func TestStringsEndpoint404(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	h.SetStringsDir("../../../strings")

	req := httptest.NewRequest("GET", "/strings/v1/nonexistent.ftl", nil)
	w := httptest.NewRecorder()

	h.HandleStrings(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("Expected 404 for missing file, got %d", w.Code)
	}
}
