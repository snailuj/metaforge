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

func openMemoryDB(t *testing.T) (*sql.DB, error) {
	t.Helper()
	return sql.Open("sqlite3", ":memory:")
}
