package thesaurus

import (
	"database/sql"
	"testing"

	"github.com/snailuj/metaforge/internal/db"
)

var testDBPath = "../../../data-pipeline/output/lexicon_v2.db"

func openTestDB(t *testing.T) *sql.DB {
	t.Helper()
	database, err := db.Open(testDBPath)
	if err != nil {
		t.Skipf("skipping: cannot open test DB: %v", err)
	}
	return database
}

func TestGetLookup_Fire(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	result, err := GetLookup(database, "fire")
	if err != nil {
		t.Fatalf("GetLookup(fire) returned error: %v", err)
	}

	if result.Word != "fire" {
		t.Errorf("expected Word='fire', got %q", result.Word)
	}

	if len(result.Senses) == 0 {
		t.Fatal("expected at least one sense for 'fire'")
	}

	// fire has 21 senses in our database
	if len(result.Senses) != 21 {
		t.Errorf("expected 21 senses for 'fire', got %d", len(result.Senses))
	}

	// Each sense must have required fields
	for i, sense := range result.Senses {
		if sense.SynsetID == "" {
			t.Errorf("sense[%d] has empty SynsetID", i)
		}
		if sense.POS == "" {
			t.Errorf("sense[%d] has empty POS", i)
		}
		if sense.Definition == "" {
			t.Errorf("sense[%d] has empty Definition", i)
		}
	}
}

func TestGetLookup_Melancholy(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	result, err := GetLookup(database, "melancholy")
	if err != nil {
		t.Fatalf("GetLookup(melancholy) returned error: %v", err)
	}

	if result.Word != "melancholy" {
		t.Errorf("expected Word='melancholy', got %q", result.Word)
	}

	// melancholy has 5 senses
	if len(result.Senses) != 5 {
		t.Errorf("expected 5 senses for 'melancholy', got %d", len(result.Senses))
	}

	// Check that synonyms exclude the searched word itself
	for i, sense := range result.Senses {
		for _, syn := range sense.Synonyms {
			if syn.Word == "melancholy" {
				t.Errorf("sense[%d] synonyms should exclude the searched word, found 'melancholy'", i)
			}
		}
	}

	// Each synonym must have Word and SynsetID
	for i, sense := range result.Senses {
		for _, syn := range sense.Synonyms {
			if syn.Word == "" {
				t.Errorf("sense[%d] has synonym with empty Word", i)
			}
			if syn.SynsetID == "" {
				t.Errorf("sense[%d] has synonym with empty SynsetID", i)
			}
		}
	}

	// Sense 8067 should have "somber" and "sombre" as synonyms
	found := false
	for _, sense := range result.Senses {
		if sense.SynsetID == "8067" {
			found = true
			hasSomber := false
			hasSombre := false
			for _, syn := range sense.Synonyms {
				if syn.Word == "somber" {
					hasSomber = true
				}
				if syn.Word == "sombre" {
					hasSombre = true
				}
			}
			if !hasSomber {
				t.Error("sense 8067 should have 'somber' as synonym")
			}
			if !hasSombre {
				t.Error("sense 8067 should have 'sombre' as synonym")
			}
		}
	}
	if !found {
		t.Error("expected sense with SynsetID '8067'")
	}
}

func TestGetLookup_CaseInsensitive(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	variants := []string{"Fire", "FIRE", " fire ", "MELANCHOLY"}
	for _, input := range variants {
		result, err := GetLookup(database, input)
		if err != nil {
			t.Errorf("GetLookup(%q) returned error: %v", input, err)
			continue
		}
		if len(result.Senses) == 0 {
			t.Errorf("GetLookup(%q) returned no senses", input)
		}
	}
}

func TestGetLookup_UnknownWord(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	_, err := GetLookup(database, "xyzzyplugh")
	if err == nil {
		t.Fatal("expected error for unknown word, got nil")
	}
	if err != ErrWordNotFound {
		t.Errorf("expected ErrWordNotFound, got %v", err)
	}
}

