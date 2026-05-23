package handler

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

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
		// Startup-phase labels (emitted during NewHandlerWithCascade →
		// LoadCascadeCache with timing already enabled by Init above).
		"cascade_cache_load_total",
		"cascade_cache_load_concreteness",
		"cascade_cache_load_centroids",
		// Request-phase labels.
		"cascade_request_total",
		"cascade_candidates_query",
		"cascade_batch_props_query",
		"cascade_scoring_loop",
		"cascade_sort",
		"cascade_response_encode",
	}
	for _, label := range wantLabels {
		if !strings.Contains(out, `"label":"`+label+`"`) {
			t.Errorf("expected timing record for %q in output", label)
		}
	}
}

func TestCascadeRequest_TimingEnabled_EmptyNoGatePass_EmitsEncodeStage(t *testing.T) {
	// R3-S1/R3-OWN-1: the cascade_response_encode timer on the empty
	// (no-gate-pass) branch was added in round 2 commit e793e168 but the
	// existing TimingEnabled test only exercises the scored path ('anger'
	// has gate-pass candidates). This test pins the symmetric instrumentation
	// using 'cat' — a highly-concrete topic that usually produces an empty
	// Suggestions list — and asserts that cascade_response_encode AND
	// cascade_request_total both fire regardless of which branch the request
	// lands on. Robust against the rare case 'cat' returns scored candidates
	// because both branches emit the encode label.
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

	req := httptest.NewRequest("GET", "/forge/suggest?word=cat&limit=5", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status: %d: %s", w.Code, w.Body.String())
	}

	out := buf.String()
	for _, label := range []string{"cascade_response_encode", "cascade_request_total"} {
		if !strings.Contains(out, `"label":"`+label+`"`) {
			t.Errorf("expected timing record for %q regardless of branch, got: %s", label, out)
		}
	}
	// R4-ST3 / R4-S1 tightening: assert this test actually pinned the
	// empty branch's outcome enum, not just its label presence. If the
	// fixture drifts so 'cat' starts scoring, this assertion fires and
	// the test author re-picks a fixture rather than silently moving to
	// scored-branch coverage.
	if !strings.Contains(out, `"outcome":"empty_no_gate_pass"`) {
		t.Errorf("expected outcome=empty_no_gate_pass on this fixture — 'cat' may have started scoring, re-pick fixture or stub candidates: %s", out)
	}
}

// failingWriter is an http.ResponseWriter that returns an error from
// every Write call. Used to exercise the encode-error outcome branches
// on /forge/suggest cascade paths (R4-OWN-2 / R4-ST2 pins).
type failingWriter struct {
	header http.Header
	code   int
}

func (f *failingWriter) Header() http.Header {
	if f.header == nil {
		f.header = make(http.Header)
	}
	return f.header
}

func (f *failingWriter) Write(p []byte) (int, error) {
	return 0, fmt.Errorf("simulated write failure")
}

func (f *failingWriter) WriteHeader(code int) {
	f.code = code
}

func TestCascadeRequest_ScoredEncodeError_OutcomeBranches(t *testing.T) {
	// R4-OWN-2 / R4-ST2 pin: when json.NewEncoder.Encode fails on the
	// scored path, cascade_request_total must record
	// outcome="scored_encode_error" rather than the happy "scored".
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
	w := &failingWriter{}
	h.HandleSuggest(w, req)

	out := buf.String()
	if !strings.Contains(out, `"outcome":"scored_encode_error"`) {
		t.Errorf("expected scored_encode_error outcome on failing writer, got: %s", out)
	}
}

