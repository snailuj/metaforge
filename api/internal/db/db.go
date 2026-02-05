// Package db provides database access for the Metaforge lexicon.
// It handles retrieval of WordNet synsets with LLM-enriched properties.
package db

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"

	_ "github.com/mattn/go-sqlite3"

	"github.com/snailuj/metaforge/internal/embeddings"
)

// Synset represents a WordNet synset with enrichment
type Synset struct {
	ID           string   `json:"id"`
	POS          string   `json:"pos"`
	Definition   string   `json:"definition"`
	Properties   []string `json:"properties,omitempty"`
	Metonyms     []string `json:"metonyms,omitempty"`
	Connotation  string   `json:"connotation,omitempty"`
	Register     string   `json:"register,omitempty"`
	UsageExample string   `json:"usage_example,omitempty"`
	Rarity       string   `json:"rarity,omitempty"`
}

// Open establishes a read-only connection to the lexicon SQLite database.
// The path parameter should point to the lexicon.db file.
func Open(path string) (*sql.DB, error) {
	return sql.Open("sqlite3", path+"?mode=ro")
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
			continue
		}
		s.Properties = append(s.Properties, prop)
	}

	return &s, nil
}

// GetSynsetsWithSharedProperties finds synsets with similar properties using
// the pre-computed property_similarity matrix and IDF weighting.
//
// Parameters:
//   - sourceID: the synset to find matches for
//   - threshold: minimum similarity score (0.0-1.0) for property matches
//   - limit: maximum number of results to return
//
// Returns matches sorted by TotalScore (descending), where TotalScore is the
// sum of (similarity × IDF) for all matching properties. Higher IDF values
// indicate rarer properties that are more distinctive.
//
// IMPLEMENTATION NOTES:
// Uses the property_similarity table (pre-computed cosine similarity between
// property embeddings) and property_vocabulary IDF weights. This approach:
// - Finds semantically similar properties, not just exact matches
// - Weights matches by property rarity (IDF) for better relevance
// - Leverages database indexes for efficient querying
func GetSynsetsWithSharedProperties(db *sql.DB, sourceID string, threshold float64, limit int) ([]SynsetMatch, error) {
	// Check if the v2 tables exist (property_similarity, synset_properties)
	var tableExists int
	err := db.QueryRow(`
		SELECT COUNT(*) FROM sqlite_master
		WHERE type='table' AND name='property_similarity'
	`).Scan(&tableExists)

	if err != nil || tableExists == 0 {
		// Fall back to legacy exact-match implementation for v1 databases
		return getSynsetsWithSharedPropertiesLegacy(db, sourceID, limit)
	}

	// V2 implementation using similarity matrix with IDF weighting
	rows, err := db.Query(`
		WITH source_props AS (
			SELECT sp.property_id, pv.idf
			FROM synset_properties sp
			JOIN property_vocabulary pv ON pv.property_id = sp.property_id
			WHERE sp.synset_id = ?
		),
		similar_props AS (
			SELECT ps.property_id_b as property_id,
			       MAX(ps.similarity * src.idf) as weighted_similarity
			FROM source_props src
			JOIN property_similarity ps ON ps.property_id_a = src.property_id
			WHERE ps.similarity >= ?
			GROUP BY ps.property_id_b
		)
		SELECT sp.synset_id,
		       SUM(sim.weighted_similarity) as total_score,
		       COUNT(*) as match_count
		FROM similar_props sim
		JOIN synset_properties sp ON sp.property_id = sim.property_id
		WHERE sp.synset_id != ?
		GROUP BY sp.synset_id
		ORDER BY total_score DESC
		LIMIT ?
	`, sourceID, threshold, sourceID, limit)

	if err != nil {
		return nil, fmt.Errorf("failed to query similar synsets: %w", err)
	}
	defer rows.Close()

	var matches []SynsetMatch
	for rows.Next() {
		var m SynsetMatch
		if err := rows.Scan(&m.SynsetID, &m.TotalScore, &m.OverlapCount); err != nil {
			continue
		}
		matches = append(matches, m)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating results: %w", err)
	}

	return matches, nil
}

