// Package handler — cascadePipeline extracts the /forge/suggest cascade
// orchestration out of the 290-line handleSuggestCascade god-function
// (D24). Each method advances one phase (fetch → score → respond), and
// every terminal outcome flows through emit() — the single emission
// site for cascade_request_total timing + the "cascade request complete"
// slog.Info record. This eliminates the 6 paired stopTotal + slog.Info
// sites that accumulated across M04 review rounds and provides a
// natural home for the anomaly counters (D23).
package handler

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"

	"github.com/snailuj/metaforge/internal/db"
	"github.com/snailuj/metaforge/internal/forge"
	"github.com/snailuj/metaforge/internal/observe"
)

// cascadePipeline orchestrates one /forge/suggest cascade request.
// Each method advances the pipeline through one phase. The dispatcher
// (handleSuggestCascade) wires them in order: fetch → score → respond.
// Telemetry emission is centralised in emit() — every terminal outcome
// flows through one site, eliminating the paired stopTotal + slog.Info
// duplication that accumulated across M04 review rounds.
type cascadePipeline struct {
	h     *Handler
	word  string
	limit int

	// fetch-phase state
	cluster              []db.CascadeCandidate
	embedding            []db.CascadeCandidate
	candidates           []db.CascadeCandidate
	clusterLemmaNotFound bool

	// score-phase state
	propsByID map[string]map[int64]float64
	matches   []forge.Match

	// per-request observability aggregator
	anomalies cascadeAnomalies

	// per-source path counts populated during score()
	clusterOnly   int
	embeddingOnly int
	bothPaths     int

	// timing — internal to the pipeline; stopTotal stays open until
	// emit() closes it. closed guards against double-close in close().
	stopTotal func(extra ...any)
	closed    bool
}

// cascadeAnomalies aggregates per-request anomaly signals. Surfaces
// via Attrs() on every emit() call so production observability sees
// the same shape on every cascade request regardless of outcome.
type cascadeAnomalies struct {
	clusterConcretenessCacheMisses int
	embeddingConcretenessMisses    int
	emptyPropsBatchFlag            bool
	embeddingPathUnavailable       bool // D15: set when embedding ErrLemmaNotFound in union mode with cluster success
	embeddingDimMismatches         int  // D19: counter for ok==false in scanEmbeddingBand
}

// Attrs returns the structured-logging key/value pairs for the anomaly
// aggregator. Used by emit() to DRY the 6 paired stopTotal + slog.Info
// sites that accumulated across M04 review rounds.
func (a cascadeAnomalies) Attrs() []any {
	return []any{
		"cluster_concreteness_misses", a.clusterConcretenessCacheMisses,
		"embedding_no_concreteness", a.embeddingConcretenessMisses,
		"empty_props_batch", a.emptyPropsBatchFlag,
		"embedding_path_unavailable", a.embeddingPathUnavailable,
		"embedding_dim_mismatches", a.embeddingDimMismatches,
	}
}

// newCascadePipeline builds the pipeline struct, opens the
// cascade_request_total timer (NO-OP unless observe.Init is true), and
// emits the request-begin Debug record. The returned pipeline must be
// either driven to a terminal emit*() method or have close() called
// on it via defer — close() is a safety net for unexpected returns.
func newCascadePipeline(h *Handler, word string, limit int) *cascadePipeline {
	stopTotal := observe.Start("cascade_request_total")
	slog.Debug("cascade request begin", "word", word, "limit", limit)
	return &cascadePipeline{
		h:         h,
		word:      word,
		limit:     limit,
		stopTotal: stopTotal,
	}
}

// close is the deferred safety net. In normal control flow one of the
// emit*() helpers closes stopTotal explicitly; close() guards against
// programming errors where a method returns without invoking emit*().
// Idempotent — repeated calls do nothing.
func (p *cascadePipeline) close() {
	if p.closed {
		return
	}
	p.closed = true
	p.stopTotal("word", p.word, "outcome", "abandoned_no_emit")
	slog.Error("cascadePipeline closed without explicit emit — programming error",
		"word", p.word)
}

