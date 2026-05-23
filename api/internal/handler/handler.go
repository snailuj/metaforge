// Package handler provides HTTP handlers for the Metaforge API.
package handler

import (
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	"github.com/snailuj/metaforge/internal/db"
	"github.com/snailuj/metaforge/internal/embeddings"
	"github.com/snailuj/metaforge/internal/forge"
	"github.com/snailuj/metaforge/internal/observe"
	"github.com/snailuj/metaforge/internal/thesaurus"
)

// DefaultLimit is the default number of forge suggestions to return.
const DefaultLimit = 50

// Handler holds a shared database connection for all API endpoints.
type Handler struct {
	database    *sql.DB
	stringsDir  string
	useCascade  bool
	cascadeConf forge.CascadeConfig
	cache       *db.CascadeCache // nil when cascade disabled
}

// NewHandler creates a legacy-mode handler (CompositeScore path).
func NewHandler(dbPath string) (*Handler, error) {
	return NewHandlerWithCascade(dbPath, false)
}

// NewHandlerWithCascade opts into the M03 cascade path on /forge/suggest.
// Cascade mode requires synset_concreteness and synset_centroids and
// eagerly loads them into memory (~50 MB) — startup cost trades for
// per-request latency.
func NewHandlerWithCascade(dbPath string, useCascade bool) (*Handler, error) {
	database, err := db.Open(dbPath)
	if err != nil {
		return nil, err
	}

	required := []string{
		"synsets", "lemmas", "synset_properties_curated", "property_vocab_curated",
		"frequencies", "cluster_antonyms", "vocab_clusters", "lemma_embeddings",
	}
	if useCascade {
		required = append(required, "synset_concreteness", "synset_centroids")
	}
	for _, table := range required {
		var count int
		err := database.QueryRow(
			"SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
			table,
		).Scan(&count)
		if err != nil || count == 0 {
			database.Close()
			return nil, fmt.Errorf("required table %q not found in database", table)
		}
	}

	if useCascade {
		// Existence-only check above leaves a silent-failure mode: a fresh
		// deploy with empty cascade tables passes the loop, loads empty
		// caches, and every request returns empty 200. Assert non-zero
		// rows so we fail loud at startup instead. SQL injection-safe:
		// table names are hard-coded, not user input.
		for _, table := range []string{"synset_concreteness", "synset_centroids"} {
			var rowCount int
			err := database.QueryRow(fmt.Sprintf("SELECT COUNT(*) FROM %s", table)).Scan(&rowCount)
			if err != nil {
				database.Close()
				return nil, fmt.Errorf("counting rows in %q: %w", table, err)
			}
			if rowCount == 0 {
				database.Close()
				return nil, fmt.Errorf("cascade table %q is empty — cannot serve cascade traffic against an empty table", table)
			}
		}
	}

	database.SetMaxOpenConns(4)

	h := &Handler{
		database:    database,
		useCascade:  useCascade,
		cascadeConf: forge.DefaultCascadeConfig(),
	}

	if useCascade {
		cache, err := db.LoadCascadeCache(database)
		if err != nil {
			database.Close()
			return nil, fmt.Errorf("load cascade cache: %w", err)
		}
		h.cache = cache
	}

	return h, nil
}

// SetStringsDir sets the base directory for Fluent string files.
func (h *Handler) SetStringsDir(dir string) {
	h.stringsDir = dir
}

// WithCascadeConfig overrides the default cascade config. Must be
// called immediately after NewHandlerWithCascade and before serving
// traffic. Errors if cfg.Validate() rejects the config.
func (h *Handler) WithCascadeConfig(cfg forge.CascadeConfig) error {
	if err := cfg.Validate(); err != nil {
		return fmt.Errorf("invalid cascade config: %w", err)
	}
	h.cascadeConf = cfg
	return nil
}

// Close releases database resources.
func (h *Handler) Close() error {
	return h.database.Close()
}

// SuggestResponse is the JSON response for /forge/suggest.
// Each suggestion carries its own source context (synset, definition, POS)
// since polysemous words may align different targets to different senses.
type SuggestResponse struct {
	Source      string        `json:"source"`
	Suggestions []forge.Match `json:"suggestions"`
}

