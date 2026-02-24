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
	Antonyms  []RelatedWord `json:"antonyms"`
}

// Sense represents a single word sense (synset) with its synonyms and relations.
type Sense struct {
	SynsetID     string        `json:"synset_id"`
	POS          string        `json:"pos"`
	Definition   string        `json:"definition"`
	Register     string        `json:"register,omitempty"`
	Connotation  string        `json:"connotation,omitempty"`
	UsageExample string        `json:"usage_example,omitempty"`
	Synonyms     []RelatedWord `json:"synonyms"`
	Relations    Relations     `json:"relations"`
	Collocations []RelatedWord `json:"collocations,omitempty"`
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

	// Query 4: enrichment metadata (register, connotation, usage_example)
	if err := attachEnrichment(database, result.Senses, synsetIDs, senseIndex); err != nil {
		// Non-fatal: enrichment is optional
		slog.Warn("attachEnrichment failed", "lemma", lemma, "err", err)
	}

	// Query 5: collocations from syntagms
	if err := attachCollocations(database, result.Senses, synsetIDs, senseIndex); err != nil {
		// Non-fatal: collocations are optional
		slog.Warn("attachCollocations failed", "lemma", lemma, "err", err)
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
			Antonyms:  []RelatedWord{},
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

// attachEnrichment fetches register, connotation, and usage_example from the
// enrichment table and populates the corresponding fields on each sense in-place.
// Non-fatal: returns an error but callers should log and continue.
func attachEnrichment(database *sql.DB, senses []Sense, synsetIDs []string, senseIndex map[string]int) error {
	if len(synsetIDs) == 0 {
		return nil
	}

	placeholders := make([]string, len(synsetIDs))
	args := make([]interface{}, len(synsetIDs))
	for i, id := range synsetIDs {
		placeholders[i] = "?"
		args[i] = id
	}

	query := `SELECT synset_id, connotation, register, usage_example
		FROM enrichment
		WHERE synset_id IN (` + strings.Join(placeholders, ",") + `)`

	rows, err := database.Query(query, args...)
	if err != nil {
		return err
	}
	defer rows.Close()

	for rows.Next() {
		var synsetID string
		var connotation, register, usageExample sql.NullString
		if err := rows.Scan(&synsetID, &connotation, &register, &usageExample); err != nil {
			continue
		}
		idx, ok := senseIndex[synsetID]
		if !ok {
			continue
		}
		if connotation.Valid {
			senses[idx].Connotation = connotation.String
		}
		if register.Valid {
			senses[idx].Register = register.String
		}
		if usageExample.Valid {
			senses[idx].UsageExample = usageExample.String
		}
	}
	return rows.Err()
}

// maxCollocationsPerSense caps the number of collocations returned per sense.
const maxCollocationsPerSense = 10

// attachCollocations queries the syntagms table to find collocation partners
// for each sense and populates the Collocations field in-place.
// Collocations are deduplicated by word and capped at maxCollocationsPerSense per sense.
// Non-fatal: returns an error but callers should log and continue.
func attachCollocations(database *sql.DB, senses []Sense, synsetIDs []string, senseIndex map[string]int) error {
	if len(synsetIDs) == 0 {
		return nil
	}

	placeholders := make([]string, len(synsetIDs))
	args := make([]interface{}, 0, len(synsetIDs)*2)
	for i, id := range synsetIDs {
		placeholders[i] = "?"
		args = append(args, id)
	}
	inClause := strings.Join(placeholders, ",")

	// Duplicate the args for the second half of the UNION
	args = append(args, args...)

	query := `
		SELECT source_id, target_id, lemma FROM (
			SELECT st.synset1id AS source_id, st.synset2id AS target_id, l.lemma
			FROM syntagms st
			JOIN lemmas l ON l.synset_id = st.synset2id
			WHERE st.synset1id IN (` + inClause + `)
			UNION
			SELECT st.synset2id AS source_id, st.synset1id AS target_id, l.lemma
			FROM syntagms st
			JOIN lemmas l ON l.synset_id = st.synset1id
			WHERE st.synset2id IN (` + inClause + `)
		)
		ORDER BY source_id, lemma
	`

	rows, err := database.Query(query, args...)
	if err != nil {
		return err
	}
	defer rows.Close()

	// Track seen words per sense for deduplication
	seenPerSense := make(map[int]map[string]bool)

	for rows.Next() {
		var sourceID, targetID, word string
		if err := rows.Scan(&sourceID, &targetID, &word); err != nil {
			continue
		}
		idx, ok := senseIndex[sourceID]
		if !ok {
			continue
		}

		if seenPerSense[idx] == nil {
			seenPerSense[idx] = make(map[string]bool)
		}
		if seenPerSense[idx][word] {
			continue
		}
		if len(senses[idx].Collocations) >= maxCollocationsPerSense {
			continue
		}

		seenPerSense[idx][word] = true
		senses[idx].Collocations = append(senses[idx].Collocations, RelatedWord{
			Word:     word,
			SynsetID: targetID,
		})
	}
	return rows.Err()
}

// AutocompleteSuggestion represents a single autocomplete result with
// the dominant sense definition and total sense count for the lemma.
type AutocompleteSuggestion struct {
	Word       string `json:"word"`
	Definition string `json:"definition"`
	SenseCount int    `json:"sense_count"`
	Rarity     string `json:"rarity,omitempty"`
}

// AutocompletePrefix returns lemmas matching a prefix, each with its dominant
// sense definition (preferring enriched synsets), total sense count, and rarity.
// Returns an error if prefix is empty. No-match returns an empty slice, not an error.
func AutocompletePrefix(database *sql.DB, prefix string, limit int) ([]AutocompleteSuggestion, error) {
	prefix = strings.ToLower(strings.TrimSpace(prefix))
	if prefix == "" {
		return nil, errors.New("prefix must not be empty")
	}

	// Escape LIKE metacharacters so user input is treated literally.
	likeEscaper := strings.NewReplacer(`%`, `\%`, `_`, `\_`)
	escapedPrefix := likeEscaper.Replace(prefix)

	rows, err := database.Query(`
		WITH matching_lemmas AS (
			SELECT DISTINCT lemma
			FROM lemmas
			WHERE lemma LIKE ? || '%' ESCAPE '\'
			ORDER BY lemma
			LIMIT ?
		)
		SELECT ml.lemma,
		       (SELECT s.definition
		        FROM lemmas l
		        JOIN synsets s ON s.synset_id = l.synset_id
		        LEFT JOIN synset_properties sp ON sp.synset_id = s.synset_id
		        WHERE l.lemma = ml.lemma
		        ORDER BY (sp.synset_id IS NOT NULL) DESC, s.synset_id
		        LIMIT 1) as definition,
		       (SELECT COUNT(DISTINCT l2.synset_id)
		        FROM lemmas l2
		        WHERE l2.lemma = ml.lemma) as sense_count,
		       f.rarity
		FROM matching_lemmas ml
		LEFT JOIN frequencies f ON f.lemma = ml.lemma
		ORDER BY ml.lemma
	`, escapedPrefix, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var suggestions []AutocompleteSuggestion
	for rows.Next() {
		var s AutocompleteSuggestion
		var definition sql.NullString
		var rarity sql.NullString
		if err := rows.Scan(&s.Word, &definition, &s.SenseCount, &rarity); err != nil {
			slog.Warn("scan autocomplete row failed", "prefix", prefix, "err", err)
			continue
		}
		if definition.Valid {
			s.Definition = definition.String
		}
		if rarity.Valid {
			s.Rarity = rarity.String
		}
		suggestions = append(suggestions, s)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	if suggestions == nil {
		suggestions = []AutocompleteSuggestion{}
	}
	return suggestions, nil
}

func posName(code string) string {
	if name, ok := posNames[code]; ok {
		return name
	}
	return code
}
