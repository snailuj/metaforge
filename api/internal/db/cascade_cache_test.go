package db

import (
	"bytes"
	"database/sql"
	"log/slog"
	"strings"
	"testing"

	_ "github.com/mattn/go-sqlite3"
)

const testDBPath = "../../../data-pipeline/output/lexicon_v2.db"

func TestLoadCascadeCache_PopulatesBothTablesFromLiveDB(t *testing.T) {
	database, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	cache, err := LoadCascadeCache(database)
	if err != nil {
		t.Fatalf("LoadCascadeCache: %v", err)
	}

	// synset_concreteness has ~74k rows on the current DB (verified via sqlite3).
	if len(cache.Concreteness) < 70000 {
		t.Errorf("expected >=70k concreteness rows, got %d", len(cache.Concreteness))
	}
	// synset_centroids has ~36k rows.
	if len(cache.Centroids) < 35000 {
		t.Errorf("expected >=35k centroid rows, got %d", len(cache.Centroids))
	}

	// Spot-check known row (synset 76737, score 4.88 from brysbaert).
	if score, ok := cache.Concreteness["76737"]; !ok {
		t.Error("expected synset 76737 in concreteness cache")
	} else if score < 4.87 || score > 4.89 {
		t.Errorf("synset 76737: want ~4.88, got %v", score)
	}

	// Spot-check known centroid (synset 12933, 300-dim float32).
	if vec, ok := cache.Centroids["12933"]; !ok {
		t.Error("expected synset 12933 in centroid cache")
	} else if len(vec) != 300 {
		t.Errorf("synset 12933 centroid: want 300-dim, got %d", len(vec))
	}
}

func TestLoadCascadeCache_MissingTablesFailLoud(t *testing.T) {
	// The production handler pre-flights that synset_concreteness +
	// synset_centroids exist before calling LoadCascadeCache, so a
	// missing table at load time means something raced or corrupted.
	// Fail loud rather than silently producing an empty cache that
	// would route every cascade pair to missing_concreteness.
	database, err := openMemoryDB(t)
	if err != nil {
		t.Fatalf("openMemoryDB: %v", err)
	}
	defer database.Close()

	_, err = LoadCascadeCache(database)
	if err == nil {
		t.Fatal("expected error for missing cascade tables, got nil")
	}
	if !strings.Contains(err.Error(), "no such table") {
		t.Errorf("expected 'no such table' in error, got: %v", err)
	}
}

func TestLoadCascadeCache_MalformedAndZeroBlobCentroidsExcluded(t *testing.T) {
	// OF1 round-3 fix + OF1-R4 round-4 TDD closure: a zero-byte or
	// wrong-dimension centroid BLOB is a pipeline contract violation.
	// The loader logs Error + increments a counter + excludes the
	// synset from the cache so downstream cascade scoring fails open
	// through 'no centroid' rather than scoring on garbage.
	//
	// Live-DB tests can't easily exercise this path; in-memory SQLite
	// with hand-inserted bad rows is the right shape.
	database, err := openMemoryDB(t)
	if err != nil {
		t.Fatalf("openMemoryDB: %v", err)
	}
	defer database.Close()

	setup := []string{
		`CREATE TABLE synset_concreteness (synset_id TEXT PRIMARY KEY, score REAL, source TEXT)`,
		`CREATE TABLE synset_centroids (synset_id TEXT PRIMARY KEY, centroid BLOB, property_count INTEGER)`,
		// One zero-byte BLOB row.
		`INSERT INTO synset_centroids VALUES ('zero-blob-synset', X'', 0)`,
		// One wrong-dimension BLOB row (4 bytes instead of 1200).
		`INSERT INTO synset_centroids VALUES ('wrong-dim-synset', X'01020304', 1)`,
		// vocab_clusters needs to exist for LoadCascadeCache (M05 S02).
		// Empty table is fine — the loader handles zero rows gracefully.
		`CREATE TABLE vocab_clusters (cluster_id INTEGER, vocab_id INTEGER, dominant_type TEXT)`,
	}
	for _, stmt := range setup {
		if _, err := database.Exec(stmt); err != nil {
			t.Fatalf("setup stmt %q: %v", stmt, err)
		}
	}

	cache, err := LoadCascadeCache(database)
	if err != nil {
		t.Fatalf("LoadCascadeCache: %v", err)
	}
	if _, ok := cache.Centroids["zero-blob-synset"]; ok {
		t.Error("zero-blob row must be excluded from cache (OF1 round-3 fix)")
	}
	if _, ok := cache.Centroids["wrong-dim-synset"]; ok {
		t.Error("wrong-dimension row must be excluded from cache (round-1 malformed-blob fix)")
	}
}

func openMemoryDB(t *testing.T) (*sql.DB, error) {
	t.Helper()
	return sql.Open("sqlite3", ":memory:")
}

