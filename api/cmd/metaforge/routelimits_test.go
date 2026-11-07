package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/snailuj/metaforge/internal/handler"
)

func clearRouteLimitEnv(t *testing.T) {
	t.Helper()
	for _, k := range []string{
		"METAFORGE_AUTOCOMPLETE_PER_VISITOR_MINUTE",
		"METAFORGE_LOOKUP_PER_VISITOR_MINUTE",
		"METAFORGE_SUGGEST_PER_VISITOR_MINUTE",
		"METAFORGE_FOREST_READ_PER_VISITOR_MINUTE",
	} {
		t.Setenv(k, "")
	}
}

// Rule: each limit has a default a real user never reaches and is set by its
// own variable; a value outside its range falls back rather than disabling
// the guard.
func TestLoadRouteLimits(t *testing.T) {
	clearRouteLimitEnv(t)
	if got, want := loadRouteLimits(), (routeLimitSettings{Autocomplete: 600, Lookup: 1500, Suggest: 150, Forest: 120}); got != want {
		t.Errorf("defaults = %+v, want %+v", got, want)
	}

	t.Setenv("METAFORGE_AUTOCOMPLETE_PER_VISITOR_MINUTE", "7")
	t.Setenv("METAFORGE_LOOKUP_PER_VISITOR_MINUTE", "8")
	t.Setenv("METAFORGE_SUGGEST_PER_VISITOR_MINUTE", "9")
	t.Setenv("METAFORGE_FOREST_READ_PER_VISITOR_MINUTE", "10")
	if got, want := loadRouteLimits(), (routeLimitSettings{Autocomplete: 7, Lookup: 8, Suggest: 9, Forest: 10}); got != want {
		t.Errorf("overrides = %+v, want %+v", got, want)
	}

	for _, bad := range []string{"0", "-5", "abc", "99999999999"} {
		t.Setenv("METAFORGE_LOOKUP_PER_VISITOR_MINUTE", bad)
		if got := loadRouteLimits().Lookup; got != 1500 {
			t.Errorf("%q gave lookup limit %d, want the default 1500", bad, got)
		}
	}
}

// Rule: the built routes limit each visitor separately per route, and one
// visitor's refusals never touch another's.
func TestDatabaseRoutesAreLimitedPerRoutePerVisitor(t *testing.T) {
	lexicon, err := handler.NewHandler("../../../data-pipeline/output/lexicon_v2.db")
	if err != nil {
		t.Skipf("skipping: cannot open test DB: %v", err)
	}
	defer lexicon.Close()
	r := chi.NewRouter()
	registerDatabaseRoutes(r, lexicon, routeLimitSettings{Autocomplete: 2, Lookup: 3, Suggest: 1}, newDatabaseGate())

	get := func(path, query, visitor string) int {
		req := httptest.NewRequest("GET", path+"?"+query, nil)
		req.RemoteAddr = "127.0.0.1:4000"
		req.Header.Set("X-Forwarded-For", visitor)
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)
		return w.Code
	}
	lookup := "word=" + url.QueryEscape("anger")
	auto := "prefix=ang"
	suggest := "word=anger"
	const a, b = "203.0.113.7", "198.51.100.9"

	for i := 0; i < 3; i++ {
		if code := get("/thesaurus/lookup", lookup, a); code != http.StatusOK {
			t.Fatalf("lookup %d within allowance: %d", i+1, code)
		}
	}
	if code := get("/thesaurus/lookup", lookup, a); code != http.StatusTooManyRequests {
		t.Errorf("lookup past allowance: %d, want 429", code)
	}
	if code := get("/thesaurus/lookup", lookup, b); code != http.StatusOK {
		t.Errorf("another visitor's lookup: %d", code)
	}
	for i := 0; i < 2; i++ {
		if code := get("/thesaurus/autocomplete", auto, a); code != http.StatusOK {
			t.Errorf("autocomplete %d after lookup was spent: %d", i+1, code)
		}
	}
	if code := get("/thesaurus/autocomplete", auto, a); code != http.StatusTooManyRequests {
		t.Errorf("autocomplete past allowance: %d, want 429", code)
	}
	if code := get("/forge/suggest", suggest, a); code == http.StatusTooManyRequests {
		t.Error("suggest refused although its own allowance was untouched")
	}
	if code := get("/forge/suggest", suggest, a); code != http.StatusTooManyRequests {
		t.Errorf("suggest past allowance: %d, want 429", code)
	}
}

// Rule: the database routes share one in-flight cap sized from the lexicon
// pool, and a busy server answers 503 rather than queueing without end.
func TestDatabaseRoutesShareTheGate(t *testing.T) {
	lexicon, err := handler.NewHandler("../../../data-pipeline/output/lexicon_v2.db")
	if err != nil {
		t.Skipf("skipping: cannot open test DB: %v", err)
	}
	defer lexicon.Close()
	if got, want := databaseGateSize, 2*handler.DBMaxOpenConns; got != want {
		t.Errorf("gate size %d, want twice the pool (%d)", got, want)
	}
	gate := handler.NewGate(1, 20*time.Millisecond, time.Now)
	r := chi.NewRouter()
	registerDatabaseRoutes(r, lexicon, loadRouteLimits(), gate)

	release, err := gate.Acquire(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	for _, target := range []string{"/thesaurus/lookup?word=anger", "/thesaurus/autocomplete?prefix=ang", "/forge/suggest?word=anger"} {
		w := httptest.NewRecorder()
		r.ServeHTTP(w, httptest.NewRequest("GET", target, nil))
		if w.Code != http.StatusServiceUnavailable || w.Header().Get("Retry-After") == "" {
			t.Errorf("%s with the gate full: status %d, Retry-After %q", target, w.Code, w.Header().Get("Retry-After"))
		}
	}
	release()
	w := httptest.NewRecorder()
	r.ServeHTTP(w, httptest.NewRequest("GET", "/thesaurus/lookup?word=anger", nil))
	if w.Code != http.StatusOK {
		t.Errorf("lookup after the slot freed: status %d", w.Code)
	}
}

// Rule: /forge/forest has a per-visitor read allowance of its own, applied
// before anything else, and one visitor's refusals never touch another's.
func TestForestRouteHasItsOwnReadLimit(t *testing.T) {
	clearForestEnv(t)
	fh := newForestHandler(loadForestSettings(), anyWord) // no key: answers 503 once past the limit
	r := chi.NewRouter()
	registerForestRoute(r, fh, routeLimitSettings{Forest: 2})

	get := func(visitor string) int {
		req := httptest.NewRequest("GET", "/forge/forest?word=anger", nil)
		req.RemoteAddr = "127.0.0.1:4000"
		req.Header.Set("X-Forwarded-For", visitor)
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)
		return w.Code
	}
	for i := 0; i < 2; i++ {
		if code := get("203.0.113.7"); code == http.StatusTooManyRequests {
			t.Fatalf("request %d refused within the allowance", i+1)
		}
	}
	if code := get("203.0.113.7"); code != http.StatusTooManyRequests {
		t.Errorf("past the allowance: %d, want 429", code)
	}
	if code := get("198.51.100.9"); code == http.StatusTooManyRequests {
		t.Error("another visitor was refused")
	}
}
