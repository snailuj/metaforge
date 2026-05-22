package db

import (
	"database/sql"
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