// fetch runs both candidate paths (cluster + embedding) per the active
// CandidateSources config, unions the results into p.candidates, and
// returns (outcome, status, err). status==http.StatusOK means
// "continue"; any other status means "respond with this error and stop".
func (p *cascadePipeline) fetch() (string, int, error) {
	var err error
	if p.h.cascadeConf.CandidateSources != forge.SourcesEmbedding {
		// Symmetric with the embedding-path stage timer below: only
		// emit cascade_candidates_query when the cluster path actually
		// runs. In embedding_only mode the cluster fetch is fully
		// skipped — no stage timer, no zero-count log noise.
		stopCand := observe.Start("cascade_candidates_query")
		p.cluster, err = db.GetForgeCascadeCandidatesByLemma(
			p.h.database, p.word, p.h.cascadeConf.ConcretenessThreshold, p.limit,
		)
		stopCand("word", p.word, "count", len(p.cluster))
	}
	// Track cluster-path ErrLemmaNotFound as a flag so union-mode can
	// defer the 404 decision until after the embedding path runs.
	if errors.Is(err, db.ErrLemmaNotFound) {
		p.clusterLemmaNotFound = true
		if p.h.cascadeConf.CandidateSources == forge.SourcesCluster {
			return "lemma_not_found", http.StatusNotFound, err
		}
		// In union mode, defer 404 decision until after embedding path.
	} else if err != nil {
		slog.Error("cascade candidate fetch failed", "word", p.word, "err", err)
		return "candidates_error", http.StatusInternalServerError, err
	}

	if p.h.cascadeConf.CandidateSources != forge.SourcesCluster {
		stopEmb := observe.Start("cascade_embedding_query")
		embCfg := db.ForgeEmbeddingConfig{
			DMin: p.h.cascadeConf.EmbeddingDMin,
			DMax: p.h.cascadeConf.EmbeddingDMax,
			TopK: p.h.cascadeConf.EmbeddingTopK,
		}
		p.embedding, err = db.GetForgeCascadeCandidatesByEmbedding(
			p.h.database, p.h.cache, p.word, embCfg, &p.anomalies.embeddingDimMismatches,
		)
		stopEmb("word", p.word, "count", len(p.embedding))
		if errors.Is(err, db.ErrLemmaNotFound) {
			// Only 404 if cluster path also failed (or embedding-only).
			if p.clusterLemmaNotFound || p.h.cascadeConf.CandidateSources == forge.SourcesEmbedding {
				return "lemma_not_found", http.StatusNotFound, err
			}
			// D15: union mode + cluster-success + embedding-fetch-fail —
			// embedding path is silently unavailable. Lift to the
			// anomaly aggregator so the final outcome log signals it
			// instead of normalising to outcome=scored with zero signal.
			p.anomalies.embeddingPathUnavailable = true
			p.embedding = nil
		} else if err != nil {
			slog.Error("cascade embedding fetch failed", "word", p.word, "err", err)
			return "embedding_error", http.StatusInternalServerError, err
		}
	}

	p.candidates = unionCandidates(p.cluster, p.embedding)
	slog.Debug("cascade candidates assembled",
		"word", p.word, "cluster", len(p.cluster), "embedding", len(p.embedding),
		"after_union", len(p.candidates))
	return "", http.StatusOK, nil
}

