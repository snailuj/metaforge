package handler

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// Rule: however many requests arrive at once, no more than the cap are ever
// inside the gated routes together, and every request still gets served
// when the wait is long enough.
func TestGateNeverExceedsItsCap(t *testing.T) {
	const limit, requests = 3, 40
	g := NewGate(limit, 10*time.Second, time.Now)
	var inside, peak atomic.Int32
	h := g.Middleware(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		n := inside.Add(1)
		for p := peak.Load(); n > p && !peak.CompareAndSwap(p, n); p = peak.Load() {
		}
		time.Sleep(5 * time.Millisecond)
		inside.Add(-1)
	}))

	var wg sync.WaitGroup
	var served atomic.Int32
	for i := 0; i < requests; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			w := httptest.NewRecorder()
			h.ServeHTTP(w, httptest.NewRequest("GET", "/x", nil))
			if w.Code == http.StatusOK {
				served.Add(1)
			}
		}()
	}
	wg.Wait()

	if got := peak.Load(); got > limit {
		t.Errorf("%d requests inside at once, cap is %d", got, limit)
	}
	if got := peak.Load(); got < limit {
		t.Errorf("peak concurrency %d never reached the cap %d, so the test proves nothing", got, limit)
	}
	if served.Load() != requests {
		t.Errorf("served %d of %d", served.Load(), requests)
	}
}

// Rule: a request that cannot get a slot within the wait is refused with a
// 503 and Retry-After; it is never queued for longer, and a freed slot is
// usable again.
func TestGateRefusesAfterTheWait(t *testing.T) {
	g := NewGate(1, 50*time.Millisecond, time.Now)
	hold, entered := make(chan struct{}), make(chan struct{})
	h := g.Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/hold" {
			close(entered)
			<-hold
		}
	}))
	done := make(chan struct{})
	go func() {
		h.ServeHTTP(httptest.NewRecorder(), httptest.NewRequest("GET", "/hold", nil))
		close(done)
	}()
	<-entered

	start := time.Now()
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest("GET", "/x", nil))

	if w.Code != http.StatusServiceUnavailable || w.Header().Get("Retry-After") == "" {
		t.Errorf("status %d, Retry-After %q; want 503 with a Retry-After", w.Code, w.Header().Get("Retry-After"))
	}
	if errorBody(t, w) == "" {
		t.Error("no error message")
	}
	if took := time.Since(start); took > 2*time.Second {
		t.Errorf("refusal took %v, the wait is 50ms", took)
	}

	close(hold)
	<-done
	if w := httptest.NewRecorder(); func() int { h.ServeHTTP(w, httptest.NewRequest("GET", "/x", nil)); return w.Code }() != http.StatusOK {
		t.Errorf("slot not reusable after release: status %d", w.Code)
	}
}

// Rule: a request whose client has gone while it waits is dropped without
// taking a slot or being counted as a refusal.
func TestGateDropsRequestsWhoseClientLeft(t *testing.T) {
	g := NewGate(1, 10*time.Second, time.Now)
	release, err := g.Acquire(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	defer release()

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	called := false
	h := g.Middleware(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { called = true }))
	h.ServeHTTP(httptest.NewRecorder(), httptest.NewRequest("GET", "/x", nil).WithContext(ctx))
	if called {
		t.Error("handler ran for a request with no client")
	}
}

// Rule: a flood of refusals logs one line, then one summary per window.
func TestGateLogsRefusalsOncePerWindow(t *testing.T) {
	buf := logCapture(t)
	g := NewGate(1, time.Millisecond, time.Now)
	release, _ := g.Acquire(context.Background())
	defer release()
	for i := 0; i < 30; i++ {
		if _, err := g.Acquire(context.Background()); err == nil {
			t.Fatal("acquired a slot past the cap")
		}
	}
	if got := countLines(buf.String(), "in-flight cap reached"); got != 1 {
		t.Errorf("%d log lines for 30 refusals, want 1:\n%s", got, buf)
	}
}
