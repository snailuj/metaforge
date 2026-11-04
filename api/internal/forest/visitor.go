package forest

import (
	"log/slog"
	"sync"
	"time"
)

const (
	visitorWindow = time.Hour
	// visitorPruneEvery bounds how often a full table is scanned for idle
	// visitors, so a flood of new addresses cannot make every request walk
	// it. It is also the retry-after a visitor gets while the table is full.
	visitorPruneEvery = time.Minute
)

// VisitorLimiter caps what one visitor may do: a token bucket per visitor,
// allowance deep, refilling evenly over its window. It never blocks.
// It tracks at most maxVisitors at once; while the table is full of visitors
// still inside their hour, a new visitor is refused rather than tracked, so
// the limiter fails closed and its memory stays bounded.
type VisitorLimiter struct {
	name        string // names the limiter in logs
	allowance   int
	window      time.Duration
	maxVisitors int
	now         func() time.Time

	mu        sync.Mutex
	buckets   map[string]visitorBucket
	lastPrune time.Time
}

type visitorBucket struct {
	tokens float64
	at     time.Time // when tokens was last brought up to date
}

// NewVisitorLimiter limits forests per visitor per hour. It takes an
// injectable clock so tests control refills. perHour and maxVisitors below 1
// are treated as 1.
func NewVisitorLimiter(perHour, maxVisitors int, now func() time.Time) *VisitorLimiter {
	return NewWindowedLimiter("forest", perHour, maxVisitors, visitorWindow, now)
}

// NewWindowedLimiter allows each visitor perWindow takes, refilling evenly
// over window. name appears in logs. perWindow and maxVisitors below 1 are
// treated as 1, and a window below a millisecond as one.
func NewWindowedLimiter(name string, perWindow, maxVisitors int, window time.Duration, now func() time.Time) *VisitorLimiter {
	return &VisitorLimiter{
		name:        name,
		allowance:   max(perWindow, 1),
		window:      max(window, time.Millisecond),
		maxVisitors: max(maxVisitors, 1),
		now:         now,
		buckets:     map[string]visitorBucket{},
	}
}

// Take spends one of visitor's tokens. On success the caller may call refund
// to give the token back when the request is refused further on; refund is
// safe to call more than once. On refusal, retryAfter says when to try again.
func (l *VisitorLimiter) Take(visitor string) (refund func(), retryAfter time.Duration, ok bool) {
	l.mu.Lock()
	defer l.mu.Unlock()

	now := l.now()
	b, known := l.buckets[visitor]
	switch {
	case known:
		b = l.refilled(b, now)
	case len(l.buckets) >= l.maxVisitors && !l.makeRoomLocked(now):
		return nil, visitorPruneEvery, false
	default:
		b = visitorBucket{tokens: float64(l.allowance), at: now}
	}

	if b.tokens < 1 {
		l.buckets[visitor] = b
		return nil, time.Duration((1 - b.tokens) * float64(l.interval())), false
	}
	b.tokens--
	l.buckets[visitor] = b
	var once sync.Once
	return func() { once.Do(func() { l.refund(visitor) }) }, 0, true
}

// Tracked is how many visitors the limiter holds state for.
func (l *VisitorLimiter) Tracked() int {
	l.mu.Lock()
	defer l.mu.Unlock()
	return len(l.buckets)
}

func (l *VisitorLimiter) interval() time.Duration {
	return l.window / time.Duration(l.allowance)
}

// refilled brings b up to now, never past a full bucket.
func (l *VisitorLimiter) refilled(b visitorBucket, now time.Time) visitorBucket {
	if elapsed := now.Sub(b.at); elapsed > 0 {
		b.tokens = min(b.tokens+float64(elapsed)/float64(l.interval()), float64(l.allowance))
		b.at = now
	}
	return b
}

// makeRoomLocked drops visitors whose buckets have refilled, who are then no
// different from a visitor never seen, and reports whether there is room. It
// scans at most once every visitorPruneEvery. Callers hold mu.
func (l *VisitorLimiter) makeRoomLocked(now time.Time) bool {
	if !l.lastPrune.IsZero() && now.Sub(l.lastPrune) < visitorPruneEvery {
		return false
	}
	l.lastPrune = now
	before := len(l.buckets)
	for k, b := range l.buckets {
		if l.refilled(b, now).tokens >= float64(l.allowance) {
			delete(l.buckets, k)
		}
	}
	room := len(l.buckets) < l.maxVisitors
	if !room {
		slog.Warn(l.name+": visitor table full, refusing new visitors", "tracked", len(l.buckets), "max", l.maxVisitors)
	} else {
		slog.Info(l.name+": visitor table pruned", "dropped", before-len(l.buckets), "tracked", len(l.buckets))
	}
	return room
}

func (l *VisitorLimiter) refund(visitor string) {
	l.mu.Lock()
	defer l.mu.Unlock()
	b, ok := l.buckets[visitor]
	if !ok {
		return // pruned meanwhile, so already full
	}
	b = l.refilled(b, l.now())
	b.tokens = min(b.tokens+1, float64(l.allowance))
	l.buckets[visitor] = b
}
