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
	"strconv"
	"strings"

	"github.com/snailuj/metaforge/internal/db"
	"github.com/snailuj/metaforge/internal/embeddings"
	"github.com/snailuj/metaforge/internal/forge"
	"github.com/snailuj/metaforge/internal/thesaurus"
)

// DefaultLimit is the default number of forge suggestions to return.
const DefaultLimit = 50

// Handler holds a shared database connection for all API endpoints.
type Handler struct {
	database   *sql.DB
	stringsDir string
}

// NewHandler creates a handler with database connection.
func NewHandler(dbPath string) (*Handler, error) {
	database, err := db.Open(dbPath)
	if err != nil {
		return nil, err
	}

	// Validate required tables exist
	requiredTables := []string{"synsets", "lemmas", "synset_properties_curated", "property_vocab_curated", "frequencies", "cluster_antonyms", "vocab_clusters", "lemma_embeddings"}
	for _, table := range requiredTables {
		var count int
		err := database.QueryRow("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", table).Scan(&count)
		if err != nil || count == 0 {
			database.Close()
			return nil, fmt.Errorf("required table %q not found in database", table)
		}
	}

	database.SetMaxOpenConns(4)

	return &Handler{database: database}, nil
}

// SetStringsDir sets the base directory for Fluent string files.
func (h *Handler) SetStringsDir(dir string) {
	h.stringsDir = dir
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

	// Fetch source lemma embedding for cross-domain distance
	sourceEmb, err := db.GetLemmaEmbedding(h.database, word)
	if err != nil {
		slog.Warn("source embedding lookup failed", "word", word, "err", err)
	}

	// Batch-fetch candidate embeddings
	candidateWords := make([]string, len(candidates))
	for i, c := range candidates {
		candidateWords[i] = c.Word
	}
	candidateEmbs, err := db.GetLemmaEmbeddingsBatch(h.database, candidateWords)
	if err != nil {
		slog.Warn("candidate embeddings batch lookup failed", "word", word, "err", err)
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
