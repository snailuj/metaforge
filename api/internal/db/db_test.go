// api/internal/db/db_test.go
package db

import (
	"bytes"
	"database/sql"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"testing"

	_ "github.com/mattn/go-sqlite3"
)

func TestOpenDatabase(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	var count int
	err = db.QueryRow("SELECT COUNT(*) FROM synsets").Scan(&count)
	if err != nil {
		t.Fatalf("Failed to query synsets: %v", err)
	}

	if count < 100000 {
		t.Errorf("Expected >100k synsets, got %d", count)
	}
}

func TestGetSynsetWithEnrichment(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// Find a synset with properties from synset_properties junction table
	var synsetID string
	err = db.QueryRow(`
		SELECT sp.synset_id
		FROM synset_properties sp
		GROUP BY sp.synset_id
		HAVING COUNT(*) >= 3
		LIMIT 1
	`).Scan(&synsetID)
	if err != nil {
		t.Fatalf("No synset with properties: %v", err)
	}

	synset, err := GetSynset(db, synsetID)
	if err != nil {
		t.Fatalf("Failed to get synset %s: %v", synsetID, err)
	}

	if synset.ID != synsetID {
		t.Errorf("Expected %s, got %s", synsetID, synset.ID)
	}

	if len(synset.Properties) == 0 {
		t.Error("Expected properties from synset_properties junction table")
	}
}

// testDBPathV2 points to the v2 database
const testDBPathV2 = "../../../data-pipeline/output/lexicon_v2.db"

func TestGetLemmaEmbedding_NotFound(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	emb, err := GetLemmaEmbedding(db, "xyzzynotaword12345")
	if err != nil {
		t.Fatalf("Expected nil error for missing lemma, got: %v", err)
	}
	if emb != nil {
		t.Error("Expected nil embedding for missing lemma")
	}
}

func TestGetForgeMatchesCuratedByLemma_ReturnsErrLemmaNotFound(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	_, err = GetForgeMatchesCuratedByLemma(db, "xyzzynotaword12345", 50)
	if err == nil {
		t.Fatal("Expected error for nonexistent lemma, got nil")
	}
	if !errors.Is(err, ErrLemmaNotFound) {
		t.Errorf("Expected ErrLemmaNotFound, got: %v", err)
	}
}

func TestGetForgeMatchesCuratedByLemma_LimitReturnsDistinctCandidates(t *testing.T) {
	// D16 regression test: mirrors the cascade-side PR1.1 fix. The legacy
	// `JOIN lemmas l ON l.synset_id = bs.target_id` row-amplifies before
	// `LIMIT`, so a broad-coverage lemma like 'anger' was truncated to
	// roughly half the requested limit by per-target lemma duplicates.
	// Asserts the post-fix shape: distinct synsets and a non-truncated
	// candidate count.
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	matches, err := GetForgeMatchesCuratedByLemma(db, "anger", 50)
	if err != nil {
		t.Fatalf("GetForgeMatchesCuratedByLemma: %v", err)
	}
	t.Logf("anger limit=50 returned %d distinct candidates", len(matches))
	if len(matches) < 40 {
		t.Errorf("expected at least 40 distinct candidates for 'anger' limit=50, got %d "+
			"(pre-fix legacy path truncated to ~half due to lemma row-amplification before LIMIT)",
			len(matches))
	}
	seen := make(map[string]bool)
	for _, m := range matches {
		if seen[m.SynsetID] {
			t.Errorf("duplicate synset in legacy matches: %s", m.SynsetID)
		}
		seen[m.SynsetID] = true
	}
}

func TestGetLemmaEmbeddingsBatch_QueryFaultEscalates(t *testing.T) {
	// Pins the pre-existing Query-fault escalation path: wrong-column-shape
	// table makes db.Query return "no such column: embedding" before the
	// rows loop is reached. Not a regression test for the SF1 per-row
	// Scan-escalation branch (that branch is hard to reach without a
	// custom sql/driver stub since SQLite's rows.Scan on (TEXT, BLOB)
	// rarely fails) — see TestGetLemmaEmbeddingsBatch_MalformedBlobEscalates
	// below which pins the SF2 malformed-tally branch that DOES exercise
	// the post-loop escalation introduced by round 1.
	db, err := sql.Open("sqlite3", ":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if _, err := db.Exec(`CREATE TABLE lemma_embeddings (lemma TEXT PRIMARY KEY, vector_garbled BLOB);`); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`INSERT INTO lemma_embeddings VALUES ('anger', NULL)`); err != nil {
		t.Fatal(err)
	}

	_, err = GetLemmaEmbeddingsBatch(db, []string{"anger", "fire"})
	if err == nil {
		t.Fatal("expected error on wrong-column-shape lemma_embeddings, got nil")
	}
}

