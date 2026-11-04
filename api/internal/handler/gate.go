package handler

import (
	"context"
	"errors"
	"net/http"
	"time"
)

// DBMaxOpenConns is the lexicon pool size; the gate is sized from it.
const DBMaxOpenConns = 4

// ErrBusy means the gate gave no slot within its wait.
var ErrBusy = errors.New("database routes are busy")

// Gate caps how many requests are inside the database routes at once, all
// routes sharing it, so a flood from many addresses queues for the few
// connections the lexicon pool has instead of piling up behind them. A
// request waits a bounded time for a slot, then is refused.
type Gate struct {
	slots    chan struct{}
	wait     time.Duration
	refusals *refusalLog
}

// NewGate allows at most size requests in at once; one waits up to wait.
func NewGate(size int, wait time.Duration, now func() time.Time) *Gate {
	return &Gate{
		slots:    make(chan struct{}, max(size, 1)),
		wait:     wait,
		refusals: &refusalLog{route: "database", msg: "in-flight cap reached", window: time.Minute, now: now, seen: map[string]struct{}{}},
	}
}

// Acquire takes a slot, waiting up to the gate's wait. It returns ErrBusy
// when none came free, or ctx's error when the caller left first.
func (g *Gate) Acquire(ctx context.Context) (release func(), err error) {
	release = func() { <-g.slots }
	select {
	case g.slots <- struct{}{}:
		return release, nil
	default:
	}
	timer := time.NewTimer(g.wait)
	defer timer.Stop()
	select {
	case g.slots <- struct{}{}:
		return release, nil
	case <-ctx.Done():
		return nil, ctx.Err()
	case <-timer.C:
		g.refusals.note("all", 1)
		return nil, ErrBusy
	}
}

// Middleware holds a slot for the whole of the wrapped handler.
func (g *Gate) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		release, err := g.Acquire(r.Context())
		if err != nil {
			if errors.Is(err, ErrBusy) {
				writeBusy(w)
			}
			return // otherwise the client left; nobody to answer
		}
		defer release()
		next.ServeHTTP(w, r)
	})
}

// WrapKnownWord gates a lemma check, for the forest route, which must not
// hold a slot through its minute-long model calls.
func (g *Gate) WrapKnownWord(known func(context.Context, string) (bool, error)) func(context.Context, string) (bool, error) {
	return func(ctx context.Context, word string) (bool, error) {
		release, err := g.Acquire(ctx)
		if err != nil {
			return false, err
		}
		defer release()
		return known(ctx, word)
	}
}

func writeBusy(w http.ResponseWriter) {
	w.Header().Set("Retry-After", "1")
	writeForestError(w, http.StatusServiceUnavailable, "the server is busy, try again in a moment")
}
