package forest

import (
	"sync"
	"testing"
	"time"
)

type fakeClock struct {
	mu sync.Mutex
	t  time.Time
}

func newFakeClock() *fakeClock { return &fakeClock{t: time.Date(2026, 10, 21, 12, 0, 0, 0, time.UTC)} }

func (c *fakeClock) Now() time.Time {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.t
}

func (c *fakeClock) Advance(d time.Duration) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.t = c.t.Add(d)
}

// Rule: in-flight requests never exceed the concurrency cap, and a release
// frees exactly one slot, however many times it is called.
func TestLimiterConcurrencyCap(t *testing.T) {
	l := NewLimiter(2, 100, newFakeClock().Now)

	r1, _, ok1 := l.Acquire()
	r2, _, ok2 := l.Acquire()
	_, wait, ok3 := l.Acquire()
	if !ok1 || !ok2 || ok3 {
		t.Fatalf("admitted = %v %v %v, want true true false", ok1, ok2, ok3)
	}
	if wait <= 0 {
		t.Errorf("refusal must carry a positive retry-after, got %v", wait)
	}

	r1()
	r1() // a second release must not free a second slot
	if _, _, ok := l.Acquire(); !ok {
		t.Fatal("slot not freed by release")
	}
	if _, _, ok := l.Acquire(); ok {
		t.Fatal("double release freed an extra slot")
	}
	r2()
}

// Rule: at most perMinute requests are admitted in a fixed one-minute
// window; the retry-after is the time left in that window.
func TestLimiterPerMinuteWindow(t *testing.T) {
	clock := newFakeClock()
	l := NewLimiter(100, 3, clock.Now)

	for i := 0; i < 3; i++ {
		release, _, ok := l.Acquire()
		if !ok {
			t.Fatalf("request %d refused inside quota", i+1)
		}
		release()
		clock.Advance(10 * time.Second)
	}
	// 30 s into the window.
	_, wait, ok := l.Acquire()
	if ok {
		t.Fatal("fourth request admitted in the same window")
	}
	if wait != 30*time.Second {
		t.Errorf("retry-after = %v, want 30s", wait)
	}

	clock.Advance(30 * time.Second) // window ends exactly now
	if release, _, ok := l.Acquire(); !ok {
		t.Fatal("request refused after the window rolled")
	} else {
		release()
	}
}

// Rule: a refused request consumes neither a slot nor quota.
func TestLimiterRefusalsAreFree(t *testing.T) {
	clock := newFakeClock()
	l := NewLimiter(1, 2, clock.Now)

	r1, _, _ := l.Acquire() // quota 1/2, slot taken
	for i := 0; i < 10; i++ {
		if _, _, ok := l.Acquire(); ok {
			t.Fatal("admitted over the concurrency cap")
		}
	}
	r1()
	r2, _, ok := l.Acquire() // quota 2/2: concurrency refusals did not use quota
	if !ok {
		t.Fatal("concurrency refusals consumed quota")
	}
	r2()
	if _, _, ok := l.Acquire(); ok {
		t.Fatal("quota not enforced")
	}
	clock.Advance(time.Minute)
	if _, _, ok := l.Acquire(); !ok {
		t.Fatal("quota refusal blocked the next window")
	}
}

func TestLimiterConcurrentUse(t *testing.T) {
	const cap = 4
	l := NewLimiter(cap, 1000, newFakeClock().Now)
	var (
		wg           sync.WaitGroup
		mu           sync.Mutex
		inFlight, hi int
	)
	for i := 0; i < 200; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			release, _, ok := l.Acquire()
			if !ok {
				return
			}
			mu.Lock()
			inFlight++
			hi = max(hi, inFlight)
			mu.Unlock()
			time.Sleep(time.Millisecond)
			mu.Lock()
			inFlight--
			mu.Unlock()
			release()
		}()
	}
	wg.Wait()
	if hi > cap {
		t.Errorf("peak concurrency %d exceeded cap %d", hi, cap)
	}
}
