// In-memory cache of the static cascade lookup tables.
//
// synset_concreteness and synset_centroids are immutable across the
// lifetime of an API process — they're written by the data pipeline and
// only read by the API. Pulling them into memory at startup eliminates
// the per-candidate DB round-trips that would otherwise dominate
// /forge/suggest latency under the cascade path.
package db

import (
	"database/sql"
	"fmt"
	"log/slog"
	"strings"

	"github.com/snailuj/metaforge/internal/blobconv"
)

// CascadeCache holds the per-synset concreteness scores and centroid
// vectors for fast in-memory lookup during cascade scoring. Construct
// via LoadCascadeCache; the maps themselves are exposed read-only by
// convention.
type CascadeCache struct {
	Concreteness map[string]float64
	Centroids    map[string][]float32
}

// LoadCascadeCache reads both static cascade tables into memory in one
// pass each. Missing tables fail open (empty maps, nil error) so fixture
// DBs without the cascade pipeline can still construct a handler.
func LoadCascadeCache(database *sql.DB) (*CascadeCache, error) {
	cache := &CascadeCache{
		Concreteness: make(map[string]float64, 80000),
		Centroids:    make(map[string][]float32, 40000),
	}

	if err := loadConcreteness(database, cache.Concreteness); err != nil {
		return nil, err
	}
	if err := loadCentroids(database, cache.Centroids); err != nil {
		return nil, err
	}

	slog.Info("cascade cache loaded",
		"concreteness_rows", len(cache.Concreteness),
		"centroid_rows", len(cache.Centroids),
	)
	return cache, nil
}

func loadConcreteness(database *sql.DB, dst map[string]float64) error {
	rows, err := database.Query("SELECT synset_id, score FROM synset_concreteness")
	if err != nil {
		if strings.Contains(err.Error(), "no such table") {
			return nil
		}
		return fmt.Errorf("load concreteness: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var id string
		var score float64
		if err := rows.Scan(&id, &score); err != nil {
			slog.Warn("scan concreteness row failed", "err", err)
			continue
		}
		dst[id] = score
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("iterate concreteness: %w", err)
	}
	return nil
}

func loadCentroids(database *sql.DB, dst map[string][]float32) error {
	rows, err := database.Query("SELECT synset_id, centroid FROM synset_centroids")
	if err != nil {
		if strings.Contains(err.Error(), "no such table") {
			return nil
		}
		return fmt.Errorf("load centroids: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var id string
		var blob []byte
		if err := rows.Scan(&id, &blob); err != nil {
			slog.Warn("scan centroid row failed", "err", err)
			continue
		}
		if len(blob) == 0 {
			continue
		}
		vec := blobconv.BlobToFloats(blob)
		if vec == nil {
			// Dim mismatch — log and skip. The cache's job is to mirror what
			// the DB has; a malformed row is a pipeline-side issue.
			slog.Warn("centroid blob malformed, skipping", "synset", id, "bytes", len(blob))
			continue
		}
		dst[id] = vec
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("iterate centroids: %w", err)
	}
	return nil
}