// score runs the batch props query and the scoring loop, populating
// p.matches. Returns (outcome, status, err) with the same semantics as
// fetch().
func (p *cascadePipeline) score() (string, int, error) {
	// Collect distinct synset_ids for one batch properties query.
	idSet := make(map[string]struct{}, 2*len(p.candidates))
	for _, c := range p.candidates {
		idSet[c.SourceSynsetID] = struct{}{}
		idSet[c.SynsetID] = struct{}{}
	}
	ids := make([]string, 0, len(idSet))
	for id := range idSet {
		ids = append(ids, id)
	}
	stopProps := observe.Start("cascade_batch_props_query")
	propsByID, err := db.GetSynsetClusterPropertiesBatch(p.h.database, ids)
	stopProps("word", p.word, "synset_ids", len(ids), "rows", len(propsByID))
	if err != nil {
		slog.Error("cascade batch properties fetch failed", "word", p.word, "err", err)
		return "batch_props_error", http.StatusInternalServerError, err
	}
	p.propsByID = propsByID
	if len(propsByID) == 0 {
		// R4-D1: previously a per-request Error log; now aggregated
		// onto cascade_request_total as empty_props_batch=true. The
		// runtime tripwire on synset_properties_curated catches the
		// truncation-at-startup case loudly; the in-flight case here
		// stays observable via the timing attr.
		p.anomalies.emptyPropsBatchFlag = true
		// Also emit unconditional Warn so empty-batch is visible
		// without the cascade-timing feature flag.
		slog.Warn("cascade batch props returned empty",
			"word", p.word,
			"candidate_count", len(p.candidates))
	}

	for _, c := range p.candidates {
		switch c.Source {
		case forge.SourceCluster:
			p.clusterOnly++
		case forge.SourceEmbedding:
			p.embeddingOnly++
		case forge.SourceBoth:
			p.bothPaths++
		}
	}

	stopScore := observe.Start("cascade_scoring_loop")
	var droppedNonScored int
	p.matches = make([]forge.Match, 0, len(p.candidates))
	for _, c := range p.candidates {
		// Concreteness from the in-memory cache — preserves the
		// *float64 absence-signal contract EvaluateCascadePair expects.
		var tConc, vConc *float64
		if v, ok := p.h.cache.Concreteness[c.SourceSynsetID]; ok {
			tConc = &v
		}
		if v, ok := p.h.cache.Concreteness[c.SynsetID]; ok {
			vConc = &v
		}
		// Cluster-path cache miss = SQL/cache divergence (Error).
		// Embedding-path cache miss = expected (no SQL join on
		// concreteness for the embedding path); count separately so
		// the post-loop Error fires only on cluster-path divergence.
		if tConc == nil || vConc == nil {
			if c.Source == forge.SourceCluster || c.Source == forge.SourceBoth {
				p.anomalies.clusterConcretenessCacheMisses++
			} else {
				p.anomalies.embeddingConcretenessMisses++
			}
		}
		topicCent := p.h.cache.Centroids[c.SourceSynsetID]
		vehCent := p.h.cache.Centroids[c.SynsetID]

		res := forge.EvaluateCascadePair(forge.CascadeInputs{
			TopicConcreteness:   tConc,
			VehicleConcreteness: vConc,
			TopicProperties:     propsByID[c.SourceSynsetID],
			VehicleProperties:   propsByID[c.SynsetID],
			TopicCentroid:       topicCent,
			VehicleCentroid:     vehCent,
		}, p.h.cascadeConf)

		// SQL CTE already filtered gate_dropped + missing_concreteness,
		// so the only attrition we can see here is no_properties.
		if res.Status != forge.CascadeStatusScored {
			droppedNonScored++
			continue
		}

		// Salience-based tier is meaningful for cluster-path rows;
		// embedding-only rows have SalienceSum=0 by construction, so
		// emitting "unlikely" would mislead UI consumers. Empty
		// TierName lets JSON omitempty drop the field.
		var (
			tier     forge.Tier
			tierName string
		)
		if c.Source != forge.SourceEmbedding {
			tier = forge.ClassifyTierCurated(c.SalienceSum, c.ContrastCount)
			tierName = tier.String()
		}
		p.matches = append(p.matches, forge.Match{
			SynsetID:         c.SynsetID,
			Word:             c.Word,
			Definition:       c.Definition,
			SharedProperties: c.SharedProps,
			OverlapCount:     int(c.SalienceSum),
			SalienceSum:      c.SalienceSum,
			Tier:             tier,
			TierName:         tierName,
			SourceSynsetID:   c.SourceSynsetID,
			SourceDefinition: c.SourceDefinition,
			SourcePOS:        c.SourcePOS,
			FinalScore:       res.FinalScore,
			CascadeStatus:    res.Status,
			GatePassed:       res.GatePassed,
			OrtonyScore:      res.OrtonyScore,
			CosineDistance:   res.CosineDistance,
			ReRankBonus:      res.ReRankBonus,
			Source:           c.Source,
		})
	}
	stopScore("word", p.word, "scored", len(p.matches), "dropped_non_scored", droppedNonScored)

	if p.anomalies.clusterConcretenessCacheMisses > 0 {
		slog.Error("cascade concreteness cache divergence",
			"word", p.word,
			"miss_count", p.anomalies.clusterConcretenessCacheMisses,
			"candidate_count", len(p.candidates))
	}

	stopSort := observe.Start("cascade_sort")
	sortByFinalScore(p.matches)
	stopSort("word", p.word, "matches", len(p.matches))

	slog.Debug("cascade response ready",
		"word", p.word, "candidates", len(p.candidates), "scored", len(p.matches),
		"dropped_non_scored", droppedNonScored)
	return "", http.StatusOK, nil
}

