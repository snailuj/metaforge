package handler

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"math"
	"net/http"
	"strconv"
	"time"

	"github.com/snailuj/metaforge/internal/forest"
)

// ForestRequestTimeout bounds one forest request: two sequential LLM calls
// must finish inside the server's 90 s write timeout.
const ForestRequestTimeout = 75 * time.Second

const (
	defaultForestHops = 3
	minForestHops     = 1
	maxForestHops     = 5
)

// ForestGenerator is the slice of forest.Service the handler needs.
type ForestGenerator interface {
	Generate(ctx context.Context, word string, maxHops int) (forest.Forest, error)
}

// ForestHandler serves GET /forge/forest. It holds no database, so the
// route works without one.
type ForestHandler struct {
	gen     ForestGenerator // nil when no API key is configured
	limiter *forest.Limiter
	Timeout time.Duration
}

// NewForestHandler takes a nil gen when the server has no API key; the
// route then answers 503.
func NewForestHandler(gen ForestGenerator, limiter *forest.Limiter) *ForestHandler {
	return &ForestHandler{gen: gen, limiter: limiter, Timeout: ForestRequestTimeout}
}

// HandleForest handles GET /forge/forest?word=<word>&max_hops=<1..5>
func (h *ForestHandler) HandleForest(w http.ResponseWriter, r *http.Request) {
	if h.gen == nil {
		writeForestError(w, http.StatusServiceUnavailable, "metaphor forest is not configured on this server")
		return
	}

	word, err := forest.ParseSourceWord(r.URL.Query().Get("word"))
	if err != nil {
		slog.Warn("forest: invalid word", "err", err)
		writeForestError(w, http.StatusBadRequest, "invalid 'word' parameter: 1-40 letters, spaces, hyphens or apostrophes")
		return
	}
	maxHops, err := parseForestHops(r)
	if err != nil {
		slog.Warn("forest: invalid max_hops", "word", word, "err", err)
		writeForestError(w, http.StatusBadRequest, "invalid 'max_hops' parameter: must be an integer from 1 to 5")
		return
	}

	release, retryAfter, ok := h.limiter.Acquire()
	if !ok {
		secs := max(1, int(math.Ceil(retryAfter.Seconds())))
		slog.Warn("forest: rate limited", "word", word, "retry_after_s", secs)
		w.Header().Set("Retry-After", strconv.Itoa(secs))
		writeForestError(w, http.StatusTooManyRequests, "too many metaphor forest requests, try again shortly")
		return
	}
	defer release()

	ctx, cancel := context.WithTimeout(r.Context(), h.Timeout)
	defer cancel()

	result, err := h.gen.Generate(ctx, word, maxHops)
	if err != nil {
		// forest.Service has already logged the cause with its request context.
		timedOut := errors.Is(err, context.DeadlineExceeded)
		slog.Warn("forest: request failed", "word", word, "timed_out", timedOut)
		if timedOut {
			writeForestError(w, http.StatusGatewayTimeout, "metaphor forest request timed out")
			return
		}
		writeForestError(w, http.StatusBadGateway, "metaphor forest generation failed")
		return
	}

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(result); err != nil {
		slog.Error("failed to encode forest response", "word", word, "err", err)
	}
}

func parseForestHops(r *http.Request) (int, error) {
	q := r.URL.Query()
	if !q.Has("max_hops") {
		return defaultForestHops, nil
	}
	n, err := strconv.Atoi(q.Get("max_hops"))
	if err != nil {
		return 0, err
	}
	if n < minForestHops || n > maxForestHops {
		return 0, errors.New("max_hops outside 1-5")
	}
	return n, nil
}

func writeForestError(w http.ResponseWriter, status int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(map[string]string{"error": msg}); err != nil {
		slog.Error("failed to encode forest error response", "status", status, "err", err)
	}
}
