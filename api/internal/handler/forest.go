package handler

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"math"
	"net"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/snailuj/metaforge/internal/forest"
	"github.com/snailuj/metaforge/internal/llmlog"
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

// ForestStreamer is the streaming slice of forest.Service. A generator that
// also implements it serves event-stream requests as a stream.
type ForestStreamer interface {
	GenerateStream(ctx context.Context, word string, maxHops int, emit func(forest.StreamEvent)) (forest.Forest, error)
}

// defaultForestKeepalive is how often an idle stream gets a comment line,
// well inside common proxy idle timeouts.
const defaultForestKeepalive = 10 * time.Second

// ForestCache is a best-effort store of finished forests (forestcache.Store).
type ForestCache interface {
	Random(ctx context.Context, word string, maxHops int) (forest.Forest, bool, error)
	Add(ctx context.Context, word string, maxHops int, f forest.Forest) error
	Full(ctx context.Context, word string, maxHops int) (bool, error)
	List(ctx context.Context, word string, maxHops int) ([]forest.Forest, error)
}

// ForestLedger keeps every forest request for good (llmlog.Store).
type ForestLedger interface {
	RecordRun(ctx context.Context, r llmlog.Run) error
	RunCost(ctx context.Context, runID string) (float64, error)
}

// ForestBudget reports the rolling-week model spend against its cap.
type ForestBudget interface {
	Status(ctx context.Context) (llmlog.BudgetStatus, error)
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
	// Keepalive is the comment interval on an idle event stream.
	Keepalive time.Duration
	Ledger    ForestLedger // nil: runs are not recorded
	Budget    ForestBudget // nil: no spending cap
	// Ceiling stops everyone generating, live users included, once the
	// week's recorded spend reaches it; nil: no ceiling.
	Ceiling ForestBudget
	// Visitors caps the forests one visitor may generate; nil: no cap.
	Visitors *forest.VisitorLimiter
	// Fingerprint is the pipeline version recorded with each run.
	Fingerprint string
}

// NewForestHandler takes a nil gen when the server has no API key; the
// route then answers 503.
func NewForestHandler(gen ForestGenerator, limiter *forest.Limiter) *ForestHandler {
	return &ForestHandler{gen: gen, limiter: limiter, Timeout: ForestRequestTimeout, Keepalive: defaultForestKeepalive}
}

// HandleForest handles GET /forge/forest?word=<word>&max_hops=<1..5>&fresh=1
//
// With a cache, a request without fresh=1 (the panel's Forge) is served a
// random forest from the word's pool and spends nothing; fresh=1 (New
// forest), or an empty pool, generates and adds the forest to the pool.
// X-Forest-Cache reports hit, miss or fresh.
//
// With Accept: text/event-stream, and a generator that can stream, the
// answer is a server-sent event stream (see streamForest). Refusals before
// generation starts keep their status codes and JSON bodies either way.
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
			if wantsStream(r) {
				sse := startSSE(w)
				sse.event("done", cached)
				return
			}
			writeForest(w, word, cached)
			return
		}
	}
	if h.gen == nil {
		writeForestUnconfigured(w)
		return
	}
	if refuseOtherSite(w, r, word) {
		return
	}
	origin := parseOrigin(r)
	if origin == enrichmentOrigin && h.poolFull(r.Context(), word, maxHops) {
		// Another forest would only evict one; enrichment moves on.
		w.Header().Set("X-Forest-Pool", "full")
		if h.serveFromPool(w, r, word, maxHops) {
			return
		}
		w.Header().Del("X-Forest-Pool") // emptied since the count; generate after all
	}
	if origin == enrichmentOrigin && budgetSpent(r.Context(), h.Budget, "weekly cap", word) {
		w.Header().Set("X-Forest-Budget", "exhausted")
		if h.serveFromPool(w, r, word, maxHops) {
			return
		}
		writeForestError(w, http.StatusServiceUnavailable, "the weekly model budget is spent; new metaphor forests resume as it frees up")
		return
	}
	if budgetSpent(r.Context(), h.Ceiling, "ceiling", word) {
		w.Header().Set("X-Forest-Budget", "ceiling")
		if h.serveFromPool(w, r, word, maxHops) {
			return
		}
		w.Header().Set("Retry-After", strconv.Itoa(int(ceilingRetryAfter.Seconds())))
		writeForestError(w, http.StatusTooManyRequests, "new metaphor forests are paused for now; forests already made still load, try again later")
		return
	}

	refundVisit, ok := h.admitVisitor(w, r, word)
	if !ok {
		return
	}
	release, retryAfter, ok := h.limiter.Acquire()
	if !ok {
		refundVisit()
		secs := max(1, int(math.Ceil(retryAfter.Seconds())))
		slog.Warn("forest: rate limited", "word", word, "retry_after_s", secs)
		w.Header().Set("Retry-After", strconv.Itoa(secs))
		writeForestError(w, http.StatusTooManyRequests, "too many metaphor forest requests, try again shortly")
		return
	}
	defer release()

	ctx, cancel := context.WithTimeout(r.Context(), h.Timeout)
	defer cancel()
	run := llmlog.RunInfo{ID: newRunID(), Origin: origin, Word: word, MaxHops: maxHops}
	ctx = llmlog.WithRun(ctx, run)
	started := time.Now()

	if streamer, ok := h.gen.(ForestStreamer); ok && wantsStream(r) && canStream(h.gen) {
		if h.Cache != nil {
			w.Header().Set("X-Forest-Cache", cacheState)
		}
		h.streamForest(ctx, w, streamer, run, started)
		return
	}

	result, err := h.gen.Generate(ctx, word, maxHops)
	cost, costKnown := h.recordRun(ctx, run, started, result, err)
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
	if costKnown {
		w.Header().Set("X-Forest-Cost-USD", strconv.FormatFloat(cost, 'f', 6, 64))
	}
	writeForest(w, word, result)
}

