// Package db provides database access for the Metaforge lexicon.
// It handles retrieval of WordNet synsets with LLM-enriched properties.
package db

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"

	_ "github.com/mattn/go-sqlite3"

	"github.com/snailuj/metaforge/internal/blobconv"
)

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
			slog.Warn("scan match failed", "source", sourceID, "err", err)
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
			slog.Warn("scan legacy match failed", "source", sourceID, "err", err)
			continue
		}

		var props []string
		if err := json.Unmarshal([]byte(propsJSON), &props); err != nil {
			slog.Warn("unmarshal properties failed", "synset", id, "err", err)
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

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating legacy matches: %w", err)
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
// GetLemmaForSynset + per-candidate distance computation.
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
			slog.Warn("scan forge match failed", "err", err)
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
		m.SourceCentroid = blobconv.BlobToFloats(srcBlob)
		m.TargetCentroid = blobconv.BlobToFloats(tgtBlob)

		matches = append(matches, m)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("GetForgeMatches iteration error: %w", err)
	}

	return matches, nil
}

// CuratedMatch represents a forge match via set intersection (curated vocabulary).
type CuratedMatch struct {
	SynsetID         string   `json:"synset_id"`
	Word             string   `json:"word"`
	POS              string   `json:"pos"`
	Definition       string   `json:"definition"`
	SharedCount      int      `json:"shared_count"`
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
			       COUNT(*) as shared_count,
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
		       sub.shared_count,
		       sub.contrast_count,
		       sub.shared_props
		FROM (
			SELECT COALESCE(sh.synset_id, co.synset_id) as synset_id,
			       COALESCE(sh.shared_count, 0) as shared_count,
			       COALESCE(co.contrast_count, 0) as contrast_count,
			       COALESCE(sh.shared_props, '') as shared_props
			FROM (
				SELECT synset_id FROM shared
				UNION
				SELECT synset_id FROM contrast
			) all_matches
			LEFT JOIN shared sh ON sh.synset_id = all_matches.synset_id
			LEFT JOIN contrast co ON co.synset_id = all_matches.synset_id
			ORDER BY COALESCE(sh.shared_count, 0) + COALESCE(co.contrast_count, 0) DESC
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
			&m.SharedCount, &m.ContrastCount, &sharedProps,
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
		-- For each (source_sense, target) pair, count shared properties
		per_sense_shared AS (
			SELECT ss.synset_id as source_id,
			       tgt.synset_id as target_id,
			       COUNT(*) as shared_count,
			       GROUP_CONCAT(pvc.lemma) as shared_props
			FROM source_synsets ss
			JOIN synset_properties_curated src ON src.synset_id = ss.synset_id
			JOIN synset_properties_curated tgt ON tgt.cluster_id = src.cluster_id
			JOIN property_vocab_curated pvc ON pvc.vocab_id = src.cluster_id
			WHERE tgt.synset_id NOT IN (SELECT synset_id FROM source_synsets)
			GROUP BY ss.synset_id, tgt.synset_id
		),
		-- Pick best source sense per target (most shared properties)
		best_sense AS (
			SELECT source_id, target_id, shared_count, shared_props,
			       ROW_NUMBER() OVER (PARTITION BY target_id ORDER BY shared_count DESC) as rn
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
		       bs.shared_count,
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
		ORDER BY bs.shared_count + COALESCE(bc.contrast_count, 0) DESC
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
			&m.SharedCount, &m.ContrastCount, &sharedProps,
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
		return nil, fmt.Errorf("lemma not found or has no curated properties: %s", lemma)
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
		// Graceful degradation: table missing or lemma not found
		if err == sql.ErrNoRows || strings.Contains(err.Error(), "no such table") {
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
