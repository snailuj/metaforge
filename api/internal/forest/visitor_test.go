package forest

import (
	"testing"
	"time"
)

// Rule: one visitor may generate perHour forests at once, then waits for the
// next token, which arrives hour/perHour after the last one was spent.
func TestVisitorLimiterBurstThenWait(t *testing.T) {
	clock := newFakeClock()
	l := NewVisitorLimiter(3, 100, clock.Now)

	for i := 0; i < 3; i++ {
		if _, _, ok := l.Take("203.0.113.7"); !ok {
			t.Fatalf("take %d refused within the allowance", i+1)
		}
	}
	_, wait, ok := l.Take("203.0.113.7")
	if ok {
		t.Fatal("fourth take admitted past an allowance of 3")
	}
	if wait != 20*time.Minute {
		t.Errorf("retry-after = %v, want 20m (one hour / 3)", wait)
	}
}

// Rule: tokens come back evenly over the hour, capped at the allowance.
func TestVisitorLimiterRefills(t *testing.T) {
	clock := newFakeClock()
	l := NewVisitorLimiter(3, 100, clock.Now)
	for i := 0; i < 3; i++ {
		l.Take("203.0.113.7")
	}

	clock.Advance(20 * time.Minute)
	if _, _, ok := l.Take("203.0.113.7"); !ok {
		t.Fatal("no token back after hour/perHour")
	}
	if _, _, ok := l.Take("203.0.113.7"); ok {
		t.Fatal("two tokens back after hour/perHour")
	}

	clock.Advance(10 * time.Hour)
	for i := 0; i < 3; i++ {
		if _, _, ok := l.Take("203.0.113.7"); !ok {
			t.Fatalf("take %d refused after a long idle", i+1)
		}
	}
	if _, _, ok := l.Take("203.0.113.7"); ok {
		t.Fatal("a long idle refilled past the allowance")
	}
}

// Rule: each visitor has an allowance of their own.
func TestVisitorLimiterVisitorsAreIndependent(t *testing.T) {
	l := NewVisitorLimiter(1, 100, newFakeClock().Now)
	if _, _, ok := l.Take("a"); !ok {
		t.Fatal("a refused")
	}
	if _, _, ok := l.Take("b"); !ok {
		t.Fatal("b refused after a spent its allowance")
	}
	if _, _, ok := l.Take("a"); ok {
		t.Fatal("a admitted twice on an allowance of 1")
	}
}

// Rule: a refund returns the token once, however many times it is called,
// so a request refused further on costs the visitor nothing.
func TestVisitorLimiterRefundOnce(t *testing.T) {
	l := NewVisitorLimiter(1, 100, newFakeClock().Now)
	refund, _, ok := l.Take("a")
	if !ok {
		t.Fatal("first take refused")
	}
	refund()
	refund()
	if _, _, ok := l.Take("a"); !ok {
		t.Fatal("refunded token not returned")
	}
	if _, _, ok := l.Take("a"); ok {
		t.Fatal("double refund returned two tokens")
	}
}

// Rule: memory is bounded. With the table full of visitors still within
// their hour, a new visitor is refused rather than tracked; once the others
// have been idle long enough to refill, they are dropped to make room.
func TestVisitorLimiterBoundsTrackedVisitors(t *testing.T) {
	clock := newFakeClock()
	l := NewVisitorLimiter(2, 2, clock.Now)
	l.Take("a")
	l.Take("b")

	_, wait, ok := l.Take("c")
	if ok {
		t.Fatal("third visitor tracked past a table of 2")
	}
	if wait <= 0 {
		t.Errorf("a full table must still give a positive retry-after, got %v", wait)
	}
	if n := l.Tracked(); n != 2 {
		t.Errorf("tracked = %d, want 2", n)
	}

	clock.Advance(time.Hour)
	if _, _, ok := l.Take("c"); !ok {
		t.Fatal("idle visitors were not dropped to make room")
	}
	if n := l.Tracked(); n != 1 {
		t.Errorf("tracked after pruning = %d, want 1 (only c)", n)
	}
}

// Rule: a limiter's tokens refill evenly over its own window, whatever its
// length, and a different visitor has a bucket of its own.
func TestWindowedLimiterRefillsOverItsWindow(t *testing.T) {
	clock := newFakeClock()
	l := NewWindowedLimiter("test", 6, 100, time.Minute, clock.Now)

	for i := 0; i < 6; i++ {
		if _, _, ok := l.Take("203.0.113.7"); !ok {
			t.Fatalf("take %d refused within the allowance", i+1)
		}
	}
	_, wait, ok := l.Take("203.0.113.7")
	if ok || wait != 10*time.Second {
		t.Fatalf("seventh take: ok=%v wait=%v, want refused with 10s (one minute / 6)", ok, wait)
	}
	if _, _, ok := l.Take("198.51.100.9"); !ok {
		t.Error("another visitor was refused")
	}

	clock.Advance(10 * time.Second)
	if _, _, ok := l.Take("203.0.113.7"); !ok {
		t.Error("no token back after window/perWindow")
	}
	if _, _, ok := l.Take("203.0.113.7"); ok {
		t.Error("two tokens back after window/perWindow")
	}
}
