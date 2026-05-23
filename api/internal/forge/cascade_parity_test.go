// Scoring-math parity test against the Python reference.
//
// This test exists because the Go /forge/suggest endpoint cannot exercise
// the same code paths the Python evaluate_cascade does — the Go endpoint
// only surfaces candidates that share at least one curated cluster between
// source-primary-synset and vehicle-primary-synset, while Python's
// evaluate_cascade_pair scores any synset pair handed to it.  Broadening
// the Go candidate set is the M04 — Cosine-Sim Candidate Generation
// milestone (see docs/roadmap/M04-cosine-candidate-gen-roadmap.md).
//
// Pending M04, we still need confidence that the Go scoring math itself
// matches the Python ground truth.  This test resolves each smoke pair
// to its primary synset_ids the same way Python's lookup_primary_synset
// does (curated-vocab least-polysemous → lemmas first-by-synset-id),
// looks up concreteness/properties/centroids the same way the handler
// would, calls forge.EvaluateCascadePair directly, and diffs against the
// pinned crib values to ±1e-6.
//
// Crib: docs/plans/2026-05-21-m03-s05-smoke-test-crib.md
package forge_test

import (
	"database/sql"
	"math"
	"testing"

	_ "github.com/mattn/go-sqlite3"

	"github.com/snailuj/metaforge/internal/db"
	"github.com/snailuj/metaforge/internal/forge"
)

const testDBPath = "../../../data-pipeline/output/lexicon_v2.db"

// cribEntry is one row from the crib's Python ground-truth JSON.
type cribEntry struct {
	topic, vehicle              string
	topicSynset, vehicleSynset  string
	status                      forge.CascadeStatus
	finalScore, ortonyScore     *float64
	cosineDistance, reRankBonus *float64
}

func ptr(v float64) *float64 { return &v }

// crib pins the Python evaluate_cascade.evaluate_cascade_pair output for
// the 8 smoke pairs.  These are the literal values from the JSON block in
// docs/plans/2026-05-21-m03-s05-smoke-test-crib.md — DO NOT round.
//
// Generated 2026-05-21 against data-pipeline/output/lexicon_v2.db (curated
// × enriched 99.2%, curated × centroid 99.3%).
var crib = []cribEntry{
	{topic: "anger", vehicle: "fire",
		topicSynset: "30227", vehicleSynset: "50554",
		status:         forge.CascadeStatusScored,
		finalScore:     ptr(0.3264111093603957),
		ortonyScore:    ptr(0.0),
		cosineDistance: ptr(0.25133655420750467),
		reRankBonus:    ptr(0.3264111093603957)},
	{topic: "idea", vehicle: "light",
		topicSynset: "64981", vehicleSynset: "44464",
		status:         forge.CascadeStatusScored,
		finalScore:     ptr(0.2483492844771258),
		ortonyScore:    ptr(0.0),
		cosineDistance: ptr(0.19122894904738685),
		reRankBonus:    ptr(0.2483492844771258)},
	{topic: "time", vehicle: "money",
		topicSynset: "445", vehicleSynset: "94024",
		status:         forge.CascadeStatusScored,
		finalScore:     ptr(0.31237238468193407),
		ortonyScore:    ptr(0.0),
		cosineDistance: ptr(0.24052673620508924),
		reRankBonus:    ptr(0.31237238468193407)},
	{topic: "argument", vehicle: "war",
		topicSynset: "67993", vehicleSynset: "15970",
		status: forge.CascadeStatusGateDropped},
	{topic: "life", vehicle: "journey",
		topicSynset: "92", vehicleSynset: "31055",
		status: forge.CascadeStatusGateDropped},
	{topic: "truth", vehicle: "hammer",
		topicSynset: "64180", vehicleSynset: "28753",
		status:         forge.CascadeStatusScored,
		finalScore:     ptr(0.26667097125952566),
		ortonyScore:    ptr(0.0),
		cosineDistance: ptr(0.20533664786983474),
		reRankBonus:    ptr(0.26667097125952566)},
	{topic: "silence", vehicle: "velvet",
		topicSynset: "59903", vehicleSynset: "57528",
		status: forge.CascadeStatusNoProperties},
	{topic: "cat", vehicle: "feline",
		topicSynset: "81628", vehicleSynset: "46156",
		status: forge.CascadeStatusGateDropped},
}

