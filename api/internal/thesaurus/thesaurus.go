package thesaurus

import (
	"database/sql"
	"errors"
	"strings"
)

// ErrWordNotFound is returned when a lemma has no senses in the database.
var ErrWordNotFound = errors.New("word not found")

// WordNet relation type codes.
const (
	relHypernym = "1"
	relHyponym  = "2"
	relSimilar  = "11"
)

// POS code to human-readable name.
var posNames = map[string]string{
	"n": "noun",
	"v": "verb",
	"a": "adjective",
	"r": "adverb",
	"s": "adjective satellite",
}

// RelatedWord represents a word linked by a WordNet relation.
type RelatedWord struct {
	Word     string `json:"word"`
	SynsetID string `json:"synset_id"`
}

// Relations groups related words by relation type.
type Relations struct {
	Hypernyms []RelatedWord `json:"hypernyms"`
	Hyponyms  []RelatedWord `json:"hyponyms"`
	Similar   []RelatedWord `json:"similar"`
}

// Sense represents a single word sense (synset) with its synonyms and relations.
type Sense struct {
	SynsetID   string    `json:"synset_id"`
	POS        string    `json:"pos"`
	Definition string    `json:"definition"`
	Synonyms   []RelatedWord `json:"synonyms"`
	Relations  Relations `json:"relations"`
}

// LookupResult is the full response for a thesaurus lookup.
type LookupResult struct {
	Word   string  `json:"word"`
	Senses []Sense `json:"senses"`
}

// GetLookup returns all senses for a given lemma, grouped by synset,
// with synonyms and relations. Uses two queries total.
func GetLookup(database *sql.DB, lemma string) (*LookupResult, error) {
	// Query 1: all synsets for this lemma, with synonyms via GROUP_CONCAT
	senses, err := querySenses(database, lemma)
	if err != nil {
		return nil, err
	}
	if len(senses) == 0 {
		return nil, ErrWordNotFound
	}

	// Collect synset IDs for bulk relation lookup
	synsetIDs := make([]string, len(senses))
	senseIndex := make(map[string]int, len(senses))
	for i, s := range senses {
		synsetIDs[i] = s.SynsetID
		senseIndex[s.SynsetID] = i
	}

	// Query 2: all relations for these synsets in bulk
	if err := queryRelations(database, senses, synsetIDs, senseIndex); err != nil {
		return nil, err
	}

	return &LookupResult{Word: lemma, Senses: senses}, nil
}

// querySenses fetches all synsets and their synonyms for a lemma.
func querySenses(database *sql.DB, lemma string) ([]Sense, error) {
	rows, err := database.Query(`
		SELECT s.synset_id, s.pos, s.definition,
		       GROUP_CONCAT(l2.lemma, '|') AS synonyms
		FROM lemmas l
		JOIN synsets s ON s.synset_id = l.synset_id
		LEFT JOIN lemmas l2 ON l2.synset_id = s.synset_id AND l2.lemma != ?
		WHERE l.lemma = ?
		GROUP BY s.synset_id
		ORDER BY s.pos, s.synset_id
	`, lemma, lemma)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var senses []Sense
	for rows.Next() {
		var s Sense
		var rawPOS string
		var rawSynonyms sql.NullString
		if err := rows.Scan(&s.SynsetID, &rawPOS, &s.Definition, &rawSynonyms); err != nil {
			return nil, err
		}
		s.POS = posName(rawPOS)
		if rawSynonyms.Valid && rawSynonyms.String != "" {
			for _, word := range strings.Split(rawSynonyms.String, "|") {
				s.Synonyms = append(s.Synonyms, RelatedWord{Word: word, SynsetID: s.SynsetID})
			}
		}
		s.Relations = Relations{
			Hypernyms: []RelatedWord{},
			Hyponyms:  []RelatedWord{},
			Similar:   []RelatedWord{},
		}
		senses = append(senses, s)
	}
	return senses, rows.Err()
}

// queryRelations fetches hypernyms, hyponyms, and similar relations in bulk
// and populates the senses in-place.
func queryRelations(database *sql.DB, senses []Sense, synsetIDs []string, senseIndex map[string]int) error {
	if len(synsetIDs) == 0 {
		return nil
	}

	// Build placeholders for IN clause
	placeholders := make([]string, len(synsetIDs))
	args := make([]interface{}, len(synsetIDs))
	for i, id := range synsetIDs {
		placeholders[i] = "?"
		args[i] = id
	}
	inClause := strings.Join(placeholders, ",")

	query := `
		SELECT r.source_synset, r.relation_type, r.target_synset, l.lemma
		FROM relations r
		JOIN lemmas l ON l.synset_id = r.target_synset
		WHERE r.source_synset IN (` + inClause + `)
		  AND r.relation_type IN ('1', '2', '11')
		GROUP BY r.source_synset, r.relation_type, r.target_synset
	`

	rows, err := database.Query(query, args...)
	if err != nil {
		return err
	}
	defer rows.Close()

	for rows.Next() {
		var sourceSynset, relType, targetSynset, word string
		if err := rows.Scan(&sourceSynset, &relType, &targetSynset, &word); err != nil {
			return err
		}
		idx, ok := senseIndex[sourceSynset]
		if !ok {
			continue
		}
		rw := RelatedWord{Word: word, SynsetID: targetSynset}
		switch relType {
		case relHypernym:
			senses[idx].Relations.Hypernyms = append(senses[idx].Relations.Hypernyms, rw)
		case relHyponym:
			senses[idx].Relations.Hyponyms = append(senses[idx].Relations.Hyponyms, rw)
		case relSimilar:
			senses[idx].Relations.Similar = append(senses[idx].Relations.Similar, rw)
		}
	}
	return rows.Err()
}

func posName(code string) string {
	if name, ok := posNames[code]; ok {
		return name
	}
	return code
}
