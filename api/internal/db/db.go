// Package db provides database access for the Metaforge lexicon.
// It handles retrieval of WordNet synsets with LLM-enriched properties.
package db

import (
	"database/sql"
	"encoding/json"
	"fmt"

	_ "github.com/mattn/go-sqlite3"
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

// GetSynset retrieves a single synset by ID, including enrichment data
// from the enrichment table if available. Returns an error if the synset
// is not found in the database.
func GetSynset(db *sql.DB, synsetID string) (*Synset, error) {
	var s Synset
	var propsJSON, metonymsJSON sql.NullString

	err := db.QueryRow(`
		SELECT s.synset_id, s.pos, s.definition,
		       e.properties, e.metonyms, e.connotation, e.register, e.usage_example
		FROM synsets s
		LEFT JOIN enrichment e ON s.synset_id = e.synset_id
		WHERE s.synset_id = ?
	`, synsetID).Scan(&s.ID, &s.POS, &s.Definition,
		&propsJSON, &metonymsJSON, &s.Connotation, &s.Register, &s.UsageExample)

	if err != nil {
		return nil, fmt.Errorf("synset not found: %s", synsetID)
	}

	if propsJSON.Valid {
		if err := json.Unmarshal([]byte(propsJSON.String), &s.Properties); err != nil {
			return nil, fmt.Errorf("failed to parse properties for %s: %w", synsetID, err)
		}
	}
	if metonymsJSON.Valid {
		if err := json.Unmarshal([]byte(metonymsJSON.String), &s.Metonyms); err != nil {
			return nil, fmt.Errorf("failed to parse metonyms for %s: %w", synsetID, err)
		}
	}

	return &s, nil
}

// GetSynsetsWithSharedProperties finds all synsets that share at least
// one property with the source synset. Returns matches with shared properties.
//
// PERFORMANCE NOTE (Sprint Zero - Pilot Scale):
// Current implementation loads all enriched synsets into memory and performs
// in-memory property matching. This is acceptable for pilot (1k synsets) but
// will require optimization for full corpus (120k synsets).
//
// SCALING CONSIDERATIONS FOR FULL CORPUS:
//
// Memory usage at full scale (120k synsets):
// - ~120k rows × ~200 bytes/row (ID + JSON properties) = ~24 MB base memory
// - Peak memory during processing could reach 50-100 MB with Go slice growth
// - This is manageable, but response time will degrade (estimated 200-500ms per query)
//
// Required improvements for production:
//
// 1. STREAMING ARCHITECTURE:
//    - Keep current row-by-row processing (already streaming from SQLite)
//    - Add result limit/pagination (e.g., top 50 matches by overlap)
//    - Consider early termination once N high-quality matches found
//
// 2. DATABASE OPTIMIZATIONS:
//    - Add SQLite FTS5 (Full-Text Search) virtual table for property matching:
//        CREATE VIRTUAL TABLE properties_fts USING fts5(synset_id, properties);
//    - This enables SQL-side property intersection, offloading work from Go
//    - Query becomes: SELECT * FROM properties_fts WHERE properties MATCH 'prop1 OR prop2 OR prop3'
//    - Expected speedup: 10-50x for property lookups
//
// 3. CACHING STRATEGY:
//    - Cache frequent queries (e.g., top 100 most-queried words)
//    - Use LRU cache with 5-minute TTL
//    - Reduces repeated full-table scans
//
// 4. INDEX ADDITIONS:
//    - enrichment(synset_id) - already planned in pipeline Task 5
//    - Consider JSON1 extension for property array indexing if FTS5 not used
//
// ALTERNATIVE: PostgreSQL with GIN indexes
// - If SQLite FTS5 proves insufficient, migrate to PostgreSQL
// - Use GIN (Generalized Inverted Index) on jsonb properties column
// - Supports fast array overlap queries: properties ?| array['prop1','prop2']
// - Trade-off: Adds operational complexity (PostgreSQL server management)
// - SQLite remains preferable for MVP due to zero-ops deployment
//
// RECOMMENDATION FOR FULL CORPUS:
// 1. Implement result limiting (top 50 matches) immediately
// 2. Add SQLite FTS5 virtual table for property matching
// 3. Test with full corpus - if query time < 100ms, ship it
// 4. If inadequate, migrate to PostgreSQL with GIN indexes
// 5. SQLite is likely sufficient for read-heavy workload with proper indexing
//
// The current implementation prioritizes correctness and simplicity for MVP.
// Performance optimization should be data-driven after full corpus extraction.
func GetSynsetsWithSharedProperties(db *sql.DB, sourceID string) ([]SynsetMatch, error) {
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
			})
		}
	}

	return matches, nil
}

// SynsetMatch represents a candidate match
type SynsetMatch struct {
	SynsetID         string   `json:"synset_id"`
	SharedProperties []string `json:"shared_properties"`
	OverlapCount     int      `json:"overlap_count"`
	Distance         float64  `json:"distance"`
	Tier             string   `json:"tier"`
}
