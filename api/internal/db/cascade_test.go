package db

import (
	"testing"

	_ "github.com/mattn/go-sqlite3"
)

func TestGetSynsetClusterPropertiesBatch_ReturnsMapPerSynset(t *testing.T) {
	database, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	// Resolve two known-enriched lemmas to synset_ids.
	var fireID, waterID string
	if err := database.QueryRow(`
		SELECT l.synset_id FROM lemmas l
		JOIN synset_properties_curated spc ON spc.synset_id = l.synset_id
		WHERE l.lemma = 'fire' GROUP BY l.synset_id
		ORDER BY COUNT(*) DESC LIMIT 1
	`).Scan(&fireID); err != nil {
		t.Fatalf("resolve fire: %v", err)
	}
	if err := database.QueryRow(`
		SELECT l.synset_id FROM lemmas l
		JOIN synset_properties_curated spc ON spc.synset_id = l.synset_id
		WHERE l.lemma = 'water' GROUP BY l.synset_id
		ORDER BY COUNT(*) DESC LIMIT 1
	`).Scan(&waterID); err != nil {
		t.Fatalf("resolve water: %v", err)
	}

	out, err := GetSynsetClusterPropertiesBatch(database, []string{fireID, waterID})
	if err != nil {
		t.Fatalf("batch: %v", err)
	}
	if len(out[fireID]) == 0 {
		t.Errorf("expected non-empty props for fire/%s", fireID)
	}
	if len(out[waterID]) == 0 {
		t.Errorf("expected non-empty props for water/%s", waterID)
	}
	for cid, sal := range out[fireID] {
		if sal <= 0 {
			t.Errorf("fire/%d: non-positive salience %v", cid, sal)
		}
	}
}

func TestGetSynsetClusterPropertiesBatch_MissingSynsetsAbsentFromMap(t *testing.T) {
	database, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	out, err := GetSynsetClusterPropertiesBatch(database, []string{"not-a-real-id"})
	if err != nil {
		t.Fatalf("batch: %v", err)
	}
	if _, present := out["not-a-real-id"]; present {
		t.Error("missing synset must be absent from result map, not empty-mapped")
	}
}

func TestGetSynsetClusterPropertiesBatch_EmptyInputReturnsEmptyResult(t *testing.T) {
	database, err := Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	out, err := GetSynsetClusterPropertiesBatch(database, nil)
	if err != nil {
		t.Fatalf("batch nil: %v", err)
	}
	if len(out) != 0 {
		t.Errorf("nil input: want empty result, got %d entries", len(out))
	}
}
