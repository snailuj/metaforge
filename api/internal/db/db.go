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