// enrichmentOrigin marks the background enricher. Only it yields to the
// weekly cap: the owner chose (2026-11-04) never to block live users, whose
// spend still counts toward the cap and so slows enrichment. The header is
// self-declared, which is safe here because claiming another origin only
// exempts a caller from a stop that live users never get.
const enrichmentOrigin = "enrichment"

// ceilingRetryAfter is how long a client is told to wait past the ceiling.
// Spend ages out of the rolling week gradually, so this is a polling
// interval, not when generation resumes.
const ceilingRetryAfter = time.Hour

// budgetSpent reports whether b forbids generating; which names it in logs.
// A budget that cannot be read counts as spent.
func budgetSpent(ctx context.Context, b ForestBudget, which, word string) bool {
	if b == nil {
		return false
	}
	st, err := b.Status(ctx)
	if err != nil {
		slog.Error("forest: budget unreadable, refusing to generate", "budget", which, "word", word, "err", err)
		return true
	}
	if st.Exhausted {
		slog.Warn("forest: budget spent", "budget", which, "word", word, "spent_usd", st.SpentUSD, "cap_usd", st.CapUSD)
	}
	return st.Exhausted
}

// poolFull reports whether the word's pool needs no more forests. A pool
// that cannot be counted is treated as not full.
func (h *ForestHandler) poolFull(ctx context.Context, word string, maxHops int) bool {
	if h.Cache == nil {
		return false
	}
	full, err := h.Cache.Full(ctx, word, maxHops)
	if err != nil {
		slog.Warn("forest: pool size unreadable, generating", "word", word, "max_hops", maxHops, "err", err)
		return false
	}
	if full {
		slog.Info("forest: pool full, enrichment skips", "word", word, "max_hops", maxHops)
	}
	return full
}

// serveFromPool answers with a cached forest if the pool has one.
func (h *ForestHandler) serveFromPool(w http.ResponseWriter, r *http.Request, word string, maxHops int) bool {
	if h.Cache == nil {
		return false
	}
	cached, hit, err := h.Cache.Random(r.Context(), word, maxHops)
	if err != nil {
		slog.Warn("forest: cache read failed", "word", word, "max_hops", maxHops, "err", err)
		return false
	}
	if !hit {
		return false
	}
	w.Header().Set("X-Forest-Cache", "hit")
	if wantsStream(r) {
		startSSE(w).event("done", cached)
		return true
	}
	writeForest(w, word, cached)
	return true
}

