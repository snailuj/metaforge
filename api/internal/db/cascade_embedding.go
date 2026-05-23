// Cascade-embedding-band candidate generator. Brute-force cosine scan
// over the in-memory CascadeCache.Centroids cache. Zero new DB
// round-trips on the hot path — the only DB work is a primary-synset
// resolution and a batched target-side synsets row lookup.
package db

import (
	"database/sql"
	"fmt"
	"log/slog"
	"math"
	"sort"
	"strings"

	"github.com/snailuj/metaforge/internal/forge"
)

// embeddingHit is the intermediate per-candidate record produced by the
// cosine scan, before the synsets-row lookup turns it into a full
// CascadeCandidate.
type embeddingHit struct {
	synsetID string
	distance float64
}

// scanEmbeddingBand walks every entry in cache.Centroids, computes
// cosine distance against the topic centroid (passed explicitly so the
// caller controls which sense provides the "topic" vector), filters
// to [dMin, dMax] (both inclusive), and returns the topK nearest by
// ascending distance. Every entry whose ID is in `excludeIDs` is
// skipped (typically: every sense of the topic lemma, to prevent
// "anger is like anger" leakage on polysemous topics).
// Returns nil when the topic centroid is nil — caller must treat nil
// as "embedding path unavailable for this lemma".
func scanEmbeddingBand(cache *CascadeCache, topic []float32, excludeIDs map[string]struct{}, dMin, dMax float64, topK int) []embeddingHit {
	if topic == nil {
		return nil
	}
	// Precompute topic norm once — calling forge.CascadeCosineDistance
	// inside the 35k-iteration scan recomputes Σ topic[i]² + math.Sqrt
	// per call (~12M wasted multiplies per request). Hot-path lever.
	var topicSqSum float64
	for _, v := range topic {
		topicSqSum += float64(v) * float64(v)
	}
	topicNorm := math.Sqrt(topicSqSum)
	if topicNorm == 0 {
		// Pipeline contract violation: a non-nil centroid with zero
		// norm means cache load accepted a degenerate vector. Cache
		// load's malformed-blob filter should have rejected this — if
		// we reach here, the contract drifted. Log loud (Error) so
		// operators see the signal; return nil so the caller falls
		// back to cluster-only behaviour for this request.
		slog.Error("scanEmbeddingBand zero-norm topic centroid — pipeline contract violation",
			"topic_dim", len(topic))
		return nil
	}
	hits := make([]embeddingHit, 0, 64)
	for id, vec := range cache.Centroids {
		if _, excluded := excludeIDs[id]; excluded {
			continue
		}
		d, ok := forge.CascadeCosineDistanceWithANorm(topic, topicNorm, vec)
		if !ok {
			// Dimension mismatch or zero-norm — skip silently; the
			// load-side log already flagged the malformed entry.
			continue
		}
		if d < dMin || d > dMax {
			continue
		}
		hits = append(hits, embeddingHit{synsetID: id, distance: d})
	}
	sort.SliceStable(hits, func(i, j int) bool {
		if hits[i].distance != hits[j].distance {
			return hits[i].distance < hits[j].distance
		}
		// Tiebreak on synsetID for deterministic TopK truncation under
		// distance ties — without this, the topK cut varies between
		// requests due to Go's randomised map iteration order.
		return hits[i].synsetID < hits[j].synsetID
	})
	if len(hits) > topK {
		hits = hits[:topK]
	}
	return hits
}

// ForgeEmbeddingConfig is the per-call shape passed by the handler. We
// keep it independent of forge.CascadeConfig so the embedding generator
// has no compile-time dependency on the full cascade config struct.
type ForgeEmbeddingConfig struct {
	DMin float64
	DMax float64
	TopK int
}

// GetForgeCascadeCandidatesByEmbedding resolves the topic's primary
// synset, reads its centroid from the cache, brute-force-scans every
// other centroid for cosine distance ∈ [DMin, DMax], and returns the
// TopK nearest as CascadeCandidate rows with Source=SourceEmbedding,
// SalienceSum=0, ContrastCount=0, SharedProps=nil. Target-side
// definition/POS come from one batched synsets query.
//
// Returns ErrLemmaNotFound when the lemma has no curated source synset
// (matches the cluster path's contract). Returns (nil, nil) for two
// distinct empty-result cases:
//  1. the resolved topic synset has no centroid in the cache — defensive
//     only; 100% of enriched synsets have centroids by construction.
//     Differentiated via the slog.Debug "no topic centroid …" record.
//  2. the cosine scan found no synsets inside [DMin, DMax] — a legitimate
//     "no neighbours in band" outcome; tighten the band to fix.
// Callers that need to distinguish the two should read the timing
// record on cascade_embedding_query — Task 7 attaches the no_centroid
// flag there.
func GetForgeCascadeCandidatesByEmbedding(
	database *sql.DB,
	cache *CascadeCache,
	lemma string,
	cfg ForgeEmbeddingConfig,
) ([]CascadeCandidate, error) {
	topicID, err := resolvePrimaryCuratedSynset(database, lemma)
	if err != nil {
		return nil, err
	}
	siblings, err := resolveLemmaSiblingSynsets(database, lemma)
	if err != nil {
		return nil, err
	}
	topicCentroid := cache.Centroids[topicID]
	hits := scanEmbeddingBand(cache, topicCentroid, siblings, cfg.DMin, cfg.DMax, cfg.TopK)
	if hits == nil {
		// Topic resolved but no centroid in the cache. Pipeline contract
		// says every enriched synset has a centroid, so this is rare —
		// log Debug and return (nil, nil) so the handler falls back to
		// cluster-only behaviour for this request.
		slog.Debug("no topic centroid for embedding scan", "lemma", lemma, "synset", topicID)
		return nil, nil
	}
	if len(hits) == 0 {
		return nil, nil
	}

	topicRow, err := getSynsetRow(database, topicID)
	if err != nil {
		return nil, fmt.Errorf("topic synset row %s: %w", topicID, err)
	}

	targetIDs := make([]string, len(hits))
	for i, h := range hits {
		targetIDs[i] = h.synsetID
	}
	targetRows, err := getSynsetRowsBatch(database, targetIDs)
	if err != nil {
		return nil, fmt.Errorf("target synsets batch: %w", err)
	}

	out := make([]CascadeCandidate, 0, len(hits))
	for _, h := range hits {
		row, ok := targetRows[h.synsetID]
		if !ok {
			// Centroid present in cache but synset row missing — pipeline
			// contract violation; skip the candidate rather than crash.
			slog.Error("embedding hit has no synsets row", "synset", h.synsetID)
			continue
		}
		out = append(out, CascadeCandidate{
			SynsetID:         h.synsetID,
			Word:             row.lemma,
			POS:              row.pos,
			Definition:       row.definition,
			SalienceSum:      0,
			ContrastCount:    0,
			SharedProps:      nil,
			SourceSynsetID:   topicID,
			SourceDefinition: topicRow.definition,
			SourcePOS:        topicRow.pos,
			Source:           forge.SourceEmbedding,
		})
	}
	return out, nil
}

