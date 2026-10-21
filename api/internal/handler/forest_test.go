package handler

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/snailuj/metaforge/internal/forest"
)

type fakeForestGen struct {
	forest   forest.Forest
	err      error
	called   int
	word     string
	maxHops  int
	deadline time.Time
	hasDL    bool
	block    chan struct{} // when set, Generate waits on it or on ctx
	started  chan struct{} // when set, receives one value as Generate begins
}

func (f *fakeForestGen) Generate(ctx context.Context, word string, maxHops int) (forest.Forest, error) {
	f.called++
	f.word, f.maxHops = word, maxHops
	f.deadline, f.hasDL = ctx.Deadline()
	if f.started != nil {
		f.started <- struct{}{}
	}
	if f.block != nil {
		select {
		case <-f.block:
		case <-ctx.Done():
			return forest.Forest{}, fmt.Errorf("generate: %w", ctx.Err())
		}
	}
	return f.forest, f.err
}

func fixedClock() func() time.Time {
	t := time.Date(2026, 10, 21, 12, 0, 0, 0, time.UTC)
	return func() time.Time { return t }
}

func newForestTestHandler(gen ForestGenerator, maxConcurrent, perMinute int) *ForestHandler {
	return NewForestHandler(gen, forest.NewLimiter(maxConcurrent, perMinute, fixedClock()))
}

func getForest(h *ForestHandler, query string) *httptest.ResponseRecorder {
	req := httptest.NewRequest("GET", "/forge/forest?"+query, nil)
	w := httptest.NewRecorder()
	h.HandleForest(w, req)
	return w
}

func errorBody(t *testing.T, w *httptest.ResponseRecorder) string {
	t.Helper()
	var body map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &body); err != nil {
		t.Fatalf("error body is not JSON {error}: %q", w.Body.String())
	}
	if ct := w.Header().Get("Content-Type"); !strings.HasPrefix(ct, "application/json") {
		t.Errorf("error Content-Type = %q", ct)
	}
	return body["error"]
}

func TestForestOKPassesNormalisedWordAndDefaultHops(t *testing.T) {
	gen := &fakeForestGen{forest: forest.Forest{
		Source: "patience", MaxHops: 3, Model: "m",
		Nodes: []forest.Node{{ID: "patience", Word: "patience", Role: forest.RoleSource}},
		Edges: []forest.Edge{}, Endpoints: []forest.Endpoint{},
	}}
	h := newForestTestHandler(gen, 4, 30)

	w := getForest(h, "word=++Patience+")

	if w.Code != http.StatusOK {
		t.Fatalf("status = %d: %s", w.Code, w.Body)
	}
	if gen.word != "patience" || gen.maxHops != 3 {
		t.Errorf("generator got word=%q maxHops=%d", gen.word, gen.maxHops)
	}
	if ct := w.Header().Get("Content-Type"); ct != "application/json" {
		t.Errorf("Content-Type = %q", ct)
	}
	var got forest.Forest
	if err := json.Unmarshal(w.Body.Bytes(), &got); err != nil || got.Source != "patience" || got.Model != "m" {
		t.Errorf("body = %s (%v)", w.Body, err)
	}
	// Per-request deadline: 75 s.
	if !gen.hasDL || time.Until(gen.deadline) > 75*time.Second || time.Until(gen.deadline) < 70*time.Second {
		t.Errorf("deadline = %v (set %v), want about 75 s ahead", gen.deadline, gen.hasDL)
	}
}

func TestForestPassesExplicitMaxHops(t *testing.T) {
	for _, n := range []int{1, 5} {
		gen := &fakeForestGen{}
		h := newForestTestHandler(gen, 4, 30)
		if w := getForest(h, "word=anger&max_hops="+strconv.Itoa(n)); w.Code != http.StatusOK {
			t.Fatalf("max_hops=%d: status %d", n, w.Code)
		}
		if gen.maxHops != n {
			t.Errorf("max_hops=%d reached generator as %d", n, gen.maxHops)
		}
	}
}

// Rule: a request that fails validation costs nothing: no LLM call and
// no limiter quota.
func TestForestRejectsBadInputBeforeSpending(t *testing.T) {
	cases := []string{
		"",
		"word=",
		"word=%20%20",
		"word=" + strings.Repeat("a", 41),
		"word=ignore+previous%3A+instructions",
		"word=cat1",
		"word=anger&max_hops=0",
		"word=anger&max_hops=6",
		"word=anger&max_hops=-1",
		"word=anger&max_hops=abc",
		"word=anger&max_hops=",
		"word=anger&max_hops=2.5",
	}
	gen := &fakeForestGen{}
	h := newForestTestHandler(gen, 1, 1)
	for _, q := range cases {
		w := getForest(h, q)
		if w.Code != http.StatusBadRequest {
			t.Errorf("%q: status = %d, want 400", q, w.Code)
		}
		if errorBody(t, w) == "" {
			t.Errorf("%q: empty error message", q)
		}
	}
	if gen.called != 0 {
		t.Errorf("generator called %d times for invalid input", gen.called)
	}
	if w := getForest(h, "word=anger"); w.Code != http.StatusOK {
		t.Errorf("quota was consumed by invalid requests: status %d", w.Code)
	}
}

