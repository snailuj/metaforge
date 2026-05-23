// Cascade-embedding-band candidate generator. Brute-force cosine scan
// over the in-memory CascadeCache.Centroids cache. Zero new DB
// round-trips on the hot path — the only DB work is a primary-synset
// resolution and a batched target-side synsets row lookup.
package db

import (
	"sort"

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
// cosine distance against the topic centroid, filters to [dMin, dMax]
// (both inclusive), and returns the topK nearest by ascending distance.
// Self-match (topicSynsetID == entry) is dropped regardless of band.
// Returns nil when the topic centroid is absent from the cache —
// caller must treat nil as "embedding path unavailable for this lemma".
func scanEmbeddingBand(cache *CascadeCache, topicSynsetID string, dMin, dMax float64, topK int) []embeddingHit {
	topic, ok := cache.Centroids[topicSynsetID]
	if !ok {
		return nil
	}
	hits := make([]embeddingHit, 0, 64)
	for id, v := range cache.Centroids {
		if id == topicSynsetID {
			continue
		}
		d, ok := forge.CascadeCosineDistance(topic, v)
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
	sort.Slice(hits, func(i, j int) bool {
		return hits[i].distance < hits[j].distance
	})
	if len(hits) > topK {
		hits = hits[:topK]
	}
	return hits
}
