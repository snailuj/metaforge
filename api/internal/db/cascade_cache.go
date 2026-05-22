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
	"github.com/snailuj/metaforge/internal/observe"
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
	stopTotal := observe.Start("cascade_cache_load_total")
	cache := &CascadeCache{
		Concreteness: make(map[string]float64, 80000),
		Centroids:    make(map[string][]float32, 40000),
	}

	stopConc := observe.Start("cascade_cache_load_concreteness")
	if err := loadConcreteness(database, cache.Concreteness); err != nil {
		stopConc("rows", len(cache.Concreteness), "err", err.Error())
		stopTotal("phase", "concreteness", "err", err.Error())
		return nil, err
	}
	stopConc("rows", len(cache.Concreteness))

	stopCent := observe.Start("cascade_cache_load_centroids")
	if err := loadCentroids(database, cache.Centroids); err != nil {
		stopCent("rows", len(cache.Centroids), "err", err.Error())
		stopTotal("phase", "centroids", "err", err.Error())
		return nil, err
	}
	stopCent("rows", len(cache.Centroids))

	stopTotal("concreteness_rows", len(cache.Concreteness), "centroid_rows", len(cache.Centroids))
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
			// Zero-byte BLOB — pipeline contract violation
			// (synset_centroids.centroid is NOT NULL non-empty by
			// convention). Counted under the same `malformed` umbrella
			// as the dim-mismatch branch below so the load summary
			// reports total damage.
			slog.Error("centroid blob empty", "synset", id)
			malformed++
			continue
		}
		vec := blobconv.BlobToFloats(blob)
		if vec == nil {
			// Wrong-dimension BLOB — pipeline contract violation
			// (partial write, dimension drift). Zero-byte is already
			// short-circuited above; this branch covers dim-mismatch
			// only. Log at Error so operators see the signal and
			// tally a counter for the aggregate load summary below.
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
