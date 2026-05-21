package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	_ "github.com/mattn/go-sqlite3"
)

func TestForgeSuggest_CascadeDisabledByDefault_UsesLegacyShape(t *testing.T) {
	h, err := NewHandler(testDBPath)
	if err != nil {
		t.Fatalf("NewHandler: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=fire&limit=3", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status: %d: %s", w.Code, w.Body.String())
	}
	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	for _, m := range resp.Suggestions {
		if m.CascadeStatus != "" {
			t.Errorf("legacy path leaked CascadeStatus=%q", m.CascadeStatus)
		}
		if m.FinalScore != nil {
			t.Errorf("legacy path leaked FinalScore=%v", *m.FinalScore)
		}
	}
}

func TestForgeSuggest_CascadeEnabled_PopulatesCascadeFields(t *testing.T) {
	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=10", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status: %d: %s", w.Code, w.Body.String())
	}
	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	sawScored := false
	for _, m := range resp.Suggestions {
		if m.CascadeStatus == "" {
			t.Errorf("cascade response missing CascadeStatus on %s", m.Word)
		}
		if m.CascadeStatus == "scored" {
			sawScored = true
			if m.FinalScore == nil || m.OrtonyScore == nil {
				t.Errorf("scored result missing FinalScore/OrtonyScore for %s", m.Word)
			}
		}
		if m.CascadeStatus == "gate_dropped" {
			t.Errorf("gate_dropped pair leaked into response: %s", m.Word)
		}
	}
	if !sawScored {
		t.Error("expected at least one scored cascade result for 'anger'")
	}
}

func TestForgeSuggest_CascadeEnabled_RankedByFinalScore(t *testing.T) {
	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=10", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	var prev *float64
	for _, m := range resp.Suggestions {
		if m.FinalScore == nil {
			continue
		}
		if prev != nil && *m.FinalScore > *prev {
			t.Errorf("results not sorted by final_score descending: %v after %v", *m.FinalScore, *prev)
		}
		prev = m.FinalScore
	}
}