// HandleSuggest handles GET /forge/suggest?word=<word>&limit=<n>
func (h *Handler) HandleSuggest(w http.ResponseWriter, r *http.Request) {
	word := r.URL.Query().Get("word")
	if word == "" {
		http.Error(w, `{"error": "missing 'word' parameter"}`, http.StatusBadRequest)
		return
	}

	limit := DefaultLimit
	if l := r.URL.Query().Get("limit"); l != "" {
		if parsed, err := strconv.Atoi(l); err == nil {
			if parsed > 0 && parsed <= 200 {
				limit = parsed
			}
		}
	}

	if h.useCascade {
		h.handleSuggestCascade(w, word, limit)
		return
	}
	h.handleSuggestLegacy(w, word, limit)
}

// handleSuggestLegacy is the pre-M03 CompositeScore path. Body relocated
// verbatim from the original HandleSuggest.
func (h *Handler) handleSuggestLegacy(w http.ResponseWriter, word string, limit int) {
	candidates, err := db.GetForgeMatchesCuratedByLemma(h.database, word, limit)
	if errors.Is(err, db.ErrLemmaNotFound) {
		http.Error(w, `{"error": "word not found or has no curated properties"}`, http.StatusNotFound)
		return
	}
	if err != nil {
		slog.Error("matching failed", "word", word, "err", err)
		http.Error(w, `{"error": "internal server error"}`, http.StatusInternalServerError)
		return
	}

	// D8: lemma-embedding lookups return (nil, nil) for benign cases
	// ("no embedding row", "table missing") and (nil, err) only for real
	// DB faults (schema corruption, I/O failures, etc). A real error here
	// produces silently-degraded composite scores (domainDist = 0 for
	// every candidate) without any signal to the caller, so escalate to
	// 500 to match the cascade-path discipline.
	sourceEmb, err := db.GetLemmaEmbedding(h.database, word)
	if err != nil {
		slog.Error("source embedding lookup failed", "word", word, "err", err)
		http.Error(w, `{"error": "internal server error"}`, http.StatusInternalServerError)
		return
	}

	// Batch-fetch candidate embeddings
	candidateWords := make([]string, len(candidates))
	for i, c := range candidates {
		candidateWords[i] = c.Word
	}
	candidateEmbs, err := db.GetLemmaEmbeddingsBatch(h.database, candidateWords)
	if err != nil {
		slog.Error("candidate embeddings batch lookup failed", "word", word, "err", err)
		http.Error(w, `{"error": "internal server error"}`, http.StatusInternalServerError)
		return
	}

	var matches []forge.Match
	for _, c := range candidates {
		// Compute domain distance if both embeddings available
		var domainDist float64
		if sourceEmb != nil && candidateEmbs != nil {
			if candEmb, ok := candidateEmbs[c.Word]; ok {
				domainDist = embeddings.CosineDistance(sourceEmb, candEmb)
			}
		}

		compositeScore := forge.CompositeScore(c.SalienceSum, domainDist)
		tier := forge.ClassifyTierCurated(c.SalienceSum, c.ContrastCount)

		matches = append(matches, forge.Match{
			SynsetID:         c.SynsetID,
			Word:             c.Word,
			Definition:       c.Definition,
			SharedProperties: c.SharedProps,
			OverlapCount:     int(c.SalienceSum), // backward compat
			SalienceSum:      c.SalienceSum,
			Tier:             tier,
			TierName:         tier.String(),
			SourceSynsetID:   c.SourceSynsetID,
			SourceDefinition: c.SourceDefinition,
			SourcePOS:        c.SourcePOS,
			DomainDistance:    domainDist,
			CompositeScore:   compositeScore,
		})
	}

	sorted := forge.SortByTier(matches)

	resp := SuggestResponse{
		Source:      word,
		Suggestions: sorted,
	}

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		slog.Error("failed to encode suggest response", "word", word, "err", err)
	}
}

