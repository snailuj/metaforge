package handler

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/snailuj/metaforge/internal/forest"
)

// visitorHandler allows each visitor perHour generated forests and leaves
// the shared limiter wide open, so only the per-visitor rule is under test.
func visitorHandler(gen ForestGenerator, perHour int) *ForestHandler {
	h := newForestTestHandler(gen, 100, 100)
	h.Visitors = forest.NewVisitorLimiter(perHour, 1000, fixedClock())
	return h
}

// viaProxy is a request as Caddy forwards it: from loopback, with the
// client's address in X-Forwarded-For. An empty xff is a direct local call.
func viaProxy(h *ForestHandler, query, xff string, headers map[string]string) *httptest.ResponseRecorder {
	req := httptest.NewRequest("GET", "/forge/forest?"+query, nil)
	req.RemoteAddr = "127.0.0.1:41234"
	if xff != "" {
		req.Header.Set("X-Forwarded-For", xff)
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	w := httptest.NewRecorder()
	h.HandleForest(w, req)
	return w
}

// Rule: one visitor gets perHour generated forests, then a 429 whose
// Retry-After is when their next one frees up; other visitors are unaffected.
func TestForestPerVisitorLimitThroughProxy(t *testing.T) {
	gen := &fakeForestGen{}
	h := visitorHandler(gen, 2)

	for i := 0; i < 2; i++ {
		if w := viaProxy(h, "word=anger&fresh=1", "203.0.113.7", nil); w.Code != http.StatusOK {
			t.Fatalf("request %d status = %d", i+1, w.Code)
		}
	}
	w := viaProxy(h, "word=anger&fresh=1", "203.0.113.7", nil)
	if w.Code != http.StatusTooManyRequests {
		t.Fatalf("third request status = %d, want 429", w.Code)
	}
	if ra := w.Header().Get("Retry-After"); ra != "1800" {
		t.Errorf("Retry-After = %q, want 1800 (one hour / 2)", ra)
	}
	if errorBody(t, w) == "" {
		t.Error("empty 429 message")
	}
	if gen.called != 2 {
		t.Errorf("generator called %d times, want 2", gen.called)
	}
	if w := viaProxy(h, "word=anger&fresh=1", "198.51.100.9", nil); w.Code != http.StatusOK {
		t.Errorf("another visitor got %d, want 200", w.Code)
	}
}

// Rule: a request made on this host, not through Caddy (the enricher, a
// deploy check), is not a visitor and is not limited.
func TestForestVisitorLimitExemptsDirectLoopback(t *testing.T) {
	gen := &fakeForestGen{}
	h := visitorHandler(gen, 1)
	for i := 0; i < 3; i++ {
		if w := viaProxy(h, "word=anger&fresh=1", "", nil); w.Code != http.StatusOK {
			t.Fatalf("direct request %d status = %d", i+1, w.Code)
		}
	}
}

// Rule: the visitor is the entry Caddy added, the last one; whatever a
// client wrote before it cannot buy a fresh allowance.
func TestForestVisitorIsTheProxyAddedEntry(t *testing.T) {
	h := visitorHandler(&fakeForestGen{}, 1)
	if w := viaProxy(h, "word=anger&fresh=1", "192.0.2.1, 203.0.113.7", nil); w.Code != http.StatusOK {
		t.Fatalf("first status = %d", w.Code)
	}
	if w := viaProxy(h, "word=anger&fresh=1", "192.0.2.2, 203.0.113.7", nil); w.Code != http.StatusTooManyRequests {
		t.Errorf("a changed spoofed prefix got %d, want 429", w.Code)
	}
}

// Rule: IPv6 visitors are grouped by /64, the block one subscriber gets, so
// rotating addresses inside it buys nothing.
func TestForestVisitorIPv6SharesSlash64(t *testing.T) {
	h := visitorHandler(&fakeForestGen{}, 1)
	if w := viaProxy(h, "word=anger&fresh=1", "2001:db8:1:2::1", nil); w.Code != http.StatusOK {
		t.Fatalf("first status = %d", w.Code)
	}
	if w := viaProxy(h, "word=anger&fresh=1", "2001:db8:1:2:ffff::9", nil); w.Code != http.StatusTooManyRequests {
		t.Errorf("same /64 got %d, want 429", w.Code)
	}
	if w := viaProxy(h, "word=anger&fresh=1", "2001:db8:1:3::1", nil); w.Code != http.StatusOK {
		t.Errorf("another /64 got %d, want 200", w.Code)
	}
}

// Rule: a request refused for its visitor uses none of the shared
// per-minute quota, so one visitor over their limit cannot lock out others.
func TestForestVisitorRefusalSpendsNoSharedQuota(t *testing.T) {
	h := newForestTestHandler(&fakeForestGen{}, 100, 2)
	h.Visitors = forest.NewVisitorLimiter(1, 1000, fixedClock())

	viaProxy(h, "word=anger&fresh=1", "203.0.113.7", nil)
	if w := viaProxy(h, "word=anger&fresh=1", "203.0.113.7", nil); w.Code != http.StatusTooManyRequests {
		t.Fatalf("over-limit visitor got %d, want 429", w.Code)
	}
	if w := viaProxy(h, "word=anger&fresh=1", "198.51.100.9", nil); w.Code != http.StatusOK {
		t.Errorf("next visitor got %d: the refusal used shared quota", w.Code)
	}
}

// Rule: a request the shared limiter refuses gives the visitor their
// forest back, since nothing was generated.
func TestForestSharedRefusalRefundsVisitor(t *testing.T) {
	h := newForestTestHandler(&fakeForestGen{}, 100, 1)
	h.Visitors = forest.NewVisitorLimiter(1, 1000, fixedClock())

	viaProxy(h, "word=anger&fresh=1", "203.0.113.7", nil)
	if w := viaProxy(h, "word=anger&fresh=1", "198.51.100.9", nil); w.Code != http.StatusTooManyRequests {
		t.Fatalf("shared limiter let a second request through: %d", w.Code)
	}
	if _, _, ok := h.Visitors.Take("198.51.100.9"); !ok {
		t.Error("visitor refused by the shared limiter lost their forest")
	}
}

// Rule: cached forests spend nothing, so they never use the allowance.
func TestForestCacheHitsSpendNoVisitorAllowance(t *testing.T) {
	gen := &fakeForestGen{}
	h := visitorHandler(gen, 1)
	h.Cache = &fakeForestCache{pool: []forest.Forest{forestWithLine("Patience is a seed vault.")}}

	for i := 0; i < 3; i++ {
		if w := viaProxy(h, "word=patience", "203.0.113.7", nil); w.Code != http.StatusOK || w.Header().Get("X-Forest-Cache") != "hit" {
			t.Fatalf("cached request %d: status %d, cache %q", i+1, w.Code, w.Header().Get("X-Forest-Cache"))
		}
	}
	if w := viaProxy(h, "word=patience&fresh=1", "203.0.113.7", nil); w.Code != http.StatusOK {
		t.Errorf("first generated forest after cache hits got %d", w.Code)
	}
	if gen.called != 1 {
		t.Errorf("generator called %d times, want 1", gen.called)
	}
}

// Rule: a browser request from another site's page never generates; the
// refusal costs the visitor nothing. Same-origin requests, ones the user
// typed (none), and non-browser clients (no header) are served.
func TestForestRefusesOtherSiteRequests(t *testing.T) {
	gen := &fakeForestGen{}
	h := visitorHandler(gen, 1)

	for _, site := range []string{"cross-site", "same-site"} {
		w := viaProxy(h, "word=anger&fresh=1", "203.0.113.7", map[string]string{"Sec-Fetch-Site": site})
		if w.Code != http.StatusForbidden {
			t.Errorf("Sec-Fetch-Site %s: status %d, want 403", site, w.Code)
		}
		if errorBody(t, w) == "" {
			t.Errorf("Sec-Fetch-Site %s: empty 403 message", site)
		}
	}
	if gen.called != 0 {
		t.Fatalf("generator called %d times for other-site requests", gen.called)
	}
	if w := viaProxy(h, "word=anger&fresh=1", "203.0.113.7", map[string]string{"Sec-Fetch-Site": "same-origin"}); w.Code != http.StatusOK {
		t.Errorf("same-origin after refusals got %d: the refusals spent the allowance", w.Code)
	}
	for i, hdr := range []map[string]string{{"Sec-Fetch-Site": "none"}, nil} {
		if w := viaProxy(h, "word=anger&fresh=1", "", hdr); w.Code != http.StatusOK {
			t.Errorf("case %d: status %d, want 200", i, w.Code)
		}
	}
}
