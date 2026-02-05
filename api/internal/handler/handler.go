// Package handler provides HTTP handlers for the Metaforge API.
package handler

import (
	"database/sql"
	"encoding/json"
	"net/http"
	"strconv"

	"github.com/snailuj/metaforge/internal/db"
	"github.com/snailuj/metaforge/internal/embeddings"
	"github.com/snailuj/metaforge/internal/forge"
)

// Default values for query parameters
const (
	DefaultThreshold = 0.7
	DefaultLimit     = 50
)

// ForgeHandler handles /forge/* endpoints.
type ForgeHandler struct {
	database *sql.DB
}

// NewForgeHandler creates a handler with database connection.
func NewForgeHandler(dbPath string) (*ForgeHandler, error) {
	database, err := db.Open(dbPath)
	if err != nil {
		return nil, err
	}
	return &ForgeHandler{database: database}, nil
}

// Close releases database resources.
func (h *ForgeHandler) Close() error {
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
func (h *ForgeHandler) HandleSuggest(w http.ResponseWriter, r *http.Request) {
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

	// Find synsets with similar properties (using similarity-based matching)
	candidates, err := db.GetSynsetsWithSharedProperties(h.database, synsetID, threshold, limit)
	if err != nil {
		http.Error(w, `{"error": "matching failed"}`, http.StatusInternalServerError)
		return
	}

	// Build matches with tier classification
	var matches []forge.Match
	for _, c := range candidates {
		// Get target synset details
		target, err := db.GetSynset(h.database, c.SynsetID)
		if err != nil {
			continue
		}

		// Get word for target synset
		targetWord, err := db.GetLemmaForSynset(h.database, c.SynsetID)
		if err != nil {
			targetWord = c.SynsetID // Fallback to ID
		}

		// Compute semantic distance via embeddings (for tier classification)
		dist, err := embeddings.ComputeSynsetDistance(h.database, synsetID, c.SynsetID)
		if err != nil {
			dist = 0.5 // Default for errors
		}

		tier := forge.ClassifyTier(dist, c.OverlapCount)

		matches = append(matches, forge.Match{
			SynsetID:         c.SynsetID,
			Word:             targetWord,
			Definition:       target.Definition,
			SharedProperties: c.SharedProperties,
			OverlapCount:     c.OverlapCount,
			Distance:         dist,
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
