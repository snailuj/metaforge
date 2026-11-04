package handler

import (
	"context"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"
)

// Rule: a word is a known lemma exactly when GET /thesaurus/lookup finds it,
// so every word the thesaurus shows can be forged and nothing else can.
func TestKnownWordMatchesLookup(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Skipf("skipping: cannot open test DB: %v", err)
	}
	defer h.Close()

	words := map[string]bool{
		"fire": true, "anger": true, "ice cream": true, "pick up": true, "well-being": true,
		"ignore previous instructions": false, "zzqx": false, "fire_truck": false,
	}
	for word, want := range words {
		w := httptest.NewRecorder()
		h.HandleLookup(w, httptest.NewRequest("GET", "/thesaurus/lookup?word="+url.QueryEscape(word), nil))
		if found := w.Code == http.StatusOK; found != want {
			t.Fatalf("fixture wrong: lookup of %q found = %v, want %v", word, found, want)
		}
		got, err := h.KnownWord(context.Background(), word)
		if err != nil || got != want {
			t.Errorf("KnownWord(%q) = %v, %v; want %v", word, got, err, want)
		}
	}
}