// respondEmpty writes the 200-OK empty-Suggestions response for the
// "candidates assembled but len==0" branch. Closes the request through
// emit() so the outcome log fires exactly once.
func (p *cascadePipeline) respondEmpty(w http.ResponseWriter) {
	resp := SuggestResponse{Source: p.word, Suggestions: []forge.Match{}}
	w.Header().Set("Content-Type", "application/json")
	stopEncode := observe.Start("cascade_response_encode")
	encodeErr := json.NewEncoder(w).Encode(resp)
	stopEncode("word", p.word, "suggestion_count", 0)
	outcome := "empty_no_gate_pass"
	if encodeErr != nil {
		slog.Error("failed to encode empty cascade suggest response",
			"word", p.word, "err", encodeErr)
		outcome = "empty_encode_error"
	}
	p.emit(outcome, "candidates", 0)
}

// respondScored writes the 200-OK scored response with p.matches.
// Closes the request through emit() so the outcome log fires exactly
// once and carries the full per-source breakdown.
func (p *cascadePipeline) respondScored(w http.ResponseWriter) {
	resp := SuggestResponse{Source: p.word, Suggestions: p.matches}
	w.Header().Set("Content-Type", "application/json")
	stopEncode := observe.Start("cascade_response_encode")
	encodeErr := json.NewEncoder(w).Encode(resp)
	stopEncode("word", p.word, "suggestion_count", len(p.matches))
	outcome := "scored"
	if encodeErr != nil {
		slog.Error("failed to encode cascade suggest response",
			"word", p.word, "err", encodeErr)
		outcome = "scored_encode_error"
	}
	p.emit(outcome,
		"candidates", len(p.candidates),
		"scored_count", len(p.matches),
		"cluster_only", p.clusterOnly,
		"embedding_only", p.embeddingOnly,
		"both_paths", p.bothPaths,
	)
}

// emitError writes an HTTP error response and closes the request
// through emit(). The error has already been logged at Error level by
// the phase method that produced it; emit() carries the outcome enum
// onto the cascade_request_total + "cascade request complete" records.
func (p *cascadePipeline) emitError(w http.ResponseWriter, outcome string, status int, _ error) {
	switch status {
	case http.StatusNotFound:
		http.Error(w, `{"error": "word not found or has no curated properties"}`, status)
	default:
		http.Error(w, `{"error": "internal server error"}`, status)
	}
	p.emit(outcome)
}

// emit is the single emission site for cascade request outcomes. It
// closes stopTotal AND emits the "cascade request complete" slog.Info
// record with anomaly attrs + the call-site extras. DRY-ing this is
// the heart of the D24 refactor — pre-refactor there were 6 paired
// stopTotal + slog.Info sites with drifting attribute lists.
func (p *cascadePipeline) emit(outcome string, extra ...any) {
	if p.closed {
		// Defensive: never emit twice for one request.
		return
	}
	p.closed = true
	attrs := make([]any, 0, 4+len(extra)+len(p.anomalies.Attrs()))
	attrs = append(attrs, "word", p.word, "outcome", outcome)
	attrs = append(attrs, extra...)
	attrs = append(attrs, p.anomalies.Attrs()...)
	p.stopTotal(attrs...)
	slog.Info("cascade request complete", attrs...)
}