func TestCascadeRequest_EmptyEncodeError_OutcomeBranches(t *testing.T) {
	// R4-OWN-2 / R4-ST2 pin: when json.NewEncoder.Encode fails on the
	// empty-no-gate-pass path, cascade_request_total must record
	// outcome="empty_encode_error".
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

	req := httptest.NewRequest("GET", "/forge/suggest?word=cat&limit=5", nil)
	w := &failingWriter{}
	h.HandleSuggest(w, req)

	out := buf.String()
	if !strings.Contains(out, `"outcome":"empty_encode_error"`) {
		t.Errorf("expected empty_encode_error outcome on failing writer + no-gate-pass fixture, got: %s", out)
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

// TestCascadeUnion_ClassicalPairsSurface_AsCandidates pins M04's binary
// generation criterion: the four canonical cross-domain pairs MUST
// reach the cascade scorer as candidates when ModeUnion is active.
// We assert candidate PRESENCE only — final-score rank is M05/M06
// territory and out of scope here. The vehicle is the second synset
// of the pair; we accept a hit on ANY of its lemmas.
func TestCascadeUnion_ClassicalPairsSurface_AsCandidates(t *testing.T) {
	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	cfg := forge.DefaultCascadeConfig()
	cfg.Mode = forge.ModeUnion
	cfg.EmbeddingDMin = 0.0
	cfg.EmbeddingDMax = 2.0
	// TopK pinned at forge.EmbeddingTopKCeiling for the canary: this
	// test asserts CANDIDATE PRESENCE, not production ranking.
	// Diagnostics show "hammer" lands at rank ~4600 by cosine distance
	// from "truth", "money" at ~2000 from "time" — both within band but
	// well outside production TopK=100. Widening here is intentional
	// and isolated to this test; the ceiling bounds it to a value the
	// SQLite IN-clause can safely accept, and DMax=2.0 expands the band
	// to its theoretical maximum so distant-but-in-cache candidates
	// still surface in this candidate-presence canary.
	cfg.EmbeddingTopK = forge.EmbeddingTopKCeiling // = 10000; lab-mode max
	if err := h.WithCascadeConfig(cfg); err != nil {
		t.Fatalf("WithCascadeConfig: %v", err)
	}

	cases := []struct {
		topic   string
		vehicle string // lemma we expect to see in suggestions
	}{
		{"anger", "fire"},
		{"idea", "light"},
		{"time", "money"},
		{"truth", "hammer"},
	}
	for _, tc := range cases {
		t.Run(tc.topic+"-"+tc.vehicle, func(t *testing.T) {
			req := httptest.NewRequest("GET",
				"/forge/suggest?word="+tc.topic+"&limit=200", nil)
			w := httptest.NewRecorder()
			h.HandleSuggest(w, req)
			if w.Code != http.StatusOK {
				t.Fatalf("status %d: %s", w.Code, w.Body.String())
			}
			var resp SuggestResponse
			if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
				t.Fatalf("decode: %v", err)
			}
			for _, s := range resp.Suggestions {
				if s.Word == tc.vehicle {
					return // hit — pass
				}
			}
			words := make([]string, 0, len(resp.Suggestions))
			for _, s := range resp.Suggestions {
				words = append(words, s.Word)
			}
			t.Errorf("vehicle %q not present in %d suggestions for %q (sample: %v)",
				tc.vehicle, len(resp.Suggestions), tc.topic, words[:min(10, len(words))])
		})
	}
}

// TestCascadeClusterOnly_ResponseShapeUnchanged pins the contract that
// Mode=cluster_only behaves byte-for-byte identically to
// the pre-M04 M03 cascade. The assertion is "no row carries Source !=
// SourceCluster" plus "the embedding query stage timer is NOT emitted"
// — i.e. the embedding path is fully skipped, not run-and-discarded.
func TestCascadeClusterOnly_ResponseShapeUnchanged(t *testing.T) {
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

	cfg := forge.DefaultCascadeConfig()
	cfg.Mode = forge.ModeCluster
	if err := h.WithCascadeConfig(cfg); err != nil {
		t.Fatalf("WithCascadeConfig: %v", err)
	}

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=20", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}

	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	for _, s := range resp.Suggestions {
		if s.Source != "" && s.Source != forge.SourceCluster {
			t.Errorf("cluster_only mode produced %q-tagged suggestion %s", s.Source, s.Word)
		}
	}
	if strings.Contains(buf.String(), `"cascade_embedding_query"`) {
		t.Errorf("cluster_only mode must NOT emit cascade_embedding_query stage timer:\n%s", buf.String())
	}
}

// TestCascadeEmbeddingOnly_ProducesEmbeddingTaggedRowsOnly pins the
// embedding_only mode contract: every returned row is tagged
// SourceEmbedding, no cluster-overlap query timer is emitted, and the
// canary anger→fire pair still surfaces.
func TestCascadeEmbeddingOnly_ProducesEmbeddingTaggedRowsOnly(t *testing.T) {
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

	cfg := forge.DefaultCascadeConfig()
	cfg.Mode = forge.ModeEmbedding
	cfg.EmbeddingDMin = 0.0
	cfg.EmbeddingDMax = 1.5
	cfg.EmbeddingTopK = 200
	if err := h.WithCascadeConfig(cfg); err != nil {
		t.Fatalf("WithCascadeConfig: %v", err)
	}

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=200", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}

	var resp SuggestResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	for _, s := range resp.Suggestions {
		if s.Source != forge.SourceEmbedding {
			t.Errorf("embedding_only mode produced %q-tagged suggestion %s", s.Source, s.Word)
		}
	}
	logs := buf.String()
	if strings.Contains(logs, `"cascade_candidates_query"`) {
		// Cluster-path query timer must NOT fire in embedding_only mode.
		t.Errorf("embedding_only mode must skip cluster path; saw cascade_candidates_query in logs")
	}
}

// TestCascadeUnion_LatencyBudget pins the M04 latency floor: a union-mode
// request for 'anger' (broad lemma, ~35k centroid scan) must complete
// within 750ms in-process. Threshold is generous vs the spec's 500ms p99
// — this is a smoke test running under the Go test framework, not a
// production benchmark.
func TestCascadeUnion_LatencyBudget(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping latency smoke in -short mode")
	}
	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	cfg := forge.DefaultCascadeConfig()
	cfg.Mode = forge.ModeUnion
	if err := h.WithCascadeConfig(cfg); err != nil {
		t.Fatalf("WithCascadeConfig: %v", err)
	}

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=50", nil)
	w := httptest.NewRecorder()

	start := time.Now()
	h.HandleSuggest(w, req)
	elapsed := time.Since(start)

	if w.Code != http.StatusOK {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}
	if elapsed > 750*time.Millisecond {
		t.Errorf("union-mode anger limit=50 took %v, want ≤ 750ms", elapsed)
	}
	t.Logf("union-mode anger limit=50 elapsed: %v", elapsed)
}

