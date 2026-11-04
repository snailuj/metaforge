package handler

import (
	"bytes"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/snailuj/metaforge/internal/forest"
)

var okHandler = http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) })

func limited(route string, perMinute int) http.Handler {
	l := forest.NewWindowedLimiter(route, perMinute, 1000, time.Minute, fixedClock())
	return VisitorRateLimit(route, l, fixedClock())(okHandler)
}

// fromAddr is a request the way Caddy delivers one: from loopback, with the
// visitor's address last in X-Forwarded-For.
func fromAddr(addr string) *http.Request {
	r := httptest.NewRequest("GET", "/x", nil)
	r.RemoteAddr = "127.0.0.1:5555"
	r.Header.Set("X-Forwarded-For", addr)
	return r
}

func serveOnce(h http.Handler, r *http.Request) *httptest.ResponseRecorder {
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	return w
}

// Rule: a visitor past its allowance on a route gets a 429 that says when to
// retry, and another visitor is unaffected.
func TestRouteLimitRefusesOnlyTheVisitorOverItsAllowance(t *testing.T) {
	h := limited("autocomplete", 3)
	for i := 0; i < 3; i++ {
		if w := serveOnce(h, fromAddr("203.0.113.7")); w.Code != http.StatusOK {
			t.Fatalf("request %d within the allowance: status %d", i+1, w.Code)
		}
	}

	w := serveOnce(h, fromAddr("203.0.113.7"))

	if w.Code != http.StatusTooManyRequests {
		t.Fatalf("status = %d, want 429", w.Code)
	}
	if secs, err := strconv.Atoi(w.Header().Get("Retry-After")); err != nil || secs != 20 {
		t.Errorf("Retry-After = %q, want 20 (a minute / 3)", w.Header().Get("Retry-After"))
	}
	if msg := errorBody(t, w); msg == "" {
		t.Error("no error message")
	}
	if w := serveOnce(h, fromAddr("198.51.100.9")); w.Code != http.StatusOK {
		t.Errorf("another visitor refused: status %d", w.Code)
	}
}

// Rule: IPv6 visitors share an allowance across their /64, as for forests.
func TestRouteLimitGroupsIPv6By64(t *testing.T) {
	h := limited("lookup", 1)
	serveOnce(h, fromAddr("2001:db8:1:2::1"))
	if w := serveOnce(h, fromAddr("2001:db8:1:2:ffff::9")); w.Code != http.StatusTooManyRequests {
		t.Errorf("same /64 was not limited: status %d", w.Code)
	}
}

// Rule: a request made directly on this host, with no X-Forwarded-For, is
// never limited.
func TestRouteLimitExemptsDirectLoopback(t *testing.T) {
	h := limited("lookup", 1)
	for i := 0; i < 50; i++ {
		r := httptest.NewRequest("GET", "/x", nil)
		r.RemoteAddr = "127.0.0.1:5555"
		if w := serveOnce(h, r); w.Code != http.StatusOK {
			t.Fatalf("direct loopback request %d: status %d", i+1, w.Code)
		}
	}
}

// Rule: each route has its own allowance; spending one never uses another's.
func TestRouteLimitsAreIndependentPerRoute(t *testing.T) {
	lookup, autocomplete := limited("lookup", 2), limited("autocomplete", 2)
	for i := 0; i < 5; i++ {
		serveOnce(lookup, fromAddr("203.0.113.7"))
	}
	if w := serveOnce(lookup, fromAddr("203.0.113.7")); w.Code != http.StatusTooManyRequests {
		t.Fatalf("lookup not exhausted: status %d", w.Code)
	}
	for i := 0; i < 2; i++ {
		if w := serveOnce(autocomplete, fromAddr("203.0.113.7")); w.Code != http.StatusOK {
			t.Errorf("autocomplete request %d refused after lookup was spent: status %d", i+1, w.Code)
		}
	}
}

// logCapture swaps the default logger for one that records lines.
func logCapture(t *testing.T) *bytes.Buffer {
	t.Helper()
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewTextHandler(&buf, nil)))
	t.Cleanup(func() { slog.SetDefault(prev) })
	return &buf
}

// Rule: a flood does not fill the journal. A visitor's first refusal in a
// window is logged; its later ones are counted, and the next window opens
// with one summary line.
func TestRouteLimitLogsFirstRefusalPerVisitorPerWindow(t *testing.T) {
	buf := logCapture(t)
	clock := newClock()
	l := forest.NewWindowedLimiter("lookup", 1, 1000, time.Minute, clock.Now)
	h := VisitorRateLimit("lookup", l, clock.Now)(okHandler)

	serveOnce(h, fromAddr("203.0.113.7")) // spends the allowance
	refusals := 0
	for i := 0; i < 20; i++ {
		if serveOnce(h, fromAddr("203.0.113.7")).Code == http.StatusTooManyRequests {
			refusals++
		}
	}
	serveOnce(h, fromAddr("198.51.100.9"))
	serveOnce(h, fromAddr("198.51.100.9")) // a second visitor's first refusal
	if refusals != 20 {
		t.Fatalf("setup: %d refusals, want 20", refusals)
	}
	if got := strings.Count(buf.String(), "visitor limit reached"); got != 2 {
		t.Errorf("%d refusal lines for 2 visitors in one window:\n%s", got, buf)
	}

	buf.Reset()
	clock.Advance(2 * time.Minute)
	serveOnce(h, fromAddr("203.0.113.7")) // admitted again
	serveOnce(h, fromAddr("203.0.113.7")) // refused: new window
	out := buf.String()
	if !strings.Contains(out, "refusals in the last window") || !strings.Contains(out, "refused=21") {
		t.Errorf("no summary of the previous window:\n%s", out)
	}
	if got := strings.Count(out, "visitor limit reached"); got != 1 {
		t.Errorf("%d first-refusal lines in the new window, want 1:\n%s", got, out)
	}
}

type stepClock struct{ t time.Time }

func newClock() *stepClock                   { return &stepClock{t: time.Date(2026, 11, 4, 12, 0, 0, 0, time.UTC)} }
func (c *stepClock) Now() time.Time          { return c.t }
func (c *stepClock) Advance(d time.Duration) { c.t = c.t.Add(d) }

func countLines(out, sub string) int { return strings.Count(out, sub) }
