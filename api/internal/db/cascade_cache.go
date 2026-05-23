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
	// ClusterTypes maps cluster_id → canonical dominant type string
	// (sensorimotor, behaviour, functional, effect, emotional, social,
	// other) populated by snap_properties.py on the M05 schema. Empty
	// string means dominant_type IS NULL for that cluster — either a
	// pre-M05 DB or an empty cluster. The scorer treats "unknown type"
	// identically across both cases. Lifecycle mirrors Concreteness /
	// Centroids: loaded once at handler startup, read-only thereafter.
	ClusterTypes map[int64]string
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
		// Cluster count on the live DB sits in the same band as the
		// centroid count (~35-50k vocab_clusters rows feeding the same
		// cluster space). Size the map to match Centroids so the
		// per-row writes in loadClusterTypes don't trigger repeated
		// rehashes on snap-with-types runs.
		ClusterTypes: make(map[int64]string, 40000),
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

	stopTypes := observe.Start("cascade_cache_load_cluster_types")
	if err := loadClusterTypes(database, cache.ClusterTypes); err != nil {
		stopTypes("rows", len(cache.ClusterTypes), "err", err.Error())
		stopTotal("phase", "cluster_types", "err", err.Error())
		return nil, err
	}
	stopTypes("rows", len(cache.ClusterTypes))

	// Surface M05 pipeline readiness: if vocab_clusters loaded but every
	// dominant_type is NULL, the data pipeline hasn't been re-run since
	// the M05 S01 snap_properties.py change. Non-blocking — the cascade
	// remains serviceable; the type-diversity bonus simply degrades to
	// the M03/M04 scoring math. Per-cluster ratio also logged so an
	// operator can spot partial coverage.
	typedClusters := 0
	for _, t := range cache.ClusterTypes {
		if t != "" {
			typedClusters++
		}
	}
	if len(cache.ClusterTypes) > 0 && typedClusters == 0 {
		slog.Warn("cascade cache: vocab_clusters loaded but dominant_type is NULL for every row — pipeline needs snap_properties.py re-run for M05 type-aware scoring",
			"cluster_rows", len(cache.ClusterTypes))
	} else if len(cache.ClusterTypes) > 0 {
		slog.Info("cascade cache: cluster types loaded",
			"cluster_rows", len(cache.ClusterTypes),
			"typed_clusters", typedClusters,
			"untyped_pct", float64(len(cache.ClusterTypes)-typedClusters)/float64(len(cache.ClusterTypes))*100)
	}

	stopTotal("concreteness_rows", len(cache.Concreteness),
		"centroid_rows", len(cache.Centroids),
		"cluster_type_rows", len(cache.ClusterTypes))
	slog.Info("cascade cache loaded",
		"concreteness_rows", len(cache.Concreteness),
		"centroid_rows", len(cache.Centroids),
		"cluster_type_rows", len(cache.ClusterTypes),
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

// loadClusterTypes populates dst with cluster_id → dominant_type for the
// M05 type-diversity bonus (consumed by EvaluateCascadePair in S03).
//
// vocab_clusters has one row per vocab_id (PK is vocab_id); cluster_id
// is non-unique (~5-7 vocab_ids per cluster on average), so the
// (cluster_id, dominant_type) projection writes the same tuple once per
// cluster member. Idempotent by construction — snap_properties.py
// writes one dominant_type per cluster via an UPDATE, so every row for
// the same cluster carries the same dominant_type. SELECT DISTINCT
// would save a few map writes but obscures the contract; the simpler
// form wins.
//
// dominant_type is nullable for pre-M05 DBs and for empty clusters.
// Store the canonical zero value ("") in both cases so the scorer can
// treat "unknown type" identically.
func loadClusterTypes(database *sql.DB, dst map[int64]string) error {
	rows, err := database.Query("SELECT cluster_id, dominant_type FROM vocab_clusters")
	if err != nil {
		return fmt.Errorf("load cluster types: %w", err)
	}
	defer rows.Close()

	// Bounded divergence reporting: a pathological pipeline bug could
	// emit divergence on every row (~35k+ on the live DB). Cap the
	// per-row Warn at maxWarns and emit a single summary Error at the
	// end so observability survives the flood without losing the signal.
	const maxWarns = 10
	divergences := 0
	for rows.Next() {
		var id int64
		var dt sql.NullString
		if err := rows.Scan(&id, &dt); err != nil {
			// Same rationale as concreteness — first scan failure is
			// structural, escalate.
			return fmt.Errorf("scan cluster type row: %w", err)
		}
		// Defensive divergence check: snap_properties.py writes one
		// dominant_type per cluster, so every row for the same cluster
		// must carry the same canonical value (including "all NULL").
		// Any disagreement is a pipeline contract violation that
		// last-write-wins would silently absorb. Canonicalise the
		// NullString to an incoming string and resolve the three
		// divergence cases explicitly so the recovery policy is
		// deterministic across SQL row order:
		//   A) real → NULL: keep existing (prefer-non-empty).
		//   B) NULL → real: overwrite "" with real value (prefer-non-empty).
		//   C) non-empty disagreement: keep first-seen (first-write-wins).
		// All three increment the divergence counter so the flood-limit
		// summary covers them uniformly.
		incoming := ""
		if dt.Valid {
			incoming = dt.String
		}
		if existing, ok := dst[id]; ok && existing != incoming {
			divergences++
			if divergences <= maxWarns {
				slog.Warn("cascade cache: vocab_clusters.dominant_type divergence within cluster",
					"cluster_id", id, "first_seen", existing, "new", incoming)
			}
			if incoming == "" {
				// Case A: real → NULL. Keep existing.
				continue
			}
			if existing != "" {
				// Case C: non-empty disagreement. Keep first-seen so
				// the cache is deterministic across SQL row order —
				// cascade scoring must not flip between re-runs.
				continue
			}
			// Case B: existing == "", incoming non-empty. Fall through
			// to overwrite the empty sentinel with the real value.
		}
		dst[id] = incoming
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("iterate cluster types: %w", err)
	}
	// Any non-zero divergence is a pipeline contract violation — snap
	// writes one dominant_type per cluster, so disagreement within a
	// cluster means data is wrong somewhere. Always emit a summary Error
	// so operators alerting on Error level catch the signal regardless
	// of whether the flood cap fired. Carry warns_emitted + suppressed
	// only when the tail was actually suppressed; below the cap every
	// divergence already has its own Warn line.
	if divergences > maxWarns {
		slog.Error("cascade cache: vocab_clusters.dominant_type divergence flood — pipeline contract broken",
			"total_divergences", divergences,
			"warns_emitted", maxWarns,
			"suppressed", divergences-maxWarns)
	} else if divergences > 0 {
		slog.Error("cascade cache: vocab_clusters.dominant_type divergence — pipeline contract broken",
			"total_divergences", divergences)
	}
	return nil
}
