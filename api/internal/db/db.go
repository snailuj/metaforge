// Package db provides database access for the Metaforge lexicon.
// It handles retrieval of WordNet synsets with LLM-enriched properties.
package db

import (
	"database/sql"
	"errors"
	"fmt"
	"log/slog"
	"strings"

	_ "github.com/mattn/go-sqlite3"

	"github.com/snailuj/metaforge/internal/blobconv"
)

// ErrLemmaNotFound is returned when a lemma has no curated properties.
var ErrLemmaNotFound = errors.New("lemma not found or has no curated properties")

// Synset represents a WordNet synset with enrichment
type Synset struct {
	ID           string   `json:"id"`
	POS          string   `json:"pos"`
	Definition   string   `json:"definition"`
	Properties   []string `json:"properties,omitempty"`
	Metonyms     []string `json:"metonyms,omitempty"`     // Placeholder: SyntagNet import pending
	Connotation  string   `json:"connotation,omitempty"`
	Register     string   `json:"register,omitempty"`
	UsageExample string   `json:"usage_example,omitempty"`
}

// Open establishes a read-only connection to the lexicon SQLite database.
// The path parameter should point to the lexicon.db file.
// Uses immutable=1 so SQLite skips journal/WAL/shm files entirely,
// which is required when the DB lives on a read-only filesystem.
func Open(path string) (*sql.DB, error) {
	return sql.Open("sqlite3", path+"?mode=ro&immutable=1")
}

// GetSynset retrieves a single synset by ID, including enrichment data.
// Properties are retrieved from the synset_properties junction table (v2 schema).
// Returns an error if the synset is not found in the database.
func GetSynset(db *sql.DB, synsetID string) (*Synset, error) {
	var s Synset
	var connotation, register, usageExample sql.NullString

	// Get synset base data + enrichment metadata
	err := db.QueryRow(`
		SELECT s.synset_id, s.pos, s.definition,
		       e.connotation, e.register, e.usage_example
		FROM synsets s
		LEFT JOIN enrichment e ON s.synset_id = e.synset_id
		WHERE s.synset_id = ?
	`, synsetID).Scan(&s.ID, &s.POS, &s.Definition,
		&connotation, &register, &usageExample)

	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("synset not found: %s", synsetID)
	}
	if err != nil {
		return nil, fmt.Errorf("query failed for %s: %w", synsetID, err)
	}

	// Handle nullable enrichment fields
	if connotation.Valid {
		s.Connotation = connotation.String
	}
	if register.Valid {
		s.Register = register.String
	}
	if usageExample.Valid {
		s.UsageExample = usageExample.String
	}

	// Get properties from junction table (v2 schema)
	rows, err := db.Query(`
		SELECT pv.text
		FROM synset_properties sp
		JOIN property_vocabulary pv ON pv.property_id = sp.property_id
		WHERE sp.synset_id = ?
	`, synsetID)
	if err != nil {
		return nil, fmt.Errorf("failed to query properties for %s: %w", synsetID, err)
	}
	defer rows.Close()

	for rows.Next() {
		var prop string
		if err := rows.Scan(&prop); err != nil {
			slog.Warn("scan property failed", "synset", synsetID, "err", err)
			continue
		}
		s.Properties = append(s.Properties, prop)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating properties for %s: %w", synsetID, err)
	}

	return &s, nil
}

// CuratedMatch represents a forge match via set intersection (curated vocabulary).
type CuratedMatch struct {
	SynsetID         string   `json:"synset_id"`
	Word             string   `json:"word"`
	POS              string   `json:"pos"`
	Definition       string   `json:"definition"`
	SalienceSum      float64  `json:"salience_sum"`
	ContrastCount    int      `json:"contrast_count"`
	SharedProps      []string `json:"shared_properties,omitempty"`
	SourceSynsetID   string   `json:"source_synset_id,omitempty"`
	SourceDefinition string   `json:"source_definition,omitempty"`
	SourcePOS        string   `json:"source_pos,omitempty"`
}