func TestGetLookup_Relations(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	result, err := GetLookup(database, "fire")
	if err != nil {
		t.Fatalf("GetLookup(fire) returned error: %v", err)
	}

	// fire should have some relations (hypernyms at minimum)
	hasRelations := false
	for _, sense := range result.Senses {
		if len(sense.Relations.Hypernyms) > 0 || len(sense.Relations.Hyponyms) > 0 || len(sense.Relations.Similar) > 0 {
			hasRelations = true
			break
		}
	}
	if !hasRelations {
		t.Error("expected at least one sense of 'fire' to have relations")
	}

	// Each related word must have required fields
	for _, sense := range result.Senses {
		for _, rel := range sense.Relations.Hypernyms {
			if rel.Word == "" || rel.SynsetID == "" {
				t.Errorf("hypernym has empty Word or SynsetID in sense %s", sense.SynsetID)
			}
		}
		for _, rel := range sense.Relations.Hyponyms {
			if rel.Word == "" || rel.SynsetID == "" {
				t.Errorf("hyponym has empty Word or SynsetID in sense %s", sense.SynsetID)
			}
		}
		for _, rel := range sense.Relations.Similar {
			if rel.Word == "" || rel.SynsetID == "" {
				t.Errorf("similar has empty Word or SynsetID in sense %s", sense.SynsetID)
			}
		}
	}
}

func TestGetLookup_PosNames(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	// "fire" has both noun and verb senses — check POS names are human-readable
	result, err := GetLookup(database, "fire")
	if err != nil {
		t.Fatalf("GetLookup(fire) returned error: %v", err)
	}

	posValues := map[string]bool{}
	for _, sense := range result.Senses {
		posValues[sense.POS] = true
	}

	// Should have human-readable POS names, not raw codes
	if posValues["n"] || posValues["v"] || posValues["a"] || posValues["r"] {
		t.Error("POS should be human-readable (noun, verb, etc.), not raw codes")
	}
	if !posValues["noun"] {
		t.Error("Expected 'noun' among POS values for 'fire'")
	}
	if !posValues["verb"] {
		t.Error("Expected 'verb' among POS values for 'fire'")
	}
}

func TestGetLookup_SimilarRelations(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	// "hold" has many similar relations (type 11) in the database
	result, err := GetLookup(database, "hold")
	if err != nil {
		t.Skipf("'hold' not found: %v", err)
	}

	hasSimilar := false
	for _, sense := range result.Senses {
		if len(sense.Relations.Similar) > 0 {
			hasSimilar = true
			for _, rel := range sense.Relations.Similar {
				if rel.Word == "" || rel.SynsetID == "" {
					t.Errorf("Similar relation has empty Word or SynsetID in sense %s", sense.SynsetID)
				}
			}
			break
		}
	}
	if !hasSimilar {
		t.Error("Expected 'hold' to have similar relations")
	}
}

func TestGetLookup_RarityPresent(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	result, err := GetLookup(database, "happy")
	if err != nil {
		t.Fatalf("GetLookup(happy) returned error: %v", err)
	}

	if result.Rarity == "" {
		t.Error("expected Rarity to be populated for 'happy'")
	}
	if result.Rarity != "common" {
		t.Errorf("expected Rarity='common' for 'happy', got %q", result.Rarity)
	}
}

func TestGetLookup_SynonymRarityPresent(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	result, err := GetLookup(database, "fire")
	if err != nil {
		t.Fatalf("GetLookup(fire) returned error: %v", err)
	}

	// Check that at least some synonyms have rarity populated
	hasRarity := false
	for _, sense := range result.Senses {
		for _, syn := range sense.Synonyms {
			if syn.Rarity != "" {
				hasRarity = true
				break
			}
		}
		if hasRarity {
			break
		}
	}
	if !hasRarity {
		t.Error("expected at least some synonyms to have Rarity populated")
	}
}

func TestGetLookup_AdjectiveSatellitePOS(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	// "abandoned" has adjective satellite senses (POS code "s")
	result, err := GetLookup(database, "abandoned")
	if err != nil {
		t.Skipf("'abandoned' not found: %v", err)
	}

	hasAdjSat := false
	for _, sense := range result.Senses {
		if sense.POS == "adjective satellite" {
			hasAdjSat = true
			break
		}
	}
	if !hasAdjSat {
		t.Error("Expected 'abandoned' to have at least one 'adjective satellite' sense")
	}
}

