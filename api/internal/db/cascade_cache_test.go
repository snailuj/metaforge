package db

import (
	"database/sql"
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

func TestLoadCascadeCache_MissingTablesFailOpen(t *testing.T) {
	// In-memory DB has neither table -> cache loads empty, no error.
	// Fixture-DB safety net so handler tests against synthetic DBs don't
	// have to provide every cascade table.
	database, err := openMemoryDB(t)
	if err != nil {
		t.Fatalf("openMemoryDB: %v", err)
	}
	defer database.Close()

	cache, err := LoadCascadeCache(database)
	if err != nil {
		t.Fatalf("LoadCascadeCache on empty DB returned error: %v", err)
	}
	if len(cache.Concreteness) != 0 || len(cache.Centroids) != 0 {
		t.Errorf("empty DB should produce empty caches, got %d / %d",
			len(cache.Concreteness), len(cache.Centroids))
	}
}

func openMemoryDB(t *testing.T) (*sql.DB, error) {
	t.Helper()
	return sql.Open("sqlite3", ":memory:")
}
