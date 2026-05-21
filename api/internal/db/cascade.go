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

// CascadeCandidate is one gate-passed candidate row, populated by
// GetForgeCascadeCandidatesByLemma. Mirrors CuratedMatch but extends with
// the topic / vehicle concreteness scores already known from the
// CTE-side join (saves the handler from re-querying the cache for them).
type CascadeCandidate struct {
	SynsetID            string
	Word                string
	POS                 string
	Definition          string
	SalienceSum         float64
	ContrastCount       int
	SharedProps         []string
	SourceSynsetID      string
	SourceDefinition    string
	SourcePOS           string
	TopicConcreteness   float64
	VehicleConcreteness float64
}

// GetForgeCascadeCandidatesByLemma extends the curated-by-lemma CTE with a
// concreteness join that filters out gate-rejected candidates SQL-side.
// Only candidates with (vehicle_score − topic_score) ≥ threshold reach Go.
//
// The structural query shape is identical to GetForgeMatchesCuratedByLemma
// — same best-sense selection, same antonym counting — with two new JOINs
// against synset_concreteness and one WHERE clause. Candidates with missing
// concreteness on either side are excluded (INNER JOIN) because the
// cascade would route them to missing_concreteness anyway.
//
// Returns ErrLemmaNotFound when the lemma has no curated properties at all
// (same contract as GetForgeMatchesCuratedByLemma). An empty result with
// nil error means the lemma is enriched but no candidate passes the gate.
func GetForgeCascadeCandidatesByLemma(
	database *sql.DB, lemma string, threshold float64, limit int,
) ([]CascadeCandidate, error) {
	rows, err := database.Query(`
		WITH source_synsets AS (
			SELECT l.synset_id
			FROM lemmas l
			JOIN synset_properties_curated spc ON spc.synset_id = l.synset_id
			WHERE l.lemma = ?
			GROUP BY l.synset_id
		),
		per_sense_shared AS (
			SELECT ss.synset_id as source_id,
			       tgt.synset_id as target_id,
			       SUM(tgt.salience_sum) as salience_sum,
			       GROUP_CONCAT(pvc.lemma) as shared_props
			FROM source_synsets ss
			JOIN synset_properties_curated src ON src.synset_id = ss.synset_id
			JOIN synset_properties_curated tgt ON tgt.cluster_id = src.cluster_id
			JOIN property_vocab_curated pvc ON pvc.vocab_id = src.cluster_id
			WHERE tgt.synset_id NOT IN (SELECT synset_id FROM source_synsets)
			GROUP BY ss.synset_id, tgt.synset_id
		),
		shared_gated AS (
			-- Concreteness gate pushed in here so the window function below
			-- operates only on already-gated rows. Filtering after best_sense
			-- defeats SQLite's predicate pushdown and turns this query
			-- catastrophic (~200s vs ~1s on a typical lemma).
			SELECT pss.source_id, pss.target_id, pss.salience_sum, pss.shared_props,
			       sct.score AS topic_score, scv.score AS vehicle_score
			FROM per_sense_shared pss
			JOIN synset_concreteness sct ON sct.synset_id = pss.source_id
			JOIN synset_concreteness scv ON scv.synset_id = pss.target_id
			WHERE (scv.score - sct.score) >= ?
		),
		best_sense AS (
			SELECT source_id, target_id, salience_sum, shared_props,
			       topic_score, vehicle_score,
			       ROW_NUMBER() OVER (PARTITION BY target_id ORDER BY salience_sum DESC) as rn
			FROM shared_gated
		),
		per_sense_contrast AS (
			SELECT ss.synset_id as source_id,
			       tgt.synset_id as target_id,
			       COUNT(*) as contrast_count
			FROM source_synsets ss
			JOIN synset_properties_curated src ON src.synset_id = ss.synset_id
			JOIN cluster_antonyms ca ON ca.cluster_id_a = src.cluster_id
			JOIN synset_properties_curated tgt ON tgt.cluster_id = ca.cluster_id_b
			WHERE tgt.synset_id NOT IN (SELECT synset_id FROM source_synsets)
			GROUP BY ss.synset_id, tgt.synset_id
		),
		best_contrast AS (
			SELECT source_id, target_id, contrast_count,
			       ROW_NUMBER() OVER (PARTITION BY target_id ORDER BY contrast_count DESC) as rn
			FROM per_sense_contrast
		)
		SELECT bs.target_id,
		       ts.pos, ts.definition,
		       l.lemma,
		       bs.salience_sum,
		       COALESCE(bc.contrast_count, 0) as contrast_count,
		       bs.shared_props,
		       bs.source_id,
		       ss.definition as source_definition,
		       ss.pos as source_pos,
		       bs.topic_score,
		       bs.vehicle_score
		FROM best_sense bs
		JOIN synsets ts ON ts.synset_id = bs.target_id
		JOIN synsets ss ON ss.synset_id = bs.source_id
		JOIN lemmas l ON l.synset_id = bs.target_id
		LEFT JOIN best_contrast bc ON bc.target_id = bs.target_id AND bc.rn = 1
		WHERE bs.rn = 1
		ORDER BY bs.salience_sum + COALESCE(bc.contrast_count, 0) DESC
		LIMIT ?
	`, lemma, threshold, limit)

	if err != nil {
		// Surface "no such table" cleanly — cascade tables may be absent on
		// fixture DBs. Handler decides whether that's fatal (cascade mode)
		// or skippable (legacy mode never calls this).
		if strings.Contains(err.Error(), "no such table") {
			return nil, fmt.Errorf("cascade tables missing: %w", err)
		}
		return nil, fmt.Errorf("GetForgeCascadeCandidatesByLemma query: %w", err)
	}
	defer rows.Close()

	seen := make(map[string]bool)
	var matches []CascadeCandidate
	sawAnyRow := false

	for rows.Next() {
		sawAnyRow = true
		var m CascadeCandidate
		var sharedProps string
		if err := rows.Scan(
			&m.SynsetID, &m.POS, &m.Definition, &m.Word,
			&m.SalienceSum, &m.ContrastCount, &sharedProps,
			&m.SourceSynsetID, &m.SourceDefinition, &m.SourcePOS,
			&m.TopicConcreteness, &m.VehicleConcreteness,
		); err != nil {
			slog.Warn("scan cascade candidate failed", "err", err)
			continue
		}
		// Deduplicate: a synset with multiple lemmas produces multiple rows.
		if seen[m.SynsetID] {
			continue
		}
		seen[m.SynsetID] = true
		if sharedProps != "" {
			m.SharedProps = strings.Split(sharedProps, ",")
		}
		matches = append(matches, m)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("GetForgeCascadeCandidatesByLemma iterate: %w", err)
	}

	// Distinguish "lemma not enriched" from "lemma enriched but no gate-pass":
	// the former is a 404 to the user; the latter is an empty 200.
	if !sawAnyRow {
		// Re-check: does the lemma have any curated source synset at all?
		var lemmaHasProps int
		err := database.QueryRow(`
			SELECT COUNT(*) FROM lemmas l
			JOIN synset_properties_curated spc ON spc.synset_id = l.synset_id
			WHERE l.lemma = ?
		`, lemma).Scan(&lemmaHasProps)
		if err != nil {
			slog.Warn("cascade ErrLemmaNotFound re-check failed", "lemma", lemma, "err", err)
		} else if lemmaHasProps == 0 {
			return nil, fmt.Errorf("%w: %s", ErrLemmaNotFound, lemma)
		}
	}

	return matches, nil
}