// recordRun keeps the request in the ledger, whatever its outcome, and
// returns what its model calls cost, and false when that is unknown.
// Ledger failures are logged only.
func (h *ForestHandler) recordRun(ctx context.Context, run llmlog.RunInfo, started time.Time, f forest.Forest, genErr error) (float64, bool) {
	if h.Ledger == nil {
		return 0, false
	}
	ctx, cancel := context.WithTimeout(context.WithoutCancel(ctx), forestCacheWriteTimeout)
	defer cancel()
	rec := llmlog.Run{ID: run.ID, Started: started, Total: time.Since(started), Word: run.Word, MaxHops: run.MaxHops,
		Origin: run.Origin, Fingerprint: h.Fingerprint, Outcome: "ok"}
	switch {
	case errors.Is(genErr, context.Canceled):
		rec.Outcome, rec.Error = "canceled", genErr.Error()
	case errors.Is(genErr, context.DeadlineExceeded):
		rec.Outcome, rec.Error = "timeout", genErr.Error()
	case genErr != nil:
		rec.Outcome, rec.Error = "error", genErr.Error()
	default:
		body, err := json.Marshal(f)
		if err != nil {
			slog.Error("forest: could not encode forest for the ledger", "run_id", run.ID, "err", err)
		}
		rec.Forest = body
	}
	cost, err := h.Ledger.RunCost(ctx, run.ID)
	costKnown := err == nil
	if !costKnown {
		slog.Error("forest: run cost unreadable", "run_id", run.ID, "err", err)
	}
	rec.CostUSD = cost
	if err := h.Ledger.RecordRun(ctx, rec); err != nil {
		slog.Error("forest: run not recorded", "run_id", run.ID, "word", run.Word, "err", err)
	}
	slog.Info("forest: run recorded", "run_id", run.ID, "word", run.Word, "origin", run.Origin,
		"outcome", rec.Outcome, "cost_usd", cost, "cost_known", costKnown)
	return cost, costKnown
}

// streamForest answers with a server-sent event stream: each service event
// as it happens, then one done with the final forest, or one error event
// with kind "timeout" or "failed". A comment line goes out every Keepalive
// while the stream is idle.
func (h *ForestHandler) streamForest(ctx context.Context, w http.ResponseWriter, gen ForestStreamer, run llmlog.RunInfo, started time.Time) {
	word, maxHops := run.Word, run.MaxHops
	sse := startSSE(w)
	if h.Keepalive > 0 {
		// Nothing may write to w after the handler returns, so wait for it.
		stop, done := make(chan struct{}), make(chan struct{})
		go func() { defer close(done); sse.keepalive(h.Keepalive, stop) }()
		defer func() { close(stop); <-done }()
	}

	result, err := gen.GenerateStream(ctx, word, maxHops, func(ev forest.StreamEvent) { sse.event(ev.Name, ev.Data) })
	h.recordRun(ctx, run, started, result, err)
	switch {
	case errors.Is(err, context.Canceled):
		slog.Info("forest: client disconnected mid-stream", "word", word)
	case err != nil:
		kind := "failed"
		if errors.Is(err, context.DeadlineExceeded) {
			kind = "timeout"
		}
		slog.Warn("forest: stream failed", "word", word, "kind", kind)
		sse.event("error", map[string]string{"error": "metaphor forest generation failed", "kind": kind})
	default:
		if h.Cache != nil {
			h.store(ctx, word, maxHops, result)
		}
		sse.event("done", result)
	}
}

// canStream lets a generator whose model client cannot stream decline;
// the request is then answered as JSON.
func canStream(gen ForestGenerator) bool {
	c, ok := gen.(interface{ CanStream() bool })
	return !ok || c.CanStream()
}

func wantsStream(r *http.Request) bool {
	return strings.Contains(r.Header.Get("Accept"), "text/event-stream")
}

// sseWriter serialises writes from the service's events and the keepalive.
type sseWriter struct {
	mu sync.Mutex
	w  http.ResponseWriter
}

func startSSE(w http.ResponseWriter) *sseWriter {
	h := w.Header()
	h.Set("Content-Type", "text/event-stream")
	h.Set("Cache-Control", "no-cache")
	h.Set("X-Accel-Buffering", "no")
	w.WriteHeader(http.StatusOK)
	s := &sseWriter{w: w}
	s.flush()
	return s
}