// TestCascade_AggregatesConcretenessCacheMisses_NoPerCandidateSpam pins
// the R1-D4 fix: per-candidate concreteness cache-miss spam must be
// replaced by a single aggregate Error log post-loop plus a count attr
// on cascade_request_total. We can't easily force a real cache divergence
// against the test DB, so this test asserts the steady-state contract:
// under a healthy cache the per-candidate Error log MUST NOT fire even
// once during a normal request. (Direct positive verification of the
// aggregator path requires a fixture that diverges cache from SQL — see
// Task 16 for the runtime tripwire which closes that gap.)
func TestCascade_AggregatesConcretenessCacheMisses_NoPerCandidateSpam(t *testing.T) {
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelDebug})))
	defer slog.SetDefault(prev)

	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=50", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}
	if strings.Contains(buf.String(), "cascade candidate concreteness missing from cache despite SQL filter") {
		t.Errorf("per-candidate concreteness Error log must not fire on healthy data:\n%s", buf.String())
	}
}

// TestCascade_EmptyPropsByID_FlagsAggregatorAndContinues pins the R4-D1
// behaviour: when batch props returns empty for all candidates, we do
// NOT emit a per-request Error spam — instead we set the aggregator
// flag and continue serving. Verified via a synthetic DB where
// synset_properties_curated is empty but cascade tables are populated.
// (Note: this is a low-fidelity proxy — the test DB has properties,
// so we assert the negative steady-state contract.)
func TestCascade_EmptyPropsByID_NoErrorLogOnHealthyData(t *testing.T) {
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelDebug})))
	defer slog.SetDefault(prev)

	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=20", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}
	if strings.Contains(buf.String(), "cascade batch properties returned empty for all candidates") {
		t.Errorf("per-request empty-propsByID Error log must not fire on healthy data:\n%s", buf.String())
	}
}