func TestGetLemmaEmbeddingsBatch_MalformedBlobEscalates(t *testing.T) {
	// SF2-batch pin: the post-loop `if malformed > 0` escalation added in
	// round 1 must surface as a non-nil error and discard the partial
	// result map. handleSuggestLegacy relies on this to route to 500 on
	// the candidate-batch path when a pipeline-contract violation makes
	// it through enrichment.
	db, err := sql.Open("sqlite3", ":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if _, err := db.Exec(`CREATE TABLE lemma_embeddings (lemma TEXT PRIMARY KEY, embedding BLOB);`); err != nil {
		t.Fatal(err)
	}
	// 4-byte blob — clearly not EmbeddingDim*4 floats. Scan succeeds,
	// BlobToFloats returns nil, the malformed tally increments, post-loop
	// escalation fires.
	if _, err := db.Exec(`INSERT INTO lemma_embeddings VALUES ('anger', x'01020304')`); err != nil {
		t.Fatal(err)
	}

	result, err := GetLemmaEmbeddingsBatch(db, []string{"anger"})
	if err == nil {
		t.Fatalf("expected error on malformed embedding blob, got nil result=%v", result)
	}
	if result != nil {
		t.Errorf("expected nil map alongside error (partial result discarded), got %v", result)
	}
}

func TestGetLemmaEmbedding_MalformedBlobEscalates(t *testing.T) {
	// SF2 pin: a malformed-dim BLOB is a pipeline contract violation
	// indistinguishable from the benign (nil, nil) absence path pre-fix.
	// Must now escalate so the handler can 500 instead of silently
	// returning domainDist=0.
	db, err := sql.Open("sqlite3", ":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if _, err := db.Exec(`CREATE TABLE lemma_embeddings (lemma TEXT PRIMARY KEY, embedding BLOB);`); err != nil {
		t.Fatal(err)
	}
	// 7-byte blob — clearly not EmbeddingDim*4 floats.
	if _, err := db.Exec(`INSERT INTO lemma_embeddings VALUES ('anger', x'01020304050607')`); err != nil {
		t.Fatal(err)
	}

	vec, err := GetLemmaEmbedding(db, "anger")
	if err == nil {
		t.Fatalf("expected error on malformed embedding blob, got nil vec=%v", vec)
	}
	if vec != nil {
		t.Errorf("expected nil vec alongside error, got %v", vec)
	}
}

