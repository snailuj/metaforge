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
// pass each. The production handler pre-flights that the cascade tables
// exist before calling this; if the loader reaches an underlying table
// and it is missing or unreadable, the error propagates so a race or
// corruption surfaces loudly rather than silently producing an empty
// cache that routes every cascade pair to missing_concreteness.
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
		return fmt.Errorf("load concreteness: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var id string
		var score float64
		if err := rows.Scan(&id, &score); err != nil {
			// Homogeneous result set — first scan failure means rows 2..N
			// will fail for the same structural reason (schema drift,
			// type mismatch). Escalate rather than log-and-continue.
			return fmt.Errorf("scan concreteness row: %w", err)
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
		return fmt.Errorf("load centroids: %w", err)
	}
	defer rows.Close()

	var malformed int
	for rows.Next() {
		var id string
		var blob []byte
		if err := rows.Scan(&id, &blob); err != nil {
			// Same rationale as concreteness — first scan failure is
			// structural, escalate.
			return fmt.Errorf("scan centroid row: %w", err)
		}
		if len(blob) == 0 {
			continue
		}
		vec := blobconv.BlobToFloats(blob)
		if vec == nil {
			// Malformed BLOB — not a missing row, a pipeline contract
			// violation (wrong dimension, partial write, etc). Log at
			// Error so operators see the signal; track a counter so the
			// load summary can report aggregate damage.
			slog.Error("centroid blob malformed", "synset", id, "bytes", len(blob))
			malformed++
			continue
		}
		dst[id] = vec
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("iterate centroids: %w", err)
	}
	if malformed > 0 {
		slog.Error("cascade centroid load completed with malformed rows",
			"malformed_count", malformed,
			"loaded_count", len(dst),
		)
	}
	return nil
}