// TestNewHandlerWithCascade_EmptyCuratedProps_FailsLoud extends the
// post-preflight tripwire to also assert synset_properties_curated is
// non-empty. Closes R1-D4 — without this, a deploy with all cascade
// tables populated but curated_props empty would pass startup and
// silently serve no_properties for every gate-passed candidate.
func TestNewHandlerWithCascade_EmptyCuratedProps_FailsLoud(t *testing.T) {
	tmpDir := t.TempDir()
	dbPath := tmpDir + "/empty_curated.db"

	database, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	schema := []string{
		`CREATE TABLE synsets (synset_id TEXT PRIMARY KEY, pos TEXT, definition TEXT)`,
		`CREATE TABLE lemmas (synset_id TEXT, lemma TEXT)`,
		// Empty curated table — this is the failure mode we're trying to catch.
		`CREATE TABLE synset_properties_curated (synset_id TEXT, cluster_id INTEGER, salience_sum REAL)`,
		`CREATE TABLE property_vocab_curated (vocab_id INTEGER PRIMARY KEY, lemma TEXT NOT NULL)`,
		`CREATE TABLE frequencies (lemma TEXT, count INTEGER)`,
		`CREATE TABLE cluster_antonyms (cluster_id_a INTEGER, cluster_id_b INTEGER)`,
		`CREATE TABLE vocab_clusters (cluster_id INTEGER PRIMARY KEY, lemma TEXT)`,
		`CREATE TABLE lemma_embeddings (lemma TEXT, embedding BLOB)`,
		// Cascade tables populated with one row each (need a row so the
		// existing existence-AND-row check passes for them).
		`CREATE TABLE synset_concreteness (synset_id TEXT PRIMARY KEY, score REAL, source TEXT)`,
		`INSERT INTO synset_concreteness VALUES ('test-1', 3.0, 'test')`,
		`CREATE TABLE synset_centroids (synset_id TEXT PRIMARY KEY, centroid BLOB, property_count INTEGER)`,
		`INSERT INTO synset_centroids VALUES ('test-1', x'00', 1)`,
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
		t.Fatal("expected error for empty synset_properties_curated, got nil")
	}
	if !strings.Contains(err.Error(), "synset_properties_curated") {
		t.Errorf("expected error mentioning synset_properties_curated, got: %v", err)
	}
	if !strings.Contains(err.Error(), "is empty") {
		t.Errorf("expected 'is empty' in error, got: %v", err)
	}
}

// TestCascade_EmitsOutcomeSlogInfoUnconditionally pins R1-Fix-A: every
// cascade request must emit an unconditional slog.Info "cascade request
// complete" record at INFO level, independent of observe.Start's
// feature flag. Tests with timing OFF (production-like).
func TestCascade_EmitsOutcomeSlogInfoUnconditionally(t *testing.T) {
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelInfo})))
	defer slog.SetDefault(prev)

	observe.Init(false) // production posture — timing OFF
	defer observe.Init(false)

	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=10", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}

	logs := buf.String()
	if !strings.Contains(logs, `"msg":"cascade request complete"`) {
		t.Errorf("expected unconditional 'cascade request complete' slog.Info; got:\n%s", logs)
	}
	if !strings.Contains(logs, `"outcome":"scored"`) {
		t.Errorf("outcome=scored not present in log:\n%s", logs)
	}
}