func TestGetLemmaEmbeddingsBatch_MalformedBlob_LogCapBounded(t *testing.T) {
	// R4-OWN-1 / R4-ST1 pin: round-3 widened the malformed-blob log
	// throttle from "first occurrence only" to "first malformedLogCap
	// occurrences with explicit occurrence index". Insert 12 malformed
	// rows (> cap of 10) and assert (i) the function still escalates
	// with the full count, (ii) the partial map is discarded, (iii) exactly
	// `malformedLogCap` Error log records emit (R5-OWN-2 pin — pins the
	// cap *value*, not just the count), (iv) exactly 1 cap-boundary Warn
	// marker fires at the transition (R5-OWN-1 / R5-ST1 pin — pins the
	// marker added in R4 commit 72bd9a0b).
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelDebug})))
	defer slog.SetDefault(prev)

	db, err := sql.Open("sqlite3", ":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if _, err := db.Exec(`CREATE TABLE lemma_embeddings (lemma TEXT PRIMARY KEY, embedding BLOB);`); err != nil {
		t.Fatal(err)
	}

	lemmas := make([]string, 12)
	for i := 0; i < 12; i++ {
		lemma := fmt.Sprintf("bad_%02d", i)
		lemmas[i] = lemma
		// 4-byte blob — wrong size, BlobToFloats returns nil.
		if _, err := db.Exec(`INSERT INTO lemma_embeddings VALUES (?, x'01020304')`, lemma); err != nil {
			t.Fatal(err)
		}
	}

	result, err := GetLemmaEmbeddingsBatch(db, lemmas)
	if err == nil {
		t.Fatal("expected error on 12 malformed blobs, got nil")
	}
	if result != nil {
		t.Errorf("expected nil map alongside error, got %v", result)
	}
	// The aggregate-count error message must report all 12, not just the
	// 10 that were logged.
	if !strings.Contains(err.Error(), "12 malformed embedding blobs") {
		t.Errorf("aggregate count past cap not surfaced in error: %v", err)
	}

	// Pin the cap-value behaviour: exactly malformedLogCap (=10) Error
	// records emit, then suppression kicks in. Counted via the slog JSON
	// "msg":"malformed lemma embedding blob" substring.
	logBytes := buf.Bytes()
	errorMarkerCount := bytes.Count(logBytes, []byte(`"msg":"malformed lemma embedding blob"`))
	if errorMarkerCount != malformedLogCap {
		t.Errorf("expected exactly %d malformed-blob Error records (cap value), got %d",
			malformedLogCap, errorMarkerCount)
	}

	// Pin the cap-boundary Warn marker (R4-S2 / 72bd9a0b): fires exactly
	// once when malformed transitions from cap-1 to cap.
	capMarkerCount := bytes.Count(logBytes, []byte(`"msg":"malformed lemma embedding log cap reached`))
	if capMarkerCount != 1 {
		t.Errorf("expected exactly 1 cap-boundary Warn record, got %d", capMarkerCount)
	}
}

func TestGetSynsetIDForLemma(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// "fire" should exist and return a synset ID
	synsetID, err := GetSynsetIDForLemma(db, "fire")
	if err != nil {
		t.Fatalf("GetSynsetIDForLemma(fire) failed: %v", err)
	}
	if synsetID == "" {
		t.Error("Expected non-empty synset ID for 'fire'")
	}
}

func TestGetSynsetIDForLemmaNotFound(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	_, err = GetSynsetIDForLemma(db, "xyzzynotaword12345")
	if err == nil {
		t.Error("Expected error for nonexistent lemma")
	}
}

func TestGetLemmaForSynset(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// First get a valid synset ID
	synsetID, err := GetSynsetIDForLemma(db, "fire")
	if err != nil {
		t.Fatalf("GetSynsetIDForLemma(fire) failed: %v", err)
	}

	lemma, err := GetLemmaForSynset(db, synsetID)
	if err != nil {
		t.Fatalf("GetLemmaForSynset(%s) failed: %v", synsetID, err)
	}
	if lemma == "" {
		t.Error("Expected non-empty lemma")
	}
}

func TestGetLemmaForSynsetNotFound(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	_, err = GetLemmaForSynset(db, "999999999")
	if err == nil {
		t.Error("Expected error for nonexistent synset")
	}
}

func TestGetSynsetNotFound(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	_, err = GetSynset(db, "999999999")
	if err == nil {
		t.Error("Expected error for nonexistent synset ID")
	}
}

func TestGetSynsetsNotFound(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// Nonexistent synset ID should return error
	_, err = GetSynset(db, "nonexistent99999")
	if err == nil {
		t.Error("Expected error for nonexistent synset ID")
	}
}

func TestGetSynsetsNoProperties(t *testing.T) {
	db, err := Open(testDBPathV2)
	if err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// Find a synset with no properties
	var synsetID string
	err = db.QueryRow(`
		SELECT s.synset_id
		FROM synsets s
		WHERE NOT EXISTS (
			SELECT 1 FROM synset_properties sp
			WHERE sp.synset_id = s.synset_id
		)
		LIMIT 1
	`).Scan(&synsetID)
	if err != nil {
		t.Skipf("No synset without properties found: %v", err)
	}

	synset, err := GetSynset(db, synsetID)
	if err != nil {
		t.Fatalf("GetSynset failed: %v", err)
	}

	// Synset should have no properties
	if len(synset.Properties) != 0 {
		t.Errorf("Expected 0 properties for synset %s, got %d", synsetID, len(synset.Properties))
	}
}
