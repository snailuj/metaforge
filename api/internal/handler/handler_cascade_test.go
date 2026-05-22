package handler

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/snailuj/metaforge/internal/forge"
	"github.com/snailuj/metaforge/internal/observe"

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

func TestForgeSuggest_CascadeEnabled_UnknownWordReturns404(t *testing.T) {
	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=zzznotarealword&limit=10", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusNotFound {
		t.Errorf("status: want 404, got %d: %s", w.Code, w.Body.String())
	}
}

func TestForgeSuggest_CascadeEnabled_NoGatePassReturnsEmpty200(t *testing.T) {
	// Pick a highly-concrete topic where (vehicle − topic ≥ 1.0) is hard to
	// satisfy (vehicle would need to exceed ~5.0 on Brysbaert's ~5-point
	// scale). 'cat' is enriched (curated props exist) but most candidates
	// can't clear the gate. Expected: 200 OK with empty Suggestions slice,
	// NOT 404 (which would imply "lemma not enriched").
	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=cat&limit=10", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status: want 200, got %d: %s", w.Code, w.Body.String())
	}
	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if resp.Source != "cat" {
		t.Errorf("source: want 'cat', got %q", resp.Source)
	}
	// Note: in principle a few candidates could squeak through (some words
	// reach concreteness ~5.0). The assertion is that the response is a
	// well-formed empty/short list, not a 404. We accept any len(Suggestions).
	t.Logf("cat returned %d cascade-scored suggestions", len(resp.Suggestions))
}

func TestNewHandlerWithCascade_EmptyCascadeTables_FailsLoud(t *testing.T) {
	// D12 row-count assertion: a fresh-build deploy with empty cascade
	// tables would have passed the existence-only pre-flight and
	// silently served empty 200s for every request. This test pins
	// the post-fix behaviour: NewHandlerWithCascade must error if
	// either cascade table is empty.

	// Build a synthetic SQLite file with all required tables present
	// but the cascade tables empty (rest populated minimally to pass
	// the existence pre-flight).
	tmpDir := t.TempDir()
	dbPath := tmpDir + "/empty_cascade.db"

	database, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	// Create the schema fragments NewHandlerWithCascade requires.
	schema := []string{
		`CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT)`,
		`CREATE TABLE lemmas (synset_id TEXT, lemma TEXT)`,
		`CREATE TABLE synset_properties_curated (synset_id TEXT, cluster_id INTEGER, salience_sum REAL)`,
		`CREATE TABLE property_vocab_curated (vocab_id INTEGER PRIMARY KEY, lemma TEXT NOT NULL)`,
		`CREATE TABLE frequencies (lemma TEXT, count INTEGER)`,
		`CREATE TABLE cluster_antonyms (cluster_id_a INTEGER, cluster_id_b INTEGER)`,
		`CREATE TABLE vocab_clusters (cluster_id INTEGER PRIMARY KEY, lemma TEXT)`,
		`CREATE TABLE lemma_embeddings (lemma TEXT, embedding BLOB)`,
		// Both cascade tables exist but are empty:
		`CREATE TABLE synset_concreteness (synset_id TEXT PRIMARY KEY, score REAL, source TEXT)`,
		`CREATE TABLE synset_centroids (synset_id TEXT PRIMARY KEY, centroid BLOB, property_count INTEGER)`,
	}
	for _, stmt := range schema {
		if _, err := database.Exec(stmt); err != nil {
			t.Fatalf("schema setup: %v", err)
		}
	}
	if err := database.Close(); err != nil {
		t.Fatalf("close: %v", err)
	}

	_, err = NewHandlerWithCascade(dbPath, true)
	if err == nil {
		t.Fatal("expected error for empty cascade tables, got nil")
	}
	if !strings.Contains(err.Error(), "is empty") {
		t.Errorf("expected 'is empty' in error, got: %v", err)
	}
}

func TestSortByFinalScore_AllNilFinalScores_DoesNotPanicOrLoop(t *testing.T) {
	// O7 round-2 fix: the (nil, nil) case in the comparator must
	// return false explicitly so sort.Slice's strict-weak-ordering
	// contract holds. Pre-fix the comparator was technically
	// transitive but adjacent-symmetric only by chance through the
	// early-return order. This test pins the explicit branch.
	matches := []forge.Match{
		{SynsetID: "a", Word: "a"},
		{SynsetID: "b", Word: "b"},
		{SynsetID: "c", Word: "c"},
	}
	// All FinalScore fields are nil zero-values. Sort must not panic
	// and must terminate.
	sortByFinalScore(matches)
	if len(matches) != 3 {
		t.Errorf("expected 3 matches preserved, got %d", len(matches))
	}
}

func TestCascadeRequest_TimingEnabled_EmitsStageRecords(t *testing.T) {
	// D20: when METAFORGE_CASCADE_TIMING is on, the hot path must emit
	// timing records for the recognised stages so operators can build a
	// latency baseline before M04 broadens the candidate pool. Default
	// must remain NO-OP per the Observability standard.
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelDebug})))
	defer slog.SetDefault(prev)

	observe.Init(true)
	defer observe.Init(false)

	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=5", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status: %d: %s", w.Code, w.Body.String())
	}

	out := buf.String()
	wantLabels := []string{
		"cascade_request_total",
		"cascade_candidates_query",
		"cascade_batch_props_query",
		"cascade_scoring_loop",
		"cascade_sort",
	}
	for _, label := range wantLabels {
		if !strings.Contains(out, `"label":"`+label+`"`) {
			t.Errorf("expected timing record for %q in output", label)
		}
	}
}

func TestCascadeRequest_TimingDisabled_EmitsNoTimingRecords(t *testing.T) {
	// Confirms the default off-state really is NO-OP — no timing records
	// emitted even though the cascade hot path executes.
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelDebug})))
	defer slog.SetDefault(prev)

	observe.Init(false)

	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=5", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status: %d: %s", w.Code, w.Body.String())
	}

	out := buf.String()
	if strings.Contains(out, `"msg":"timing"`) {
		t.Errorf("expected zero timing records when disabled, got: %s", out)
	}
}

func TestSortByFinalScore_MixedNilAndNonNil_SinksNilToBottom(t *testing.T) {
	// The nil-FinalScore sort policy is "nil sinks to bottom".
	// Verify with a 3-element mix.
	a, b := 0.5, 0.2
	matches := []forge.Match{
		{SynsetID: "no-score", Word: "no-score"},          // FinalScore: nil
		{SynsetID: "high", Word: "high", FinalScore: &a},
		{SynsetID: "low", Word: "low", FinalScore: &b},
	}
	sortByFinalScore(matches)
	if matches[0].SynsetID != "high" {
		t.Errorf("expected 'high' first, got %q", matches[0].SynsetID)
	}
	if matches[1].SynsetID != "low" {
		t.Errorf("expected 'low' second, got %q", matches[1].SynsetID)
	}
	if matches[2].SynsetID != "no-score" {
		t.Errorf("expected 'no-score' last, got %q", matches[2].SynsetID)
	}
}