// TestCascade_UnionMode_NoConcretenessErrorForEmbeddingMisses pins R1-Fix-B:
// in union mode, embedding-path candidates that lack synset_concreteness
// MUST NOT trigger the "cascade concreteness cache divergence" Error log.
// The current production DB produces ~30 such embedding misses per
// 'anger' union request; pre-fix this was 30 lines of Error spam, now
// it's a single Info attr (embedding_no_concreteness=30).
func TestCascade_UnionMode_NoConcretenessErrorForEmbeddingMisses(t *testing.T) {
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelDebug})))
	defer slog.SetDefault(prev)

	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	cfg := forge.DefaultCascadeConfig()
	cfg.Mode = forge.ModeUnion
	cfg.EmbeddingDMin = 0.0
	cfg.EmbeddingDMax = 1.5
	cfg.EmbeddingTopK = 200
	if err := h.WithCascadeConfig(cfg); err != nil {
		t.Fatalf("WithCascadeConfig: %v", err)
	}

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=200", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}

	logs := buf.String()
	if strings.Contains(logs, `"cascade concreteness cache divergence"`) {
		t.Errorf("union mode must NOT emit 'cache divergence' Error for embedding-source misses:\n%s", logs)
	}
	// Confirm the embedding miss count IS recorded as an Info attr instead.
	if !strings.Contains(logs, `"embedding_no_concreteness"`) {
		t.Errorf("expected 'embedding_no_concreteness' attr on cascade_request_total / cascade request complete log; got:\n%s", logs)
	}
}

// TestCascade_EmbeddingOnly_OmitsTierFromJSON pins D4: embedding-only
// candidates have no meaningful salience-based tier; the JSON wire
// must omit the tier field rather than emit a misleading "unlikely".
func TestCascade_EmbeddingOnly_OmitsTierFromJSON(t *testing.T) {
	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	cfg := forge.DefaultCascadeConfig()
	cfg.Mode = forge.ModeEmbedding
	cfg.EmbeddingDMin = 0.0
	cfg.EmbeddingDMax = 1.5
	cfg.EmbeddingTopK = 50
	if err := h.WithCascadeConfig(cfg); err != nil {
		t.Fatalf("WithCascadeConfig: %v", err)
	}

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=50", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}
	body := w.Body.String()
	if strings.Contains(body, `"tier":"unlikely"`) {
		t.Errorf("embedding-only response must not emit tier=unlikely (semantically wrong); body=\n%s", body)
	}
}

// TestHandleSuggest_LemmaCaseInsensitive pins the entry-boundary lowercase
// normalisation. Without it, the cluster path's exact-match SQL would
// 404 on capitalised words even when the lowercase form is enriched.
func TestHandleSuggest_LemmaCaseInsensitive(t *testing.T) {
	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	for _, word := range []string{"Anger", "ANGER", "AnGeR"} {
		t.Run(word, func(t *testing.T) {
			req := httptest.NewRequest("GET", "/forge/suggest?word="+word+"&limit=5", nil)
			w := httptest.NewRecorder()
			h.HandleSuggest(w, req)
			if w.Code != http.StatusOK {
				t.Errorf("status %d for word=%q (want 200; lowercase 'anger' resolves): %s",
					w.Code, word, w.Body.String())
			}
		})
	}
}

// TestCascadePipeline_EmbeddingPathUnavailable_AttrPresentOnCompleteLog
// pins D15: the cascadeAnomalies.embeddingPathUnavailable flag must
// flow through Attrs() → emit() onto the "cascade request complete"
// Info log on every union-mode request. We assert PRESENCE of the
// attr key here — constructing the union+cluster-success+embedding-404
// scenario requires injecting a divergent test fixture (both paths
// share the same lemmas JOIN synset_properties_curated filter against
// the real DB), which is out of scope for this canary. Presence proves
// the field flows from struct → Attrs() → emit().
func TestCascadePipeline_EmbeddingPathUnavailable_AttrPresentOnCompleteLog(t *testing.T) {
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelInfo})))
	defer slog.SetDefault(prev)

	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	cfg := forge.DefaultCascadeConfig()
	cfg.Mode = forge.ModeUnion
	cfg.EmbeddingDMin = 0.0
	cfg.EmbeddingDMax = 1.5
	cfg.EmbeddingTopK = 50
	if err := h.WithCascadeConfig(cfg); err != nil {
		t.Fatalf("WithCascadeConfig: %v", err)
	}

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=10", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}

	logs := buf.String()
	if !strings.Contains(logs, `"msg":"cascade request complete"`) {
		t.Fatalf("expected cascade request complete log; got:\n%s", logs)
	}
	if !strings.Contains(logs, `"embedding_path_unavailable":`) {
		t.Errorf("embedding_path_unavailable attr missing from emit log:\n%s", logs)
	}
}

