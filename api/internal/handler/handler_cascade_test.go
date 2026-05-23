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
// reach the cascade scorer as candidates when SourcesUnion is active.
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
	cfg.CandidateSources = forge.SourcesUnion
	cfg.EmbeddingDMin = 0.0
	cfg.EmbeddingDMax = 1.5
	// TopK pinned wide for the canary: this test asserts CANDIDATE
	// PRESENCE, not production ranking. Diagnostics show "hammer" lands at
	// rank ~4600 by cosine distance from "truth", "money" at ~2000 from
	// "time" — both within band but well outside production TopK=100.
	// Widening here is intentional and isolated to this test.
	cfg.EmbeddingTopK = 10000
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
// CandidateSources=cluster_only behaves byte-for-byte identically to
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
	cfg.CandidateSources = forge.SourcesCluster
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
	cfg.CandidateSources = forge.SourcesEmbedding
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
	cfg.CandidateSources = forge.SourcesUnion
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