func TestCascadeParity_GoMatchesPythonGroundTruth(t *testing.T) {
	database, err := db.Open(testDBPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer database.Close()

	cache, err := db.LoadCascadeCache(database)
	if err != nil {
		t.Fatalf("LoadCascadeCache: %v", err)
	}

	cfg := forge.DefaultCascadeConfig()
	const tolerance = 1e-6

	for _, c := range crib {
		c := c
		t.Run(c.topic+"/"+c.vehicle, func(t *testing.T) {
			// 1. Resolve primary synsets.
			topicID, err := resolvePrimarySynset(database, c.topic)
			if err != nil {
				t.Fatalf("resolve topic %q: %v", c.topic, err)
			}
			vehicleID, err := resolvePrimarySynset(database, c.vehicle)
			if err != nil {
				t.Fatalf("resolve vehicle %q: %v", c.vehicle, err)
			}
			// Cross-check against crib's pinned synset IDs — drift here means
			// the DB rebuilt with a different lemma ordering, in which case
			// the crib needs regenerating, NOT silent acceptance.
			if topicID != c.topicSynset {
				t.Errorf("topic synset drift: crib=%s, resolved=%s — DB or lookup logic changed", c.topicSynset, topicID)
			}
			if vehicleID != c.vehicleSynset {
				t.Errorf("vehicle synset drift: crib=%s, resolved=%s", c.vehicleSynset, vehicleID)
			}

			// 2. Look up properties + concreteness + centroids.
			propsByID, err := db.GetSynsetClusterPropertiesBatch(database, []string{topicID, vehicleID})
			if err != nil {
				t.Fatalf("props batch: %v", err)
			}

			var tConc, vConc *float64
			if v, ok := cache.Concreteness[topicID]; ok {
				tConc = &v
			}
			if v, ok := cache.Concreteness[vehicleID]; ok {
				vConc = &v
			}

			res := forge.EvaluateCascadePair(forge.CascadeInputs{
				TopicConcreteness:   tConc,
				VehicleConcreteness: vConc,
				TopicProperties:     propsByID[topicID],
				VehicleProperties:   propsByID[vehicleID],
				TopicCentroid:       cache.Centroids[topicID],
				VehicleCentroid:     cache.Centroids[vehicleID],
			}, cfg)

			// 3. Verify status matches.
			if res.Status != c.status {
				t.Errorf("status: want %s, got %s", c.status, res.Status)
				return
			}

			// 4. For scored entries, diff each numeric field.
			if c.status == forge.CascadeStatusScored {
				diffField(t, "final_score", c.finalScore, res.FinalScore, tolerance)
				diffField(t, "ortony_score", c.ortonyScore, res.OrtonyScore, tolerance)
				diffField(t, "cosine_distance", c.cosineDistance, res.CosineDistance, tolerance)
				diffField(t, "re_rank_bonus", c.reRankBonus, res.ReRankBonus, tolerance)
			}
		})
	}
}

func diffField(t *testing.T, name string, want, got *float64, tol float64) {
	t.Helper()
	if want == nil && got == nil {
		return
	}
	if want == nil || got == nil {
		t.Errorf("%s: nil mismatch (want=%v got=%v)", name, want, got)
		return
	}
	if math.Abs(*want-*got) > tol {
		t.Errorf("%s: want %v, got %v, delta %.2e (tol %.0e)", name, *want, *got, math.Abs(*want-*got), tol)
	}
}

// resolvePrimarySynset mirrors data-pipeline/scripts/evaluate_aptness.py
// lookup_primary_synset:
//   1. Prefer the least-polysemous entry from property_vocab_curated.
//   2. Fall back to the first synset in lemmas (ordered by synset_id).
func resolvePrimarySynset(database *sql.DB, lemma string) (string, error) {
	var synsetID string
	err := database.QueryRow(
		"SELECT synset_id FROM property_vocab_curated WHERE LOWER(lemma) = LOWER(?) ORDER BY polysemy ASC LIMIT 1",
		lemma,
	).Scan(&synsetID)
	if err == nil {
		return synsetID, nil
	}
	if err != sql.ErrNoRows {
		return "", err
	}
	err = database.QueryRow(
		"SELECT synset_id FROM lemmas WHERE LOWER(lemma) = LOWER(?) ORDER BY synset_id LIMIT 1",
		lemma,
	).Scan(&synsetID)
	return synsetID, err
}