func TestLoadClusterTypes_PopulatesMapWithCanonicalTypesAndEmptyForNull(t *testing.T) {
	// M05 S02: vocab_clusters.dominant_type is the per-cluster mode
	// over property types (sensorimotor / behaviour / functional /
	// effect / emotional / social / other) populated by snap. NULL
	// values must come back as empty string so the scorer can treat
	// "unknown type" uniformly.
	database, err := openMemoryDB(t)
	if err != nil {
		t.Fatalf("openMemoryDB: %v", err)
	}
	defer database.Close()

	setup := []string{
		`CREATE TABLE vocab_clusters (cluster_id INTEGER, vocab_id INTEGER, dominant_type TEXT)`,
		// Two rows for cluster 1 (mirrors live shape — vocab_clusters
		// repeats cluster_id per vocab member; dominant_type repeats).
		`INSERT INTO vocab_clusters VALUES (1, 100, 'sensorimotor')`,
		`INSERT INTO vocab_clusters VALUES (1, 101, 'sensorimotor')`,
		`INSERT INTO vocab_clusters VALUES (2, 200, 'behaviour')`,
		`INSERT INTO vocab_clusters VALUES (3, 300, NULL)`,
	}
	for _, stmt := range setup {
		if _, err := database.Exec(stmt); err != nil {
			t.Fatalf("setup stmt %q: %v", stmt, err)
		}
	}

	dst := make(map[int64]string, 4)
	if err := loadClusterTypes(database, dst); err != nil {
		t.Fatalf("loadClusterTypes: %v", err)
	}

	if got := dst[1]; got != "sensorimotor" {
		t.Errorf("cluster 1: want %q, got %q", "sensorimotor", got)
	}
	if got := dst[2]; got != "behaviour" {
		t.Errorf("cluster 2: want %q, got %q", "behaviour", got)
	}
	// NULL row must come back as empty string sentinel.
	got, ok := dst[3]
	if !ok {
		t.Error("cluster 3 (NULL) should be present with empty string value")
	}
	if got != "" {
		t.Errorf("cluster 3: want empty string (NULL sentinel), got %q", got)
	}
}

func TestLoadClusterTypes_LogsDivergenceWarning(t *testing.T) {
	// Defensive tripwire: a pipeline bug that wrote diverging
	// dominant_type values for two rows of the same cluster_id would
	// otherwise be silently absorbed by last-write-wins on the map.
	// loadClusterTypes must log a slog.Warn the first time it observes
	// a non-empty existing value that differs from the incoming one.
	database, err := openMemoryDB(t)
	if err != nil {
		t.Fatalf("openMemoryDB: %v", err)
	}
	defer database.Close()

	setup := []string{
		`CREATE TABLE synset_concreteness (synset_id TEXT PRIMARY KEY, score REAL, source TEXT)`,
		`CREATE TABLE synset_centroids (synset_id TEXT PRIMARY KEY, centroid BLOB, property_count INTEGER)`,
		`CREATE TABLE vocab_clusters (cluster_id INTEGER, vocab_id INTEGER, dominant_type TEXT)`,
		// Two rows for cluster 1 with diverging non-NULL dominant_type
		// — a pipeline contract violation that the loader must surface.
		`INSERT INTO vocab_clusters VALUES (1, 100, 'sensorimotor')`,
		`INSERT INTO vocab_clusters VALUES (1, 101, 'behaviour')`,
	}
	for _, stmt := range setup {
		if _, err := database.Exec(stmt); err != nil {
			t.Fatalf("setup stmt %q: %v", stmt, err)
		}
	}

	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelWarn})))
	defer slog.SetDefault(prev)

	if _, err := LoadCascadeCache(database); err != nil {
		t.Fatalf("LoadCascadeCache: %v", err)
	}

	logs := buf.String()
	if !strings.Contains(logs, "vocab_clusters.dominant_type divergence") {
		t.Errorf("expected slog.Warn about dominant_type divergence; got:\n%s", logs)
	}
	if !strings.Contains(logs, `"level":"WARN"`) {
		t.Errorf("expected WARN level; got:\n%s", logs)
	}
}

func TestLoadCascadeCache_AllNullDominantType_LogsWarn(t *testing.T) {
	// M05 S02 readiness tripwire: if every vocab_clusters row has
	// NULL dominant_type, the pipeline hasn't been re-run since the
	// S01 snap change. Log a single slog.Warn at startup so the
	// missing-state is visible — does NOT block startup (cascade
	// remains serviceable; type-diversity bonus simply degrades).
	database, err := openMemoryDB(t)
	if err != nil {
		t.Fatalf("openMemoryDB: %v", err)
	}
	defer database.Close()

	setup := []string{
		`CREATE TABLE synset_concreteness (synset_id TEXT PRIMARY KEY, score REAL, source TEXT)`,
		`INSERT INTO synset_concreteness VALUES ('s-1', 3.0, 'test')`,
		`CREATE TABLE synset_centroids (synset_id TEXT PRIMARY KEY, centroid BLOB, property_count INTEGER)`,
		`CREATE TABLE vocab_clusters (cluster_id INTEGER, vocab_id INTEGER, dominant_type TEXT)`,
		`INSERT INTO vocab_clusters VALUES (1, 100, NULL)`,
		`INSERT INTO vocab_clusters VALUES (2, 200, NULL)`,
	}
	for _, stmt := range setup {
		if _, err := database.Exec(stmt); err != nil {
			t.Fatalf("setup stmt %q: %v", stmt, err)
		}
	}

	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelWarn})))
	defer slog.SetDefault(prev)

	if _, err := LoadCascadeCache(database); err != nil {
		t.Fatalf("LoadCascadeCache: %v", err)
	}

	logs := buf.String()
	if !strings.Contains(logs, "vocab_clusters loaded but dominant_type is NULL") {
		t.Errorf("expected slog.Warn about all-NULL dominant_type; got:\n%s", logs)
	}
	if !strings.Contains(logs, `"level":"WARN"`) {
		t.Errorf("expected WARN level; got:\n%s", logs)
	}
}