func TestPosNameUnknownCode(t *testing.T) {
	// posName should return the code itself if unknown
	result := posName("x")
	if result != "x" {
		t.Errorf("Expected posName('x') = 'x', got '%s'", result)
	}
}

func TestPosNameAllKnown(t *testing.T) {
	// All 5 known codes should map correctly
	tests := []struct {
		code     string
		expected string
	}{
		{"n", "noun"},
		{"v", "verb"},
		{"a", "adjective"},
		{"r", "adverb"},
		{"s", "adjective satellite"},
	}

	for _, tt := range tests {
		result := posName(tt.code)
		if result != tt.expected {
			t.Errorf("posName(%q) = %q, expected %q", tt.code, result, tt.expected)
		}
	}
}

func TestGetLookupEmptyString(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	// Empty string should return ErrWordNotFound
	_, err := GetLookup(database, "")
	if err != ErrWordNotFound {
		t.Errorf("Expected ErrWordNotFound for empty string, got %v", err)
	}
}

func TestGetLookupWhitespaceOnly(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	// Whitespace-only string should return ErrWordNotFound
	_, err := GetLookup(database, "   ")
	if err != ErrWordNotFound {
		t.Errorf("Expected ErrWordNotFound for whitespace, got %v", err)
	}
}

func TestAutocompletePrefix_Fire(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	suggestions, err := AutocompletePrefix(database, "fir", 10)
	if err != nil {
		t.Fatalf("AutocompletePrefix('fir', 10) returned error: %v", err)
	}

	if len(suggestions) == 0 {
		t.Fatal("expected at least one suggestion for prefix 'fir'")
	}

	// "fire" should be among the results
	found := false
	for _, s := range suggestions {
		if s.Word == "fire" {
			found = true
			if s.Definition == "" {
				t.Error("expected non-empty definition for 'fire'")
			}
			if s.SenseCount != 21 {
				t.Errorf("expected SenseCount=21 for 'fire', got %d", s.SenseCount)
			}
			break
		}
	}
	if !found {
		t.Error("expected 'fire' among suggestions for prefix 'fir'")
	}
}

func TestAutocompletePrefix_WithRarity(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	suggestions, err := AutocompletePrefix(database, "happ", 10)
	if err != nil {
		t.Fatalf("AutocompletePrefix('happ', 10) returned error: %v", err)
	}

	// "happy" should have rarity populated
	for _, s := range suggestions {
		if s.Word == "happy" {
			if s.Rarity == "" {
				t.Error("expected Rarity to be populated for 'happy'")
			}
			return
		}
	}
	t.Error("expected 'happy' among suggestions for prefix 'happ'")
}

func TestAutocompletePrefix_EmptyPrefix(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	_, err := AutocompletePrefix(database, "", 10)
	if err == nil {
		t.Fatal("expected error for empty prefix, got nil")
	}
}

func TestAutocompletePrefix_NoMatch(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	suggestions, err := AutocompletePrefix(database, "xyzzyplugh", 10)
	if err != nil {
		t.Fatalf("expected nil error for no-match prefix, got: %v", err)
	}
	if len(suggestions) != 0 {
		t.Errorf("expected empty suggestions for no-match prefix, got %d", len(suggestions))
	}
}

func TestAutocompletePrefix_Limit(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	suggestions, err := AutocompletePrefix(database, "a", 5)
	if err != nil {
		t.Fatalf("AutocompletePrefix('a', 5) returned error: %v", err)
	}
	if len(suggestions) > 5 {
		t.Errorf("expected at most 5 suggestions, got %d", len(suggestions))
	}
	if len(suggestions) < 5 {
		t.Errorf("expected 5 suggestions for prefix 'a' (many words start with a), got %d", len(suggestions))
	}
}