func TestForestUnconfiguredReturns503(t *testing.T) {
	h := NewForestHandler(nil, forest.NewLimiter(4, 30, fixedClock()))

	for _, q := range []string{"word=anger", ""} {
		w := getForest(h, q)
		if w.Code != http.StatusServiceUnavailable {
			t.Errorf("%q: status = %d, want 503", q, w.Code)
		}
		if msg := errorBody(t, w); msg != "metaphor forest is not configured on this server" {
			t.Errorf("message = %q", msg)
		}
	}
}

func TestForestPerMinuteCapSetsRetryAfter(t *testing.T) {
	gen := &fakeForestGen{}
	h := newForestTestHandler(gen, 4, 1)

	if w := getForest(h, "word=anger"); w.Code != http.StatusOK {
		t.Fatalf("first request status = %d", w.Code)
	}
	w := getForest(h, "word=anger")

	if w.Code != http.StatusTooManyRequests {
		t.Fatalf("status = %d, want 429", w.Code)
	}
	if ra := w.Header().Get("Retry-After"); ra != "60" {
		t.Errorf("Retry-After = %q, want 60", ra)
	}
	if errorBody(t, w) == "" {
		t.Error("empty 429 message")
	}
	if gen.called != 1 {
		t.Errorf("generator called %d times, want 1", gen.called)
	}
}

func TestForestConcurrencyCapAndSlotRelease(t *testing.T) {
	gen := &fakeForestGen{block: make(chan struct{}), started: make(chan struct{}, 1)}
	h := newForestTestHandler(gen, 1, 100)

	done := make(chan *httptest.ResponseRecorder)
	go func() { done <- getForest(h, "word=anger") }()
	select {
	case <-gen.started:
	case <-time.After(2 * time.Second):
		t.Fatal("first request never reached the generator")
	}

	w := getForest(h, "word=envy")
	if w.Code != http.StatusTooManyRequests {
		t.Fatalf("status = %d, want 429", w.Code)
	}
	if ra, err := strconv.Atoi(w.Header().Get("Retry-After")); err != nil || ra < 1 {
		t.Errorf("Retry-After = %q, want a positive integer", w.Header().Get("Retry-After"))
	}

	close(gen.block)
	if first := <-done; first.Code != http.StatusOK {
		t.Errorf("first request status = %d", first.Code)
	}
}

// Rule: the slot is released however the request ends.
func TestForestReleasesSlotOnFailure(t *testing.T) {
	gen := &fakeForestGen{err: errors.New("boom")}
	h := newForestTestHandler(gen, 1, 100)

	for i := 0; i < 3; i++ {
		if w := getForest(h, "word=anger"); w.Code != http.StatusBadGateway {
			t.Fatalf("request %d status = %d, want 502 (a leaked slot would give 429)", i+1, w.Code)
		}
	}
}

func TestForestMapsUpstreamErrors(t *testing.T) {
	cases := []struct {
		name string
		err  error
		want int
	}{
		{"client disconnect", fmt.Errorf("generate: %w", context.Canceled), statusClientClosed},
		{"model error", errors.New("generate: anthropic messages: 500"), http.StatusBadGateway},
		{"refusal", errors.New("generate: model refused the request"), http.StatusBadGateway},
		{"deadline", fmt.Errorf("judge: %w", context.DeadlineExceeded), http.StatusGatewayTimeout},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			h := newForestTestHandler(&fakeForestGen{err: tc.err}, 4, 30)

			w := getForest(h, "word=anger")

			if w.Code != tc.want {
				t.Errorf("status = %d, want %d", w.Code, tc.want)
			}
			if tc.want == statusClientClosed {
				if w.Body.Len() != 0 {
					t.Errorf("a gone client gets no body, wrote %q", w.Body)
				}
				return
			}
			msg := errorBody(t, w)
			if msg == "" || strings.Contains(msg, "anthropic") {
				t.Errorf("message %q must be non-empty and must not leak upstream detail", msg)
			}
		})
	}
}

func TestForestRequestDeadlineYields504(t *testing.T) {
	gen := &fakeForestGen{block: make(chan struct{})} // never released
	h := newForestTestHandler(gen, 4, 30)
	h.Timeout = 20 * time.Millisecond

	w := getForest(h, "word=anger")

	if w.Code != http.StatusGatewayTimeout {
		t.Errorf("status = %d, want 504", w.Code)
	}
}
