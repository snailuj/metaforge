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

// Default values for query parameters
const (
	DefaultThreshold = 0.7
	DefaultLimit     = 50
)

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
	requiredTables := []string{"synsets", "lemmas", "synset_properties", "property_vocabulary", "synset_centroids"}
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
type SuggestResponse struct {
	Source      string        `json:"source"`
	SynsetID    string        `json:"synset_id"`
	Definition  string        `json:"definition"`
	Properties  []string      `json:"properties"`
	Threshold   float64       `json:"threshold"`
	Suggestions []forge.Match `json:"suggestions"`
}

// HandleSuggest handles GET /forge/suggest?word=<word>&threshold=<0.0-1.0>&limit=<n>
func (h *Handler) HandleSuggest(w http.ResponseWriter, r *http.Request) {
	word := r.URL.Query().Get("word")
	if word == "" {
		http.Error(w, `{"error": "missing 'word' parameter"}`, http.StatusBadRequest)
		return
	}

	// Parse threshold (default 0.7)
	threshold := DefaultThreshold
	if t := r.URL.Query().Get("threshold"); t != "" {
		if parsed, err := strconv.ParseFloat(t, 64); err == nil {
			if parsed >= 0 && parsed <= 1 {
				threshold = parsed
			}
		}
	}

	// Parse limit (default 50)
	limit := DefaultLimit
	if l := r.URL.Query().Get("limit"); l != "" {
		if parsed, err := strconv.Atoi(l); err == nil {
			if parsed > 0 && parsed <= 200 {
				limit = parsed
			}
		}
	}

	// Look up synset for word
	synsetID, err := db.GetSynsetIDForLemma(h.database, word)
	if err != nil {
		http.Error(w, `{"error": "word not found"}`, http.StatusNotFound)
		return
	}

	// Get source synset with properties
	source, err := db.GetSynset(h.database, synsetID)
	if err != nil {
		http.Error(w, `{"error": "synset lookup failed"}`, http.StatusInternalServerError)
		return
	}

	if len(source.Properties) == 0 {
		http.Error(w, `{"error": "word has no enriched properties"}`, http.StatusNotFound)
		return
	}

	// Single mega-query: candidates + details + exact overlap + centroids
	candidates, err := db.GetForgeMatches(h.database, synsetID, threshold, limit)
	if err != nil {
		http.Error(w, `{"error": "matching failed"}`, http.StatusInternalServerError)
		return
	}

	// Compute raw distances from pre-computed centroids
	rawDistances := make([]float64, len(candidates))
	for i, c := range candidates {
		rawDistances[i] = embeddings.CosineDistance(c.SourceCentroid, c.TargetCentroid)
	}

	// Normalise distances to [0, 1] within this result set.
	// Shared-property discovery biases candidates toward similar centroids,
	// so absolute distances cluster narrowly. Normalising ensures tier
	// classification reflects relative distance within the candidate pool.
	normDistances := forge.NormaliseDistances(rawDistances)

	// Classify tiers using normalised distances
	var matches []forge.Match
	for i, c := range candidates {
		tier := forge.ClassifyTier(normDistances[i], c.ExactOverlap)

		matches = append(matches, forge.Match{
			SynsetID:         c.SynsetID,
			Word:             c.Word,
			Definition:       c.Definition,
			SharedProperties: c.SharedProperties,
			OverlapCount:     c.ExactOverlap,
			Distance:         rawDistances[i],
			Tier:             tier,
			TierName:         tier.String(),
		})
	}

	// Sort by tier (best first)
	sorted := forge.SortByTier(matches)

	resp := SuggestResponse{
		Source:      word,
		SynsetID:    synsetID,
		Definition:  source.Definition,
		Properties:  source.Properties,
		Threshold:   threshold,
		Suggestions: sorted,
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
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
	json.NewEncoder(w).Encode(result)
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
