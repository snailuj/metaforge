// Cascade-specific DB helpers consumed by the M03 cascade scorer in
// api/internal/forge.
package db

import (
	"database/sql"
	"fmt"
	"log/slog"
	"strings"
)

// GetSynsetClusterPropertiesBatch returns the curated-vocab cluster_id →
// salience_sum map for each requested synset, in one IN-clause query.
// Synsets with no curated properties are absent from the result map.
// Empty input returns an empty (non-nil) map with no error.
func GetSynsetClusterPropertiesBatch(database *sql.DB, synsetIDs []string) (map[string]map[int64]float64, error) {
	out := make(map[string]map[int64]float64, len(synsetIDs))
	if len(synsetIDs) == 0 {
		return out, nil
	}

	placeholders := make([]string, len(synsetIDs))
	args := make([]interface{}, len(synsetIDs))
	for i, id := range synsetIDs {
		placeholders[i] = "?"
		args[i] = id
	}
	query := "SELECT synset_id, cluster_id, salience_sum FROM synset_properties_curated WHERE synset_id IN (" +
		strings.Join(placeholders, ",") + ")"

	rows, err := database.Query(query, args...)
	if err != nil {
		return nil, fmt.Errorf("GetSynsetClusterPropertiesBatch query: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var id string
		var cid int64
		var sal float64
		if err := rows.Scan(&id, &cid, &sal); err != nil {
			slog.Warn("scan cluster prop batch row failed", "err", err)
			continue
		}
		props, ok := out[id]
		if !ok {
			props = make(map[int64]float64)
			out[id] = props
		}
		props[cid] = sal
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("GetSynsetClusterPropertiesBatch iterate: %w", err)
	}
	return out, nil
}