func TestAutocompletePrefix_LIKEMetacharacterEscaped(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	// "%" is a LIKE wildcard — without escaping it would match all lemmas.
	// With proper escaping it should match nothing (no lemma starts with "%").
	suggestions, err := AutocompletePrefix(database, "%%", 10)
	if err != nil {
		t.Fatalf("AutocompletePrefix('%%%%', 10) returned error: %v", err)
	}
	if len(suggestions) != 0 {
		t.Errorf("expected 0 suggestions for metacharacter prefix '%%%%', got %d", len(suggestions))
	}

	// "_a" without escaping would match any two-char prefix + "a" — lots of results.
	// With escaping it should match nothing (no lemma starts with literal "_a").
	suggestions, err = AutocompletePrefix(database, "_a", 10)
	if err != nil {
		t.Fatalf("AutocompletePrefix('_a', 10) returned error: %v", err)
	}
	if len(suggestions) != 0 {
		t.Errorf("expected 0 suggestions for metacharacter prefix '_a', got %d", len(suggestions))
	}
}

func TestAutocompletePrefix_CaseInsensitive(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	suggestions, err := AutocompletePrefix(database, "FIR", 10)
	if err != nil {
		t.Fatalf("AutocompletePrefix('FIR', 10) returned error: %v", err)
	}

	found := false
	for _, s := range suggestions {
		if s.Word == "fire" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected 'fire' among suggestions for uppercase prefix 'FIR'")
	}
}

func TestGetLookup_EnrichmentFields(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	result, err := GetLookup(database, "fire")
	if err != nil {
		t.Fatalf("GetLookup(fire) returned error: %v", err)
	}

	// Verify that each sense has the enrichment fields (may be empty for v1 data).
	// The struct must expose Register, Connotation, and UsageExample.
	for i, sense := range result.Senses {
		// Access the fields to confirm they exist on the struct.
		// With v1 data these are expected to be empty strings.
		_ = sense.Register
		_ = sense.Connotation
		_ = sense.UsageExample
		// Antonyms must be initialised as an empty slice, not nil.
		if sense.Relations.Antonyms == nil {
			t.Errorf("sense[%d] Relations.Antonyms should be initialised (empty slice), got nil", i)
		}
	}

	// If any enrichment data IS present, validate its values.
	validRegisters := map[string]bool{"": true, "formal": true, "neutral": true, "informal": true, "slang": true}
	validConnotations := map[string]bool{"": true, "positive": true, "neutral": true, "negative": true}
	for i, sense := range result.Senses {
		if !validRegisters[sense.Register] {
			t.Errorf("sense[%d] has invalid Register %q", i, sense.Register)
		}
		if !validConnotations[sense.Connotation] {
			t.Errorf("sense[%d] has invalid Connotation %q", i, sense.Connotation)
		}
	}
}

func TestGetLookup_Collocations(t *testing.T) {
	database := openTestDB(t)
	defer database.Close()

	result, err := GetLookup(database, "fire")
	if err != nil {
		t.Fatalf("GetLookup(fire) returned error: %v", err)
	}

	// "fire" has 324 syntagms — at least some senses must have collocations.
	hasCollocations := false
	for _, sense := range result.Senses {
		if len(sense.Collocations) > 0 {
			hasCollocations = true
			// Verify each collocation has required fields.
			for _, col := range sense.Collocations {
				if col.Word == "" {
					t.Errorf("collocation in sense %s has empty Word", sense.SynsetID)
				}
				if col.SynsetID == "" {
					t.Errorf("collocation in sense %s has empty SynsetID", sense.SynsetID)
				}
			}
			// No more than 10 collocations per sense.
			if len(sense.Collocations) > 10 {
				t.Errorf("sense %s has %d collocations, expected at most 10", sense.SynsetID, len(sense.Collocations))
			}
		}
	}
	if !hasCollocations {
		t.Error("expected at least one sense of 'fire' to have collocations")
	}

	// Collocations must not contain duplicate words within a sense.
	for _, sense := range result.Senses {
		seen := map[string]bool{}
		for _, col := range sense.Collocations {
			if seen[col.Word] {
				t.Errorf("sense %s has duplicate collocation word %q", sense.SynsetID, col.Word)
			}
			seen[col.Word] = true
		}
	}
}