// GetForgeMatchesCurated finds forge candidates using curated vocabulary set intersection.
// No embeddings or cosine distance — pure integer JOINs for shared + antonymous properties.
func GetForgeMatchesCurated(db *sql.DB, sourceID string, limit int) ([]CuratedMatch, error) {
	rows, err := db.Query(`
		WITH source_props AS (
			SELECT cluster_id FROM synset_properties_curated WHERE synset_id = ?
		),
		shared AS (
			SELECT spc.synset_id,
			       SUM(spc.salience_sum) as salience_sum,
			       GROUP_CONCAT(pvc.lemma) as shared_props
			FROM source_props sp
			JOIN synset_properties_curated spc ON spc.cluster_id = sp.cluster_id
			JOIN property_vocab_curated pvc ON pvc.vocab_id = sp.cluster_id
			WHERE spc.synset_id != ?
			GROUP BY spc.synset_id
		),
		contrast AS (
			SELECT spc.synset_id,
			       COUNT(*) as contrast_count
			FROM source_props sp
			JOIN cluster_antonyms ca ON ca.cluster_id_a = sp.cluster_id
			JOIN synset_properties_curated spc ON spc.cluster_id = ca.cluster_id_b
			WHERE spc.synset_id != ?
			GROUP BY spc.synset_id
		)
		SELECT sub.synset_id,
		       s.definition,
		       l.lemma,
		       sub.salience_sum,
		       sub.contrast_count,
		       sub.shared_props
		FROM (
			SELECT COALESCE(sh.synset_id, co.synset_id) as synset_id,
			       COALESCE(sh.salience_sum, 0.0) as salience_sum,
			       COALESCE(co.contrast_count, 0) as contrast_count,
			       COALESCE(sh.shared_props, '') as shared_props
			FROM (
				SELECT synset_id FROM shared
				UNION
				SELECT synset_id FROM contrast
			) all_matches
			LEFT JOIN shared sh ON sh.synset_id = all_matches.synset_id
			LEFT JOIN contrast co ON co.synset_id = all_matches.synset_id
			ORDER BY COALESCE(sh.salience_sum, 0.0) + COALESCE(co.contrast_count, 0) DESC
			LIMIT ?
		) sub
		JOIN synsets s ON s.synset_id = sub.synset_id
		JOIN lemmas l ON l.synset_id = sub.synset_id
	`, sourceID, sourceID, sourceID, limit)

	if err != nil {
		return nil, fmt.Errorf("GetForgeMatchesCurated query failed: %w", err)
	}
	defer rows.Close()

	seen := make(map[string]bool)
	var matches []CuratedMatch

	for rows.Next() {
		var m CuratedMatch
		var sharedProps string

		if err := rows.Scan(
			&m.SynsetID, &m.Definition, &m.Word,
			&m.SalienceSum, &m.ContrastCount, &sharedProps,
		); err != nil {
			slog.Warn("scan curated match failed", "err", err)
			continue
		}

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
		return nil, fmt.Errorf("GetForgeMatchesCurated iteration error: %w", err)
	}

	return matches, nil
}

// GetForgeMatchesCuratedByLemma finds forge candidates for a lemma with per-candidate
// sense alignment. For polysemous words (e.g. "bank"), each target is matched against
// whichever source sense shares the most properties with it, rather than picking a
// single source synset up front.
//
// Returns matches sorted by (shared_count + contrast_count) descending. Each match
// carries source-side context (SourceSynsetID, SourceDefinition, SourcePOS) reflecting
// the best-aligned source sense for that specific target.
func GetForgeMatchesCuratedByLemma(database *sql.DB, lemma string, limit int) ([]CuratedMatch, error) {
	rows, err := database.Query(`
		WITH source_synsets AS (
			SELECT l.synset_id
			FROM lemmas l
			JOIN synset_properties_curated spc ON spc.synset_id = l.synset_id
			WHERE l.lemma = ?
			GROUP BY l.synset_id
		),
		-- For each (source_sense, target) pair, sum salience weights
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
		-- Pick best source sense per target (highest salience sum)
		best_sense AS (
			SELECT source_id, target_id, salience_sum, shared_props,
			       ROW_NUMBER() OVER (PARTITION BY target_id ORDER BY salience_sum DESC) as rn
			FROM per_sense_shared
		),
		-- Count antonymous properties per (source_sense, target) pair
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
		       ts.pos,
		       ts.definition,
		       l.lemma,
		       bs.salience_sum,
		       COALESCE(bc.contrast_count, 0) as contrast_count,
		       bs.shared_props,
		       bs.source_id,
		       ss.definition as source_definition,
		       ss.pos as source_pos
		FROM best_sense bs
		JOIN synsets ts ON ts.synset_id = bs.target_id
		JOIN synsets ss ON ss.synset_id = bs.source_id
		JOIN lemmas l ON l.synset_id = bs.target_id
		LEFT JOIN best_contrast bc ON bc.target_id = bs.target_id AND bc.rn = 1
		WHERE bs.rn = 1
		ORDER BY bs.salience_sum + COALESCE(bc.contrast_count, 0) DESC
		LIMIT ?
	`, lemma, limit)

	if err != nil {
		return nil, fmt.Errorf("GetForgeMatchesCuratedByLemma query failed: %w", err)
	}
	defer rows.Close()

	seen := make(map[string]bool)
	var matches []CuratedMatch

	for rows.Next() {
		var m CuratedMatch
		var sharedProps string

		if err := rows.Scan(
			&m.SynsetID, &m.POS, &m.Definition, &m.Word,
			&m.SalienceSum, &m.ContrastCount, &sharedProps,
			&m.SourceSynsetID, &m.SourceDefinition, &m.SourcePOS,
		); err != nil {
			slog.Warn("scan curated-by-lemma match failed", "err", err)
			continue
		}

		// Deduplicate: a synset with multiple lemmas produces multiple rows
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
		return nil, fmt.Errorf("GetForgeMatchesCuratedByLemma iteration error: %w", err)
	}

	if len(matches) == 0 {
		return nil, fmt.Errorf("%w: %s", ErrLemmaNotFound, lemma)
	}

	return matches, nil
}