// getSynsetsWithSharedPropertiesLegacy is the original exact-match implementation
// for backwards compatibility with v1 databases that lack the similarity matrix.
func getSynsetsWithSharedPropertiesLegacy(db *sql.DB, sourceID string, limit int) ([]SynsetMatch, error) {
	source, err := GetSynset(db, sourceID)
	if err != nil {
		return nil, err
	}

	if len(source.Properties) == 0 {
		return nil, fmt.Errorf("source synset has no properties")
	}

	rows, err := db.Query(`
		SELECT synset_id, properties FROM enrichment WHERE synset_id != ?
	`, sourceID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	sourceProps := make(map[string]bool)
	for _, p := range source.Properties {
		sourceProps[p] = true
	}

	var matches []SynsetMatch
	for rows.Next() {
		var id, propsJSON string
		if err := rows.Scan(&id, &propsJSON); err != nil {
			continue
		}

		var props []string
		if err := json.Unmarshal([]byte(propsJSON), &props); err != nil {
			continue
		}

		var shared []string
		for _, p := range props {
			if sourceProps[p] {
				shared = append(shared, p)
			}
		}

		if len(shared) > 0 {
			matches = append(matches, SynsetMatch{
				SynsetID:         id,
				SharedProperties: shared,
				OverlapCount:     len(shared),
				TotalScore:       float64(len(shared)), // Use overlap count as score for legacy
			})
		}
	}

	// Sort by TotalScore descending and apply limit
	// Simple bubble sort - adequate for small result sets
	for i := 0; i < len(matches)-1; i++ {
		for j := 0; j < len(matches)-i-1; j++ {
			if matches[j].TotalScore < matches[j+1].TotalScore {
				matches[j], matches[j+1] = matches[j+1], matches[j]
			}
		}
	}

	if limit > 0 && len(matches) > limit {
		matches = matches[:limit]
	}

	return matches, nil
}

// SynsetMatch represents a candidate match with similarity scoring.
// TotalScore is the sum of (similarity × IDF) for all matching properties,
// where higher IDF values indicate rarer (more distinctive) properties.
type SynsetMatch struct {
	SynsetID         string   `json:"synset_id"`
	SharedProperties []string `json:"shared_properties,omitempty"`
	OverlapCount     int      `json:"overlap_count"`
	TotalScore       float64  `json:"total_score"`
	Distance         float64  `json:"distance,omitempty"`
	Tier             string   `json:"tier,omitempty"`
}

// SynsetMatchFull contains all data needed to classify and display a match,
// retrieved in a single query. Replaces the N+1 pattern of GetSynset +
// GetLemmaForSynset + ComputeSynsetDistance per candidate.
type SynsetMatchFull struct {
	SynsetID         string    `json:"synset_id"`
	Word             string    `json:"word"`
	Definition       string    `json:"definition"`
	SharedProperties []string  `json:"shared_properties,omitempty"`
	ExactOverlap     int       `json:"exact_overlap"`
	TotalScore       float64   `json:"total_score"`
	SourceCentroid   []float32 `json:"-"`
	TargetCentroid   []float32 `json:"-"`
}

// GetForgeMatches retrieves forge candidates in a single mega-query.
//
// Combines candidate discovery (similarity-based), exact property overlap,
// synset details (word, definition), and pre-computed centroids into one
// database round-trip. The caller computes cosine distance in-memory from
// the returned centroids.
//
// Parameters:
//   - sourceID: the synset to find matches for
//   - threshold: minimum similarity score (0.0-1.0) for property matches
//   - limit: maximum number of candidate results
func GetForgeMatches(db *sql.DB, sourceID string, threshold float64, limit int) ([]SynsetMatchFull, error) {
	rows, err := db.Query(`
		WITH source_props AS (
			SELECT sp.property_id
			FROM synset_properties sp
			WHERE sp.synset_id = ?
		),
		candidates AS (
			SELECT sp.synset_id,
			       SUM(ps.similarity * pv.idf) as total_score
			FROM source_props src
			JOIN property_similarity ps ON ps.property_id_a = src.property_id
			JOIN synset_properties sp ON sp.property_id = ps.property_id_b
			JOIN property_vocabulary pv ON pv.property_id = ps.property_id_b
			WHERE ps.similarity >= ?
			  AND sp.synset_id != ?
			GROUP BY sp.synset_id
			ORDER BY total_score DESC
			LIMIT ?
		),
		exact_overlap AS (
			SELECT c.synset_id,
			       COUNT(*) as exact_count,
			       GROUP_CONCAT(pv.text) as shared_props
			FROM candidates c
			JOIN synset_properties sp ON sp.synset_id = c.synset_id
			JOIN source_props src ON src.property_id = sp.property_id
			JOIN property_vocabulary pv ON pv.property_id = sp.property_id
			GROUP BY c.synset_id
		)
		SELECT c.synset_id,
		       s.definition,
		       l.lemma,
		       COALESCE(eo.exact_count, 0) as exact_count,
		       COALESCE(eo.shared_props, '') as shared_props,
		       c.total_score,
		       src_c.centroid as source_centroid,
		       tgt_c.centroid as target_centroid
		FROM candidates c
		JOIN synsets s ON s.synset_id = c.synset_id
		JOIN lemmas l ON l.synset_id = c.synset_id
		LEFT JOIN exact_overlap eo ON eo.synset_id = c.synset_id
		JOIN synset_centroids src_c ON src_c.synset_id = ?
		JOIN synset_centroids tgt_c ON tgt_c.synset_id = c.synset_id
		ORDER BY c.total_score DESC
	`, sourceID, threshold, sourceID, limit, sourceID)

	if err != nil {
		return nil, fmt.Errorf("GetForgeMatches query failed: %w", err)
	}
	defer rows.Close()

	// Track seen synset IDs to deduplicate (a synset may have multiple lemmas)
	seen := make(map[string]bool)
	var matches []SynsetMatchFull

	for rows.Next() {
		var m SynsetMatchFull
		var sharedProps string
		var srcBlob, tgtBlob []byte

		if err := rows.Scan(
			&m.SynsetID, &m.Definition, &m.Word,
			&m.ExactOverlap, &sharedProps, &m.TotalScore,
			&srcBlob, &tgtBlob,
		); err != nil {
			continue
		}

		// Deduplicate: a synset with multiple lemmas produces multiple rows
		if seen[m.SynsetID] {
			continue
		}
		seen[m.SynsetID] = true

		// Parse shared properties from GROUP_CONCAT result
		if sharedProps != "" {
			m.SharedProperties = strings.Split(sharedProps, ",")
		}

		// Decode centroid BLOBs
		m.SourceCentroid = embeddings.BlobToFloats(srcBlob)
		m.TargetCentroid = embeddings.BlobToFloats(tgtBlob)

		matches = append(matches, m)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("GetForgeMatches iteration error: %w", err)
	}

	return matches, nil
}

// GetSynsetIDForLemma finds the first synset ID for a given word.
// Prefers synsets that have enrichment data (properties).
func GetSynsetIDForLemma(db *sql.DB, lemma string) (string, error) {
	var synsetID string

	// Prefer enriched synsets (those with properties in synset_properties)
	err := db.QueryRow(`
		SELECT l.synset_id
		FROM lemmas l
		JOIN synset_properties sp ON sp.synset_id = l.synset_id
		WHERE l.lemma = ?
		LIMIT 1
	`, lemma).Scan(&synsetID)

	if err == nil {
		return synsetID, nil
	}

	// Fall back to any synset
	err = db.QueryRow(`
		SELECT synset_id FROM lemmas WHERE lemma = ? LIMIT 1
	`, lemma).Scan(&synsetID)

	if err == sql.ErrNoRows {
		return "", fmt.Errorf("lemma not found: %s", lemma)
	}
	return synsetID, err
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
