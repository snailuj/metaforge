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
	// statusClientClosed is nginx's 499: the client hung up before we answered.
	statusClientClosed = 499

	defaultForestHops = 3
	minForestHops     = 1
	maxForestHops     = 5
)

// ForestGenerator is the slice of forest.Service the handler needs.
type ForestGenerator interface {
	Generate(ctx context.Context, word string, maxHops int) (forest.Forest, error)
}

// ForestCache is a best-effort store of finished forests (forestcache.Store).
type ForestCache interface {
	Random(ctx context.Context, word string, maxHops int) (forest.Forest, bool, error)
	Add(ctx context.Context, word string, maxHops int, f forest.Forest) error
}

// forestCacheWriteTimeout bounds storing a forest after the client may have
// gone: the forest is paid for, so it is kept even if nobody is waiting.
const forestCacheWriteTimeout = 5 * time.Second

// ForestHandler serves GET /forge/forest. It needs no lexicon database.
type ForestHandler struct {
	gen     ForestGenerator // nil when no API key is configured
	limiter *forest.Limiter
	Timeout time.Duration
	Cache   ForestCache // nil disables caching
}

// NewForestHandler takes a nil gen when the server has no API key; the
// route then answers 503.
func NewForestHandler(gen ForestGenerator, limiter *forest.Limiter) *ForestHandler {
	return &ForestHandler{gen: gen, limiter: limiter, Timeout: ForestRequestTimeout}
}

// HandleForest handles GET /forge/forest?word=<word>&max_hops=<1..5>&fresh=1
//
// With a cache, a request without fresh=1 (the panel's Forge) is served a
// random forest from the word's pool and spends nothing; fresh=1 (New
// forest), or an empty pool, generates and adds the forest to the pool.
// X-Forest-Cache reports hit, miss or fresh.
func (h *ForestHandler) HandleForest(w http.ResponseWriter, r *http.Request) {
	if h.gen == nil && h.Cache == nil {
		writeForestUnconfigured(w)
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

	fresh := r.URL.Query().Get("fresh") == "1"
	cacheState := "fresh"
	if h.Cache != nil && !fresh {
		cacheState = "miss"
		cached, hit, err := h.Cache.Random(r.Context(), word, maxHops)
		switch {
		case err != nil:
			slog.Warn("forest: cache read failed, generating instead", "word", word, "max_hops", maxHops, "err", err)
		case hit:
			slog.Info("forest: cache hit", "word", word, "max_hops", maxHops, "endpoints", len(cached.Endpoints))
			w.Header().Set("X-Forest-Cache", "hit")
			writeForest(w, word, cached)
			return
		}
	}
	if h.gen == nil {
		writeForestUnconfigured(w)
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
		if errors.Is(err, context.Canceled) {
			slog.Info("forest: client disconnected", "word", word)
			w.WriteHeader(statusClientClosed)
			return
		}
		timedOut := errors.Is(err, context.DeadlineExceeded)
		slog.Warn("forest: request failed", "word", word, "timed_out", timedOut)
		if timedOut {
			writeForestError(w, http.StatusGatewayTimeout, "metaphor forest request timed out")
			return
		}
		writeForestError(w, http.StatusBadGateway, "metaphor forest generation failed")
		return
	}

	if h.Cache != nil {
		w.Header().Set("X-Forest-Cache", cacheState)
		h.store(r.Context(), word, maxHops, result)
	}
	writeForest(w, word, result)
}

// store adds a forest worth serving again. Failures are logged, never
// returned: the caller already has its forest.
func (h *ForestHandler) store(ctx context.Context, word string, maxHops int, f forest.Forest) {
	if len(f.Endpoints) == 0 {
		slog.Info("forest: empty forest not cached", "word", word, "max_hops", maxHops)
		return
	}
	ctx, cancel := context.WithTimeout(context.WithoutCancel(ctx), forestCacheWriteTimeout)
	defer cancel()
	if err := h.Cache.Add(ctx, word, maxHops, f); err != nil {
		slog.Error("forest: cache write failed", "word", word, "max_hops", maxHops, "err", err)
		return
	}
	slog.Info("forest: cached", "word", word, "max_hops", maxHops, "endpoints", len(f.Endpoints))
}

func writeForest(w http.ResponseWriter, word string, f forest.Forest) {
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(f); err != nil {
		slog.Error("failed to encode forest response", "word", word, "err", err)
	}
}

func writeForestUnconfigured(w http.ResponseWriter) {
	writeForestError(w, http.StatusServiceUnavailable, "metaphor forest is not configured on this server")
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