// handleSuggestCascade scores candidates through the M03 cascade.
//
// Hot path: 1 gated CTE candidate query + 1 batch properties query + N
// in-memory map lookups + per-pair pure-function scoring. Source-side
// data is memoised implicitly via the batch properties map.
func (h *Handler) handleSuggestCascade(w http.ResponseWriter, word string, limit int) {
	stopTotal := observe.Start("cascade_request_total")
	slog.Debug("cascade request begin", "word", word, "limit", limit)

	anomalies := struct {
		concretenessCacheMisses int
		emptyPropsBatchFlag     bool
	}{}

	var (
		cluster []db.CascadeCandidate
		err     error
	)
	if h.cascadeConf.CandidateSources != forge.SourcesEmbedding {
		// Symmetric with the embedding-path stage timer below: only emit
		// cascade_candidates_query when the cluster path actually runs.
		// In embedding_only mode the cluster fetch is fully skipped — no
		// stage timer, no zero-count log noise.
		stopCand := observe.Start("cascade_candidates_query")
		cluster, err = db.GetForgeCascadeCandidatesByLemma(
			h.database, word, h.cascadeConf.ConcretenessThreshold, limit,
		)
		stopCand("word", word, "count", len(cluster))
	}
	// Cluster-path ErrLemmaNotFound is a 404 ONLY when no embedding path
	// will follow; under union mode an un-enriched lemma will also fail
	// the embedding primary-synset resolver, so we let that branch return
	// the 404 below for uniformity.
	if errors.Is(err, db.ErrLemmaNotFound) && h.cascadeConf.CandidateSources == forge.SourcesCluster {
		stopTotal("word", word, "outcome", "lemma_not_found")
		http.Error(w, `{"error": "word not found or has no curated properties"}`, http.StatusNotFound)
		return
	}
	if err != nil && !errors.Is(err, db.ErrLemmaNotFound) {
		stopTotal("word", word, "outcome", "candidates_error")
		slog.Error("cascade candidate fetch failed", "word", word, "err", err)
		http.Error(w, `{"error": "internal server error"}`, http.StatusInternalServerError)
		return
	}

	var embedding []db.CascadeCandidate
	if h.cascadeConf.CandidateSources != forge.SourcesCluster {
		stopEmb := observe.Start("cascade_embedding_query")
		embCfg := db.ForgeEmbeddingConfig{
			DMin: h.cascadeConf.EmbeddingDMin,
			DMax: h.cascadeConf.EmbeddingDMax,
			TopK: h.cascadeConf.EmbeddingTopK,
		}
		embedding, err = db.GetForgeCascadeCandidatesByEmbedding(h.database, h.cache, word, embCfg)
		stopEmb("word", word, "count", len(embedding))
		if errors.Is(err, db.ErrLemmaNotFound) {
			// Both paths agree: lemma not enriched.
			stopTotal("word", word, "outcome", "lemma_not_found")
			http.Error(w, `{"error": "word not found or has no curated properties"}`, http.StatusNotFound)
			return
		}
		if err != nil {
			stopTotal("word", word, "outcome", "embedding_error")
			slog.Error("cascade embedding fetch failed", "word", word, "err", err)
			http.Error(w, `{"error": "internal server error"}`, http.StatusInternalServerError)
			return
		}
	}

	candidates := unionCandidates(cluster, embedding)
	slog.Debug("cascade candidates assembled",
		"word", word, "cluster", len(cluster), "embedding", len(embedding),
		"after_union", len(candidates))

	if len(candidates) == 0 {
		// Lemma is enriched but neither path produced a candidate.
		resp := SuggestResponse{Source: word, Suggestions: []forge.Match{}}
		w.Header().Set("Content-Type", "application/json")
		stopEncode := observe.Start("cascade_response_encode")
		encodeErr := json.NewEncoder(w).Encode(resp)
		stopEncode("word", word, "suggestion_count", 0)
		outcome := "empty_no_gate_pass"
		if encodeErr != nil {
			slog.Error("failed to encode empty cascade suggest response", "word", word, "err", encodeErr)
			outcome = "empty_encode_error"
		}
		stopTotal("word", word, "outcome", outcome)
		return
	}

	// Collect distinct synset_ids for one batch properties query.
	idSet := make(map[string]struct{}, 2*len(candidates))
	for _, c := range candidates {
		idSet[c.SourceSynsetID] = struct{}{}
		idSet[c.SynsetID] = struct{}{}
	}
	ids := make([]string, 0, len(idSet))
	for id := range idSet {
		ids = append(ids, id)
	}
	stopProps := observe.Start("cascade_batch_props_query")
	propsByID, err := db.GetSynsetClusterPropertiesBatch(h.database, ids)
	stopProps("word", word, "synset_ids", len(ids), "rows", len(propsByID))
	if err != nil {
		stopTotal("word", word, "outcome", "batch_props_error")
		slog.Error("cascade batch properties fetch failed", "word", word, "err", err)
		http.Error(w, `{"error": "internal server error"}`, http.StatusInternalServerError)
		return
	}
	if len(propsByID) == 0 {
		// Anomaly: candidates were gate-passed (so the cascade tables are
		// populated for these synsets) but NONE of them have curated
		// properties. Most likely synset_properties_curated was truncated
		// post-startup or schema drifted. Surface as Error so operators
		// can spot the silent attrition; continue serving (response will
		// be empty due to the no_properties filter below).
		slog.Error("cascade batch properties returned empty for all candidates",
			"word", word, "candidate_count", len(candidates))
	}

	var clusterOnly, embeddingOnly, bothPaths int
	for _, c := range candidates {
		switch c.Source {
		case forge.SourceCluster:
			clusterOnly++
		case forge.SourceEmbedding:
			embeddingOnly++
		case forge.SourceBoth:
			bothPaths++
		}
	}

	stopScore := observe.Start("cascade_scoring_loop")
	var droppedNonScored int
	matches := make([]forge.Match, 0, len(candidates))
	for _, c := range candidates {
		// Concreteness from the in-memory cache — preserves the *float64
		// absence-signal contract EvaluateCascadePair expects (TD1).
		var tConc, vConc *float64
		if v, ok := h.cache.Concreteness[c.SourceSynsetID]; ok {
			tConc = &v
		}
		if v, ok := h.cache.Concreteness[c.SynsetID]; ok {
			vConc = &v
		}
		// Invariant tripwire: the gated CTE filters candidates via INNER JOIN
		// on synset_concreteness for both sides, so a missing cache entry
		// here means the cache and SQL view of the table diverged — most
		// likely cache load skipped a row (SF4 malformed-blob class) or the
		// DB was rewritten under us between cache load and the request.
		// Error level so operators see the signal.
		if tConc == nil || vConc == nil {
			anomalies.concretenessCacheMisses++
		}
		topicCent := h.cache.Centroids[c.SourceSynsetID] // nil-safe: zero value is nil
		vehCent := h.cache.Centroids[c.SynsetID]

		res := forge.EvaluateCascadePair(forge.CascadeInputs{
			TopicConcreteness:   tConc,
			VehicleConcreteness: vConc,
			TopicProperties:     propsByID[c.SourceSynsetID],
			VehicleProperties:   propsByID[c.SynsetID],
			TopicCentroid:       topicCent,
			VehicleCentroid:     vehCent,
		}, h.cascadeConf)

		// SQL CTE already filtered gate_dropped + missing_concreteness, so
		// the only attrition we can see here is no_properties (curated
		// props could have been pruned). Drop those from product output.
		if res.Status != forge.CascadeStatusScored {
			droppedNonScored++
			continue
		}

		tier := forge.ClassifyTierCurated(c.SalienceSum, c.ContrastCount)
		matches = append(matches, forge.Match{
			SynsetID:         c.SynsetID,
			Word:             c.Word,
			Definition:       c.Definition,
			SharedProperties: c.SharedProps,
			OverlapCount:     int(c.SalienceSum),
			SalienceSum:      c.SalienceSum,
			Tier:             tier,
			TierName:         tier.String(),
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

	stopScore("word", word, "scored", len(matches), "dropped_non_scored", droppedNonScored)

	if anomalies.concretenessCacheMisses > 0 {
		slog.Error("cascade concreteness cache divergence",
			"word", word,
			"miss_count", anomalies.concretenessCacheMisses,
			"candidate_count", len(candidates))
	}

	stopSort := observe.Start("cascade_sort")
	sortByFinalScore(matches)
	stopSort("word", word, "matches", len(matches))

	slog.Debug("cascade response ready",
		"word", word, "candidates", len(candidates), "scored", len(matches),
		"dropped_non_scored", droppedNonScored)

	resp := SuggestResponse{Source: word, Suggestions: matches}
	w.Header().Set("Content-Type", "application/json")
	stopEncode := observe.Start("cascade_response_encode")
	encodeErr := json.NewEncoder(w).Encode(resp)
	stopEncode("word", word, "suggestion_count", len(matches))
	outcome := "scored"
	if encodeErr != nil {
		slog.Error("failed to encode cascade suggest response", "word", word, "err", encodeErr)
		outcome = "scored_encode_error"
	}
	stopTotal("word", word,
		"outcome", outcome,
		"candidates", len(candidates),
		"scored_count", len(matches),
		"cluster_only", clusterOnly,
		"embedding_only", embeddingOnly,
		"both_paths", bothPaths,
		"concreteness_cache_misses", anomalies.concretenessCacheMisses,
		"empty_props_batch", anomalies.emptyPropsBatchFlag,
	)
}

func sortByFinalScore(matches []forge.Match) {
	// nil arms are defensive — the Scored-status filter in
	// handleSuggestCascade guarantees both sides non-nil. Kept so a future
	// caller that bypasses the filter doesn't crash.
	sort.Slice(matches, func(i, j int) bool {
		a, b := matches[i].FinalScore, matches[j].FinalScore
		if a == nil && b == nil {
			return false
		}
		if a == nil {
			return false
		}
		if b == nil {
			return true
		}
		return *a > *b
	})
}

// HandleLookup handles GET /thesaurus/lookup?word=<word>
func (h *Handler) HandleLookup(w http.ResponseWriter, r *http.Request) {
	word := r.URL.Query().Get("word")
	if word == "" {
		http.Error(w, `{"error": "missing 'word' parameter"}`, http.StatusBadRequest)
		return
	}

	result, err := thesaurus.GetLookup(h.database, word)
	if errors.Is(err, thesaurus.ErrWordNotFound) {
		http.Error(w, `{"error": "word not found"}`, http.StatusNotFound)
		return
	}
	if err != nil {
		slog.Error("lookup failed", "word", word, "err", err)
		http.Error(w, `{"error": "lookup failed"}`, http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(result); err != nil {
		slog.Error("failed to encode lookup response", "word", word, "err", err)
	}
}

// AutocompleteResponse is the JSON response for /thesaurus/autocomplete.
type AutocompleteResponse struct {
	Suggestions []thesaurus.AutocompleteSuggestion `json:"suggestions"`
}

// Autocomplete defaults
const (
	DefaultAutocompleteLimit = 10
	MaxAutocompleteLimit     = 50
	MinPrefixLength          = 2
)

// HandleAutocomplete handles GET /thesaurus/autocomplete?prefix=<prefix>&limit=<n>
func (h *Handler) HandleAutocomplete(w http.ResponseWriter, r *http.Request) {
	prefix := r.URL.Query().Get("prefix")
	if len(strings.TrimSpace(prefix)) < MinPrefixLength {
		http.Error(w, `{"error": "prefix must be at least 2 characters"}`, http.StatusBadRequest)
		return
	}

	limit := DefaultAutocompleteLimit
	if l := r.URL.Query().Get("limit"); l != "" {
		if parsed, err := strconv.Atoi(l); err == nil && parsed > 0 {
			limit = parsed
		}
	}
	if limit > MaxAutocompleteLimit {
		limit = MaxAutocompleteLimit
	}

	suggestions, err := thesaurus.AutocompletePrefix(h.database, prefix, limit)
	if err != nil {
		slog.Error("autocomplete failed", "prefix", prefix, "err", err)
		http.Error(w, `{"error": "autocomplete failed"}`, http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(AutocompleteResponse{Suggestions: suggestions}); err != nil {
		slog.Error("failed to encode autocomplete response", "prefix", prefix, "err", err)
	}
}

// HandleStrings serves Fluent .ftl string files.
// Route: GET /strings/v1/{filename}.ftl
func (h *Handler) HandleStrings(w http.ResponseWriter, r *http.Request) {
	// Extract filename from path: /strings/v1/ui.ftl → v1/ui.ftl
	path := strings.TrimPrefix(r.URL.Path, "/strings/")
	if path == "" || !strings.HasSuffix(path, ".ftl") {
		http.Error(w, `{"error": "invalid path"}`, http.StatusBadRequest)
		return
	}

	// Prevent directory traversal
	clean := filepath.Clean(path)
	if strings.Contains(clean, "..") {
		http.Error(w, `{"error": "invalid path"}`, http.StatusBadRequest)
		return
	}

	// Map to locale file: ui.ftl → ui.en-GB.ftl
	base := strings.TrimSuffix(filepath.Base(clean), ".ftl")
	dir := filepath.Dir(clean)
	localePath := filepath.Join(h.stringsDir, dir, base+".en-GB.ftl")

	data, err := os.ReadFile(localePath)
	if err != nil {
		http.Error(w, `{"error": "strings file not found"}`, http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.Header().Set("Cache-Control", "public, max-age=31536000, immutable")
	w.Write(data)
}

// CORSMiddleware adds CORS headers for development (Vite dev server).
func CORSMiddleware(allowedOrigin string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Access-Control-Allow-Origin", allowedOrigin)
			w.Header().Set("Access-Control-Allow-Methods", "GET, OPTIONS")
			w.Header().Set("Access-Control-Allow-Headers", "Content-Type")

			if r.Method == http.MethodOptions {
				w.WriteHeader(http.StatusNoContent)
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}