func (s *sseWriter) event(name string, data any) {
	b, err := json.Marshal(data)
	if err != nil {
		slog.Error("forest: failed to encode stream event", "event", name, "err", err)
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, err := fmt.Fprintf(s.w, "event: %s\ndata: %s\n\n", name, b); err != nil {
		slog.Debug("forest: stream write failed", "event", name, "err", err)
		return
	}
	s.flush()
}

func (s *sseWriter) keepalive(every time.Duration, stop <-chan struct{}) {
	t := time.NewTicker(every)
	defer t.Stop()
	for {
		select {
		case <-stop:
			return
		case <-t.C:
			s.mu.Lock()
			_, _ = io.WriteString(s.w, ": keepalive\n\n")
			s.flush()
			s.mu.Unlock()
		}
	}
}

func (s *sseWriter) flush() {
	if f, ok := s.w.(http.Flusher); ok {
		f.Flush()
	}
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

// HandleSaved handles GET /forge/forest/saved?word=<word>&max_hops=<1..5>:
// the word's pool of saved forests, newest first, as {"forests": [...]}.
// It only reads the cache, so it needs no API key, limiter slot or budget.
// No cache answers an empty list: there is nothing to browse.
func (h *ForestHandler) HandleSaved(w http.ResponseWriter, r *http.Request) {
	word, err := forest.ParseSourceWord(r.URL.Query().Get("word"))
	if err != nil {
		slog.Warn("forest saved: invalid word", "err", err)
		writeForestError(w, http.StatusBadRequest, "invalid 'word' parameter: 1-40 letters, spaces, hyphens or apostrophes")
		return
	}
	maxHops, err := parseForestHops(r)
	if err != nil {
		slog.Warn("forest saved: invalid max_hops", "word", word, "err", err)
		writeForestError(w, http.StatusBadRequest, "invalid 'max_hops' parameter: must be an integer from 1 to 5")
		return
	}
	forests := []forest.Forest{}
	if h.Cache != nil {
		if forests, err = h.Cache.List(r.Context(), word, maxHops); err != nil {
			slog.Error("forest saved: cache read failed", "word", word, "max_hops", maxHops, "err", err)
			writeForestError(w, http.StatusInternalServerError, "saved forests could not be read")
			return
		}
	}
	slog.Info("forest saved: listed", "word", word, "max_hops", maxHops, "forests", len(forests))
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	if err := json.NewEncoder(w).Encode(struct {
		Forests []forest.Forest `json:"forests"`
	}{forests}); err != nil {
		slog.Error("failed to encode saved forests", "word", word, "err", err)
	}
}

func writeForest(w http.ResponseWriter, word string, f forest.Forest) {
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(f); err != nil {
		slog.Error("failed to encode forest response", "word", word, "err", err)
	}
}

// originPattern bounds the self-declared origin of a request, a label for
// telling enrichment from live use in the ledger, not an identity.
var originPattern = regexp.MustCompile(`^[a-z0-9-]{1,32}$`)

func parseOrigin(r *http.Request) string {
	o := strings.ToLower(strings.TrimSpace(r.Header.Get("X-Metaforge-Origin")))
	if !originPattern.MatchString(o) {
		return "web"
	}
	return o
}

func newRunID() string {
	b := make([]byte, 8)
	if _, err := rand.Read(b); err != nil {
		// crypto/rand does not fail on supported platforms; a time-based
		// id still groups this run's calls.
		slog.Error("forest: random run id unavailable", "err", err)
		return strconv.FormatInt(time.Now().UnixNano(), 36)
	}
	return hex.EncodeToString(b)
}

// isDirectLoopback reports a request made on this host, not through the
// proxy: Caddy connects from loopback but always sets X-Forwarded-For.
func isDirectLoopback(r *http.Request) bool {
	if r.Header.Get("X-Forwarded-For") != "" {
		return false
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return false
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}

// BudgetHandler serves GET /forge/budget: the rolling-week spend and cap.
type BudgetHandler struct {
	Budget ForestBudget // nil: no ledger configured
}

func (h *BudgetHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if !isDirectLoopback(r) {
		// The public sees no such route; spend is the operator's business.
		http.NotFound(w, r)
		return
	}
	if h.Budget == nil {
		writeForestError(w, http.StatusServiceUnavailable, "model spend is not tracked on this server")
		return
	}
	st, err := h.Budget.Status(r.Context())
	if err != nil {
		slog.Error("budget: status unreadable", "err", err)
		writeForestError(w, http.StatusServiceUnavailable, "model spend is unreadable")
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	if err := json.NewEncoder(w).Encode(st); err != nil {
		slog.Error("budget: failed to encode status", "err", err)
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
