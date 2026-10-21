package forest

import (
	"sync"
	"time"
)

const (
	limiterWindow = time.Minute
	// concurrencyRetryAfter is a guess: the slot frees when some other
	// request finishes, which the limiter cannot predict.
	concurrencyRetryAfter = 5 * time.Second
)

// Limiter guards LLM spend with a concurrency cap and a fixed one-minute
// window counter. It never blocks.
type Limiter struct {
	maxConcurrent int
	perMinute     int
	now           func() time.Time

	mu          sync.Mutex
	inFlight    int
	windowStart time.Time
	count       int
}

// NewLimiter takes an injectable clock so tests control the window.
func NewLimiter(maxConcurrent, perMinute int, now func() time.Time) *Limiter {
	return &Limiter{maxConcurrent: maxConcurrent, perMinute: perMinute, now: now}
}

// Acquire admits or refuses a request. On success the caller must call
// release when done; release is safe to call more than once. On refusal,
// retryAfter says when to try again. A refusal uses neither a slot nor quota.
func (l *Limiter) Acquire() (release func(), retryAfter time.Duration, ok bool) {
	l.mu.Lock()
	defer l.mu.Unlock()

	now := l.now()
	if l.windowStart.IsZero() || !now.Before(l.windowStart.Add(limiterWindow)) {
		l.windowStart, l.count = now, 0
	}
	if l.inFlight >= l.maxConcurrent {
		return nil, concurrencyRetryAfter, false
	}
	if l.count >= l.perMinute {
		return nil, l.windowStart.Add(limiterWindow).Sub(now), false
	}

	l.inFlight++
	l.count++
	var once sync.Once
	return func() {
		once.Do(func() {
			l.mu.Lock()
			l.inFlight--
			l.mu.Unlock()
		})
	}, 0, true
}
