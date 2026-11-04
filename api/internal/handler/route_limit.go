package handler

import (
	"log/slog"
	"math"
	"net/http"
	"strconv"
	"sync"
	"time"

	"github.com/snailuj/metaforge/internal/forest"
)

// maxLoggedVisitors bounds the per-window set of visitors whose first
// refusal has been logged; past it, refusals are only counted.
const maxLoggedVisitors = 256

// VisitorRateLimit limits each visitor to the limiter's allowance on one
// route, answering 429 with Retry-After beyond it. A request made directly
// on this host (no X-Forwarded-For) is exempt, as for forests. Each route
// takes its own limiter, so spending one allowance never uses another.
func VisitorRateLimit(route string, l *forest.VisitorLimiter, now func() time.Time) func(http.Handler) http.Handler {
	refusals := &refusalLog{route: route, window: l.Window(), now: now, seen: map[string]struct{}{}}
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			key, exempt := visitorKey(r)
			if exempt {
				next.ServeHTTP(w, r)
				return
			}
			_, wait, ok := l.Take(key)
			if ok {
				next.ServeHTTP(w, r)
				return
			}
			secs := max(1, int(math.Ceil(wait.Seconds())))
			refusals.note(key, secs)
			w.Header().Set("Retry-After", strconv.Itoa(secs))
			writeForestError(w, http.StatusTooManyRequests, "too many requests from this address, slow down and try again shortly")
		})
	}
}

// refusalLog keeps a flood of refusals out of the journal: one line for a
// visitor's first refusal in each window, and a summary of the window just
// ended when the next one opens.
type refusalLog struct {
	route  string
	window time.Duration
	now    func() time.Time

	mu      sync.Mutex
	start   time.Time
	seen    map[string]struct{}
	refused int
}

func (l *refusalLog) note(visitor string, retryAfterSecs int) {
	l.mu.Lock()
	defer l.mu.Unlock()

	now := l.now()
	if l.refused > 0 && now.Sub(l.start) >= l.window {
		slog.Warn("route: refusals in the last window", "route", l.route, "refused", l.refused, "visitors_logged", len(l.seen), "window", l.window.String())
		clear(l.seen)
		l.refused = 0
	}
	if l.refused == 0 {
		l.start = now
	}
	l.refused++
	if _, logged := l.seen[visitor]; logged || len(l.seen) >= maxLoggedVisitors {
		return
	}
	l.seen[visitor] = struct{}{}
	slog.Warn("route: visitor limit reached", "route", l.route, "visitor", visitor, "retry_after_s", retryAfterSecs)
}