// TestCascadePipeline_ClusterPathUnavailable_AttrPresentOnCompleteLog
// pins the OWN-3 symmetric flag for union+cluster-404+embedding-success.
// Asserts the attr key is present on every union-mode request — the
// flag value is false in the happy path; non-zero requires the same
// kind of fixture-divergence work as the D15 counterpart.
func TestCascadePipeline_ClusterPathUnavailable_AttrPresentOnCompleteLog(t *testing.T) {
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelInfo})))
	defer slog.SetDefault(prev)

	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	cfg := forge.DefaultCascadeConfig()
	cfg.Mode = forge.ModeUnion
	cfg.EmbeddingDMin = 0.0
	cfg.EmbeddingDMax = 1.5
	cfg.EmbeddingTopK = 50
	if err := h.WithCascadeConfig(cfg); err != nil {
		t.Fatalf("WithCascadeConfig: %v", err)
	}

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=10", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}

	logs := buf.String()
	if !strings.Contains(logs, `"cluster_path_unavailable":`) {
		t.Errorf("cluster_path_unavailable attr missing from emit log:\n%s", logs)
	}
}

// TestCascadePipeline_EmbeddingDimMismatches_AttrPresentOnCompleteLog
// pins D19: the cascadeAnomalies.embeddingDimMismatches counter must
// flow through Attrs() → emit() onto the cascade_request_complete
// Info log on every request. Non-zero requires injecting a wrong-dim
// or zero-norm centroid into the cache — overkill for this canary;
// presence of the attr key is sufficient to prove the wire.
func TestCascadePipeline_EmbeddingDimMismatches_AttrPresentOnCompleteLog(t *testing.T) {
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelInfo})))
	defer slog.SetDefault(prev)

	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	req := httptest.NewRequest("GET", "/forge/suggest?word=anger&limit=10", nil)
	w := httptest.NewRecorder()
	h.HandleSuggest(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status %d", w.Code)
	}
	logs := buf.String()
	if !strings.Contains(logs, `"embedding_dim_mismatches":`) {
		t.Errorf("embedding_dim_mismatches attr missing from emit log:\n%s", logs)
	}
}

// TestCascadePipeline_CloseWithoutEmit_LogsProgrammingError pins the
// defer-safety net: if a phase method returns without invoking emit()
// (a programming error), close() must fire a loud slog.Error. In
// normal flow emit() sets p.closed before close() is reached, making
// close() a no-op. We exercise the dormant branch directly here.
func TestCascadePipeline_CloseWithoutEmit_LogsProgrammingError(t *testing.T) {
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelError})))
	defer slog.SetDefault(prev)

	h, err := NewHandlerWithCascade(testDBPath, true)
	if err != nil {
		t.Fatalf("NewHandlerWithCascade: %v", err)
	}
	defer h.Close()

	p := newCascadePipeline(h, "anger", 5)
	// Deliberately skip any emit*() call — simulate a phase method
	// returning without owning emission.
	p.close()

	if !strings.Contains(buf.String(), "cascadePipeline closed without explicit emit") {
		t.Errorf("expected programming-error Error log on bare close(); got:\n%s", buf.String())
	}

	// Idempotency: a second close() must be a no-op (no second log line).
	prevLen := buf.Len()
	p.close()
	if buf.Len() != prevLen {
		t.Errorf("close() must be idempotent; second invocation wrote: %s", buf.String()[prevLen:])
	}
}