// GetSynsetIDForLemma finds the best synset ID for a given word.
// Prefers synsets with the most curated properties, then falls back to
// legacy enriched synsets, then to any synset for the lemma.
func GetSynsetIDForLemma(db *sql.DB, lemma string) (string, error) {
	var synsetID string

	// 1. Prefer synsets with curated properties (most curated props first)
	err := db.QueryRow(`
		SELECT l.synset_id
		FROM lemmas l
		JOIN synset_properties_curated spc ON spc.synset_id = l.synset_id
		WHERE l.lemma = ?
		GROUP BY l.synset_id
		ORDER BY COUNT(*) DESC
		LIMIT 1
	`, lemma).Scan(&synsetID)
	if err == nil {
		return synsetID, nil
	}
	slog.Debug("no curated synset for lemma", "lemma", lemma, "err", err)

	// 2. Fall back to legacy enriched synsets
	err = db.QueryRow(`
		SELECT l.synset_id
		FROM lemmas l
		JOIN synset_properties sp ON sp.synset_id = l.synset_id
		WHERE l.lemma = ?
		LIMIT 1
	`, lemma).Scan(&synsetID)
	if err == nil {
		return synsetID, nil
	}
	slog.Debug("no legacy enriched synset for lemma", "lemma", lemma, "err", err)

	// 3. Fall back to any synset
	err = db.QueryRow(`
		SELECT synset_id FROM lemmas WHERE lemma = ? LIMIT 1
	`, lemma).Scan(&synsetID)
	if err == sql.ErrNoRows {
		return "", fmt.Errorf("lemma not found: %s", lemma)
	}
	return synsetID, err
}

// GetLemmaEmbedding retrieves the FastText embedding for a single lemma.
// Returns (nil, nil) if the lemma is not found or if the lemma_embeddings table doesn't exist.
func GetLemmaEmbedding(db *sql.DB, lemma string) ([]float32, error) {
	var blob []byte
	err := db.QueryRow("SELECT embedding FROM lemma_embeddings WHERE lemma = ?", lemma).Scan(&blob)
	if err != nil {
		if err == sql.ErrNoRows {
			slog.Debug("lemma embedding not found", "lemma", lemma)
			return nil, nil
		}
		if strings.Contains(err.Error(), "no such table") {
			slog.Debug("lemma_embeddings table missing, skipping embedding lookup", "lemma", lemma)
			return nil, nil
		}
		return nil, fmt.Errorf("GetLemmaEmbedding failed for %s: %w", lemma, err)
	}
	return blobconv.BlobToFloats(blob), nil
}

// GetLemmaEmbeddingsBatch retrieves FastText embeddings for multiple lemmas.
// Returns a map of lemma -> embedding. Missing lemmas are simply absent from the map.
// Returns (nil, nil) gracefully if the lemma_embeddings table doesn't exist.
func GetLemmaEmbeddingsBatch(db *sql.DB, lemmas []string) (map[string][]float32, error) {
	if len(lemmas) == 0 {
		return nil, nil
	}

	placeholders := make([]string, len(lemmas))
	args := make([]interface{}, len(lemmas))
	for i, l := range lemmas {
		placeholders[i] = "?"
		args[i] = l
	}

	query := "SELECT lemma, embedding FROM lemma_embeddings WHERE lemma IN (" +
		strings.Join(placeholders, ",") + ")"

	rows, err := db.Query(query, args...)
	if err != nil {
		if strings.Contains(err.Error(), "no such table") {
			return nil, nil
		}
		return nil, fmt.Errorf("GetLemmaEmbeddingsBatch query failed: %w", err)
	}
	defer rows.Close()

	result := make(map[string][]float32)
	for rows.Next() {
		var lemma string
		var blob []byte
		if err := rows.Scan(&lemma, &blob); err != nil {
			slog.Warn("scan lemma embedding failed", "err", err)
			continue
		}
		vec := blobconv.BlobToFloats(blob)
		if vec != nil {
			result[lemma] = vec
		}
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("GetLemmaEmbeddingsBatch iteration error: %w", err)
	}

	return result, nil
}

// GetLemmaForSynset returns the primary lemma for a synset.
func GetLemmaForSynset(db *sql.DB, synsetID string) (string, error) {
	var lemma string
	err := db.QueryRow(`
		SELECT lemma FROM lemmas WHERE synset_id = ? LIMIT 1
	`, synsetID).Scan(&lemma)
	if err == sql.ErrNoRows {
		return "", fmt.Errorf("no lemma for synset: %s", synsetID)
	}
	return lemma, err
}

