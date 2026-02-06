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

func TestStringsDirectoryTraversal(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("Failed to create handler: %v", err)
	}
	defer h.Close()

	h.SetStringsDir("../../../strings")

	paths := []string{
		"/strings/v1/../../etc/passwd",
		"/strings/../../../etc/shadow",
		"/strings/v1/..%2f..%2fetc/passwd",
	}
	for _, path := range paths {
		req := httptest.NewRequest("GET", path, nil)
		w := httptest.NewRecorder()

		h.HandleStrings(w, req)

		if w.Code == http.StatusOK {
			t.Errorf("Path %q should not return 200", path)
		}
	}
}

func TestCORSMiddleware(t *testing.T) {
	origin := "http://localhost:5173"
	middleware := CORSMiddleware(origin)

	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	handler := middleware(inner)

	t.Run("regular request gets CORS headers", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/thesaurus/lookup?word=fire", nil)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Fatalf("Expected 200, got %d", w.Code)
		}
		if got := w.Header().Get("Access-Control-Allow-Origin"); got != origin {
			t.Errorf("Expected Access-Control-Allow-Origin %q, got %q", origin, got)
		}
	})

	t.Run("OPTIONS preflight returns 204", func(t *testing.T) {
		req := httptest.NewRequest("OPTIONS", "/thesaurus/lookup", nil)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		if w.Code != http.StatusNoContent {
			t.Errorf("Expected 204 for OPTIONS preflight, got %d", w.Code)
		}
		if got := w.Header().Get("Access-Control-Allow-Methods"); !strings.Contains(got, "GET") {
			t.Errorf("Expected Allow-Methods to include GET, got %q", got)
		}
	})
}