// resolvePrimaryCuratedSynset picks the single primary-sense synset for
// the embedding-path topic vector. The most-curated-rows-wins heuristic
// is a coarse stand-in for polysemy-ASC (see the SQL comment on the
// correlated-COUNT cost in cascade.go). This is INTENTIONALLY narrower
// than GetForgeCascadeCandidatesByLemma, which iterates every sense the
// lemma has. The asymmetry is acceptable in v1: the cosine band finds
// neighbours of the central sense, while the cluster path still
// produces candidates for niche senses via the structural CTE. Multi-
// sense ANN candidate generation is parked as M04 v2 (see PIPELINE
// backlog). Returns ErrLemmaNotFound when the lemma has no curated
// synset at all.
func resolvePrimaryCuratedSynset(database *sql.DB, lemma string) (string, error) {
	var id string
	err := database.QueryRow(`
		SELECT l.synset_id
		FROM lemmas l
		JOIN synset_properties_curated spc ON spc.synset_id = l.synset_id
		WHERE l.lemma = ?
		GROUP BY l.synset_id
		ORDER BY COUNT(*) DESC
		LIMIT 1
	`, lemma).Scan(&id)
	if err == sql.ErrNoRows {
		return "", fmt.Errorf("%w: %s", ErrLemmaNotFound, lemma)
	}
	if err != nil {
		return "", fmt.Errorf("resolvePrimaryCuratedSynset(%q): %w", lemma, err)
	}
	return id, nil
}

// resolveLemmaSiblingSynsets returns the set of all synset_ids where
// the lemma appears. Used by GetForgeCascadeCandidatesByEmbedding to
// build a self-match exclusion set covering every sense of the topic
// lemma — mirrors the cluster path's NOT IN (source_synsets) filter.
func resolveLemmaSiblingSynsets(database *sql.DB, lemma string) (map[string]struct{}, error) {
	rows, err := database.Query("SELECT synset_id FROM lemmas WHERE lemma = ?", lemma)
	if err != nil {
		return nil, fmt.Errorf("resolveLemmaSiblingSynsets(%q): %w", lemma, err)
	}
	defer rows.Close()
	out := make(map[string]struct{}, 8)
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return nil, fmt.Errorf("scan sibling synset: %w", err)
		}
		out[id] = struct{}{}
	}
	return out, rows.Err()
}

// synsetRow is the minimal projection we need on the embedding path —
// definition, POS, and the polysemy-ASC primary lemma for display.
type synsetRow struct {
	pos        string
	definition string
	lemma      string
}

func getSynsetRow(database *sql.DB, id string) (synsetRow, error) {
	var r synsetRow
	err := database.QueryRow(`
		SELECT s.pos, s.definition,
		       (SELECT lemma FROM lemmas WHERE synset_id = s.synset_id ORDER BY lemma LIMIT 1) as lemma
		FROM synsets s WHERE s.synset_id = ?
	`, id).Scan(&r.pos, &r.definition, &r.lemma)
	if err != nil {
		return r, err
	}
	return r, nil
}

// getSynsetRowsBatch fetches POS/definition/primary-lemma for many
// synset ids in one IN-clause query. Returns a map id→row; missing
// ids are absent from the result map.
func getSynsetRowsBatch(database *sql.DB, ids []string) (map[string]synsetRow, error) {
	out := make(map[string]synsetRow, len(ids))
	if len(ids) == 0 {
		return out, nil
	}
	placeholders := make([]string, len(ids))
	args := make([]interface{}, len(ids))
	for i, id := range ids {
		placeholders[i] = "?"
		args[i] = id
	}
	q := `
		SELECT s.synset_id, s.pos, s.definition,
		       (SELECT lemma FROM lemmas WHERE synset_id = s.synset_id ORDER BY lemma LIMIT 1) as lemma
		FROM synsets s WHERE s.synset_id IN (` + strings.Join(placeholders, ",") + `)`
	rows, err := database.Query(q, args...)
	if err != nil {
		return nil, fmt.Errorf("getSynsetRowsBatch query: %w", err)
	}
	defer rows.Close()
	for rows.Next() {
		var id string
		var r synsetRow
		if err := rows.Scan(&id, &r.pos, &r.definition, &r.lemma); err != nil {
			return nil, fmt.Errorf("scan synset row: %w", err)
		}
		out[id] = r
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate synset rows: %w", err)
	}
	return out, nil
}
