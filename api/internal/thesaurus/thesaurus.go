package thesaurus

import (
	"database/sql"
	"errors"
	"log/slog"
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
	Rarity   string `json:"rarity,omitempty"`
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
	Rarity string  `json:"rarity,omitempty"`
}

// GetLookup returns all senses for a given lemma, grouped by synset,
// with synonyms and relations. Uses three queries total.
func GetLookup(database *sql.DB, lemma string) (*LookupResult, error) {
	lemma = strings.ToLower(strings.TrimSpace(lemma))

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

	result := &LookupResult{Word: lemma, Senses: senses}

	// Query 3: rarity data for all words in the result
	if err := attachRarity(database, result); err != nil {
		// Non-fatal: rarity is optional enrichment
		slog.Warn("attachRarity failed", "lemma", lemma, "err", err)
	}

	return result, nil
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
		s.Synonyms = []RelatedWord{}
		if rawSynonyms.Valid && rawSynonyms.String != "" {
			seen := map[string]bool{}
			for _, word := range strings.Split(rawSynonyms.String, "|") {
				if !seen[word] {
					seen[word] = true
					s.Synonyms = append(s.Synonyms, RelatedWord{Word: word, SynsetID: s.SynsetID})
				}
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

// attachRarity fetches rarity data for the looked-up word and all related words,
// populating the Rarity fields in-place.
func attachRarity(database *sql.DB, result *LookupResult) error {
	// Collect all unique words that need rarity lookup
	words := map[string]bool{result.Word: true}
	for _, sense := range result.Senses {
		for _, syn := range sense.Synonyms {
			words[syn.Word] = true
		}
		for _, h := range sense.Relations.Hypernyms {
			words[h.Word] = true
		}
		for _, h := range sense.Relations.Hyponyms {
			words[h.Word] = true
		}
		for _, s := range sense.Relations.Similar {
			words[s.Word] = true
		}
	}

	// Build IN clause
	placeholders := make([]string, 0, len(words))
	args := make([]interface{}, 0, len(words))
	for w := range words {
		placeholders = append(placeholders, "?")
		args = append(args, w)
	}
	if len(placeholders) == 0 {
		return nil
	}

	query := `SELECT lemma, rarity FROM frequencies WHERE lemma IN (` +
		strings.Join(placeholders, ",") + `)`

	rows, err := database.Query(query, args...)
	if err != nil {
		return err
	}
	defer rows.Close()

	rarityMap := make(map[string]string)
	for rows.Next() {
		var lemma, rarity string
		if err := rows.Scan(&lemma, &rarity); err != nil {
			continue
		}
		rarityMap[lemma] = rarity
	}
	if err := rows.Err(); err != nil {
		return err
	}

	// Apply rarity to result
	result.Rarity = rarityMap[result.Word]

	for i := range result.Senses {
		for j := range result.Senses[i].Synonyms {
			result.Senses[i].Synonyms[j].Rarity = rarityMap[result.Senses[i].Synonyms[j].Word]
		}
		for j := range result.Senses[i].Relations.Hypernyms {
			result.Senses[i].Relations.Hypernyms[j].Rarity = rarityMap[result.Senses[i].Relations.Hypernyms[j].Word]
		}
		for j := range result.Senses[i].Relations.Hyponyms {
			result.Senses[i].Relations.Hyponyms[j].Rarity = rarityMap[result.Senses[i].Relations.Hyponyms[j].Word]
		}
		for j := range result.Senses[i].Relations.Similar {
			result.Senses[i].Relations.Similar[j].Rarity = rarityMap[result.Senses[i].Relations.Similar[j].Word]
		}
	}

	return nil
}

func posName(code string) string {
	if name, ok := posNames[code]; ok {
		return name
	}
	return code
}
