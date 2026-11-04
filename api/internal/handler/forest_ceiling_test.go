package handler

import (
	"errors"
	"net/http"
	"testing"

	"github.com/snailuj/metaforge/internal/forest"
	"github.com/snailuj/metaforge/internal/llmlog"
)

var ceilingReached = fakeBudget{st: llmlog.BudgetStatus{CapUSD: 50, SpentUSD: 50, Exhausted: true}}

// Rule (owner, 2026-11-04): once the week's recorded spend reaches the abuse
// ceiling, nobody generates, live users included; a pooled forest is served
// instead, even for New forest.
func TestForestCeilingServesThePoolToEveryone(t *testing.T) {
	for name, hdr := range map[string]map[string]string{"live": nil, "enrichment": enrichment} {
		gen := &fakeForestGen{forest: forestWithLine("fresh")}
		h := newForestTestHandler(gen, 4, 30)
		h.Cache = &fakeForestCache{pool: []forest.Forest{forestWithLine("cached")}}
		h.Ceiling = ceilingReached

		w := getForestWith(h, "word=patience&fresh=1", hdr)
		if w.Code != http.StatusOK || w.Header().Get("X-Forest-Budget") != "ceiling" || w.Header().Get("X-Forest-Cache") != "hit" {
			t.Errorf("%s: status %d budget %q cache %q", name, w.Code, w.Header().Get("X-Forest-Budget"), w.Header().Get("X-Forest-Cache"))
		}
		if gen.called != 0 {
			t.Errorf("%s: generator called %d times past the ceiling", name, gen.called)
		}
	}
}

// Rule: past the ceiling with nothing pooled, the answer is 429 with a
// Retry-After, which the page already shows as "try again later".
func TestForestCeilingWithAnEmptyPoolAnswers429(t *testing.T) {
	gen := &fakeForestGen{}
	h := newForestTestHandler(gen, 4, 30)
	h.Ceiling = ceilingReached

	w := getForestWith(h, "word=patience", nil)
	if w.Code != http.StatusTooManyRequests || w.Header().Get("X-Forest-Budget") != "ceiling" {
		t.Fatalf("status %d budget %q", w.Code, w.Header().Get("X-Forest-Budget"))
	}
	if ra := w.Header().Get("Retry-After"); ra != "3600" {
		t.Errorf("Retry-After = %q, want 3600", ra)
	}
	if errorBody(t, w) == "" {
		t.Error("empty 429 message")
	}
	if gen.called != 0 {
		t.Errorf("generator called %d times past the ceiling", gen.called)
	}
}

// Rule: a ceiling that cannot be read counts as reached, so a ledger fault
// never leaves spend unbounded.
func TestForestCeilingUnreadableStopsGenerating(t *testing.T) {
	gen := &fakeForestGen{}
	h := newForestTestHandler(gen, 4, 30)
	h.Ceiling = fakeBudget{st: llmlog.BudgetStatus{CapUSD: 50, Exhausted: true}, err: errors.New("disk")}

	if w := getForestWith(h, "word=patience", nil); w.Code != http.StatusTooManyRequests || gen.called != 0 {
		t.Fatalf("status %d, gen called %d", w.Code, gen.called)
	}
}

func TestForestCeilingNotReachedGenerates(t *testing.T) {
	gen := &fakeForestGen{forest: forestWithLine("fresh")}
	h := newForestTestHandler(gen, 4, 30)
	h.Ceiling = fakeBudget{st: llmlog.BudgetStatus{CapUSD: 50, SpentUSD: 12, RemainingUSD: 38}}

	if w := getForestWith(h, "word=patience", nil); w.Code != http.StatusOK || gen.called != 1 {
		t.Fatalf("status %d, gen called %d", w.Code, gen.called)
	}
}

// Rule: a request the ceiling refuses costs the visitor nothing.
func TestForestCeilingRefusalSpendsNoVisitorAllowance(t *testing.T) {
	h := visitorHandler(&fakeForestGen{}, 1)
	h.Ceiling = ceilingReached
	if w := viaProxy(h, "word=anger&fresh=1", "203.0.113.7", nil); w.Code != http.StatusTooManyRequests {
		t.Fatalf("past the ceiling got %d, want 429", w.Code)
	}

	h.Ceiling = fakeBudget{st: llmlog.BudgetStatus{CapUSD: 50, SpentUSD: 12}}
	if w := viaProxy(h, "word=anger&fresh=1", "203.0.113.7", nil); w.Code != http.StatusOK {
		t.Errorf("first forest after the ceiling lifted got %d: the refusal spent the allowance", w.Code)
	}
}
