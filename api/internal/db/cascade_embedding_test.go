package db

import (
	"bytes"
	"database/sql"
	"errors"
	"log/slog"
	"strings"
	"testing"

	"github.com/snailuj/metaforge/internal/forge"

	_ "github.com/mattn/go-sqlite3"
)

// vec returns a length-300 float32 vector with the supplied prefix and
// the remainder zero-padded — just enough for cosine math to behave.
func vec(prefix ...float32) []float32 {
	v := make([]float32, 300)
	copy(v, prefix)
	return v
}

func TestScanEmbeddingBand_FiltersOutsideBand(t *testing.T) {
	cache := &CascadeCache{
		Centroids: map[string][]float32{
			"topic":     vec(1, 0, 0), // d=0 to itself
			"near":      vec(1, 0, 0), // d≈0 — below dMin
			"in_band_a": vec(0.5, 0.5, 0),
			"in_band_b": vec(0.0, 1.0, 0),
			"far":       vec(-1, 0, 0), // d=2 — above dMax
		},
	}
	topic := cache.Centroids["topic"]
	siblings := map[string]struct{}{"topic": {}}
	hits, _ := scanEmbeddingBand(cache, topic, siblings, 0.2, 1.5, 10)
	got := map[string]bool{}
	for _, h := range hits {
		got[h.synsetID] = true
	}
	if got["topic"] || got["near"] || got["far"] {
		t.Errorf("identity/below-dMin/above-dMax must be excluded; got %v", got)
	}
	if !got["in_band_a"] || !got["in_band_b"] {
		t.Errorf("in-band entries missing; got %v", got)
	}
}

func TestScanEmbeddingBand_ExcludesAllSiblingSenses(t *testing.T) {
	cache := &CascadeCache{
		Centroids: map[string][]float32{
			"topic-sense-a":  vec(1, 0, 0),
			"topic-sense-b":  vec(0.9, 0.1, 0), // also a sense of the topic lemma
			"topic-sense-c":  vec(0.7, 0.3, 0), // also a sense
			"unrelated-near": vec(0.6, 0.4, 0),
		},
	}
	topic := cache.Centroids["topic-sense-a"]
	siblings := map[string]struct{}{
		"topic-sense-a": {},
		"topic-sense-b": {},
		"topic-sense-c": {},
	}
	hits, _ := scanEmbeddingBand(cache, topic, siblings, 0.0, 1.5, 10)
	got := map[string]bool{}
	for _, h := range hits {
		got[h.synsetID] = true
	}
	if got["topic-sense-a"] || got["topic-sense-b"] || got["topic-sense-c"] {
		t.Errorf("all sibling senses must be excluded; got %v", got)
	}
	if !got["unrelated-near"] {
		t.Errorf("unrelated in-band candidate must be present; got %v", got)
	}
}

func TestScanEmbeddingBand_CapsAtTopK(t *testing.T) {
	cache := &CascadeCache{Centroids: map[string][]float32{}}
	cache.Centroids["topic"] = vec(1, 0, 0)
	for i := 0; i < 50; i++ {
		// All 50 will be in [0.2, 1.5] band by construction.
		cache.Centroids[idForI(i)] = vec(0.5, 0.5, 0)
	}
	topic := cache.Centroids["topic"]
	siblings := map[string]struct{}{"topic": {}}
	hits, _ := scanEmbeddingBand(cache, topic, siblings, 0.2, 1.5, 7)
	if len(hits) != 7 {
		t.Errorf("want 7 hits (topK), got %d", len(hits))
	}
}

func TestScanEmbeddingBand_NoTopicCentroidReturnsNil(t *testing.T) {
	cache := &CascadeCache{Centroids: map[string][]float32{"other": vec(1, 0, 0)}}
	hits, skipped := scanEmbeddingBand(cache, nil, map[string]struct{}{}, 0.0, 2.0, 10)
	if hits != nil {
		t.Errorf("missing topic centroid: want nil, got %v", hits)
	}
	if skipped != 0 {
		t.Errorf("missing topic centroid: want 0 skipped, got %d", skipped)
	}
}

func idForI(i int) string {
	return "c-" + string(rune('a'+i%26)) + string(rune('a'+(i/26)%26))
}

func TestGetForgeCascadeCandidatesByEmbedding_AnchorPairsSurface(t *testing.T) {
	database, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	cache, err := LoadCascadeCache(database)
	if err != nil {
		t.Fatalf("LoadCascadeCache: %v", err)
	}

	cfg := ForgeEmbeddingConfig{DMin: 0.0, DMax: 1.5, TopK: 200}
	got, _, err := GetForgeCascadeCandidatesByEmbedding(database, cache, "anger", cfg)
	if err != nil {
		t.Fatalf("GetForgeCascadeCandidatesByEmbedding: %v", err)
	}
	if len(got) == 0 {
		t.Fatal("expected non-empty embedding candidates for 'anger'")
	}
	for _, c := range got {
		if c.Source != forge.SourceEmbedding {
			t.Errorf("candidate %s: Source=%q want %q", c.SynsetID, c.Source, forge.SourceEmbedding)
		}
		if c.SalienceSum != 0 || c.ContrastCount != 0 {
			t.Errorf("embedding candidate %s: salience/contrast must be zero on this path, got %v/%d",
				c.SynsetID, c.SalienceSum, c.ContrastCount)
		}
		if c.SourceSynsetID == "" || c.Definition == "" || c.POS == "" {
			t.Errorf("candidate %s missing source/definition/pos: %+v", c.SynsetID, c)
		}
	}
}

func TestGetForgeCascadeCandidatesByEmbedding_UnknownLemmaReturnsErrLemmaNotFound(t *testing.T) {
	database, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	cache, err := LoadCascadeCache(database)
	if err != nil {
		t.Fatalf("LoadCascadeCache: %v", err)
	}

	cfg := ForgeEmbeddingConfig{DMin: 0.0, DMax: 1.5, TopK: 10}
	_, _, err = GetForgeCascadeCandidatesByEmbedding(database, cache, "zzznotarealword", cfg)
	if err == nil {
		t.Fatal("want ErrLemmaNotFound for unknown lemma, got nil")
	}
	if !errors.Is(err, ErrLemmaNotFound) {
		t.Fatalf("want ErrLemmaNotFound, got %v", err)
	}
}

// TestResolveLemmaSiblingSynsets_EmptyResult_LogsError pins D20/D22:
// when the lemmas table is empty (or has no rows for the requested
// lemma) yet the caller has already resolved a primary synset, that is
// a cross-row DB invariant break — the function must NOT swallow it
// silently. The function returns an empty map (caller has a nil-safe
// downstream path) but also fires a loud slog.Error.
func TestResolveLemmaSiblingSynsets_EmptyResult_LogsError(t *testing.T) {
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelError})))
	defer slog.SetDefault(prev)

	tmp := t.TempDir() + "/sib.db"
	database, err := sql.Open("sqlite3", tmp)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()
	if _, err := database.Exec(`CREATE TABLE lemmas (synset_id TEXT, lemma TEXT)`); err != nil {
		t.Fatalf("CREATE: %v", err)
	}

	out, err := resolveLemmaSiblingSynsets(database, "nonexistent")
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if len(out) != 0 {
		t.Errorf("want empty map, got %v", out)
	}
	if !strings.Contains(buf.String(), "resolveLemmaSiblingSynsets empty after primary resolved") {
		t.Errorf("expected DB invariant break Error log; got:\n%s", buf.String())
	}
}
