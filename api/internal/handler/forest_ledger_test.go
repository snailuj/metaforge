package handler

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/snailuj/metaforge/internal/forest"
	"github.com/snailuj/metaforge/internal/llmlog"
)

type fakeLedger struct {
	runs    []llmlog.Run
	cost    float64
	costErr error
	costFor string
}

func (l *fakeLedger) RecordRun(_ context.Context, r llmlog.Run) error {
	l.runs = append(l.runs, r)
	return nil
}

func (l *fakeLedger) RunCost(_ context.Context, id string) (float64, error) {
	l.costFor = id
	return l.cost, l.costErr
}

type fakeBudget struct {
	st  llmlog.BudgetStatus
	err error
}

func (b fakeBudget) Status(context.Context) (llmlog.BudgetStatus, error) { return b.st, b.err }

func getForestWith(h *ForestHandler, query string, hdr map[string]string) *httptest.ResponseRecorder {
	req := httptest.NewRequest("GET", "/forge/forest?"+query, nil)
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	w := httptest.NewRecorder()
	h.HandleForest(w, req)
	return w
}

// Rule: once the week's spend reaches the cap, New forest is served from
// the pool instead of generating, and says why.
func TestForestBudgetSpentServesCacheEvenWhenFresh(t *testing.T) {
	gen := &fakeForestGen{forest: forestWithLine("fresh")}
	h := newForestTestHandler(gen, 4, 30)
	h.Cache = &fakeForestCache{pool: []forest.Forest{forestWithLine("cached")}}
	h.Budget = fakeBudget{st: llmlog.BudgetStatus{CapUSD: 20, SpentUSD: 20, Exhausted: true}}

	w := getForest(h, "word=patience&fresh=1")
	if w.Code != http.StatusOK || w.Header().Get("X-Forest-Budget") != "exhausted" || w.Header().Get("X-Forest-Cache") != "hit" {
		t.Fatalf("status %d budget %q cache %q", w.Code, w.Header().Get("X-Forest-Budget"), w.Header().Get("X-Forest-Cache"))
	}
	if gen.called != 0 {
		t.Errorf("generator called %d times on a spent budget", gen.called)
	}
}

func TestForestBudgetSpentWithEmptyPoolRefuses(t *testing.T) {
	gen := &fakeForestGen{forest: forestWithLine("fresh")}
	h := newForestTestHandler(gen, 4, 30)
	h.Cache = &fakeForestCache{}
	h.Budget = fakeBudget{st: llmlog.BudgetStatus{CapUSD: 20, SpentUSD: 21, Exhausted: true}}

	w := getForest(h, "word=patience")
	if w.Code != http.StatusServiceUnavailable || !strings.Contains(errorBody(t, w), "budget") || w.Header().Get("X-Forest-Budget") != "exhausted" {
		t.Fatalf("status %d body %s", w.Code, w.Body.String())
	}
	if gen.called != 0 {
		t.Errorf("generator called on a spent budget")
	}
}

func TestForestBudgetUnreadableRefusesGeneration(t *testing.T) {
	gen := &fakeForestGen{forest: forestWithLine("fresh")}
	h := newForestTestHandler(gen, 4, 30)
	h.Budget = fakeBudget{st: llmlog.BudgetStatus{CapUSD: 20, Exhausted: true}, err: errors.New("disk")}

	if w := getForest(h, "word=patience"); w.Code != http.StatusServiceUnavailable || gen.called != 0 {
		t.Fatalf("status %d, gen called %d", w.Code, gen.called)
	}
}

func TestForestBudgetLeftGenerates(t *testing.T) {
	gen := &fakeForestGen{forest: forestWithLine("fresh")}
	h := newForestTestHandler(gen, 4, 30)
	h.Budget = fakeBudget{st: llmlog.BudgetStatus{CapUSD: 20, SpentUSD: 3, RemainingUSD: 17}}

	if w := getForest(h, "word=patience"); w.Code != http.StatusOK || gen.called != 1 {
		t.Fatalf("status %d, gen called %d", w.Code, gen.called)
	}
}

// Rule: every generated forest is kept in the ledger with the run id its
// model calls carry, and the response reports what it cost.
func TestForestRunRecordedWithCostAndOrigin(t *testing.T) {
	gen := &fakeForestGen{forest: forestWithLine("fresh")}
	h := newForestTestHandler(gen, 4, 30)
	led := &fakeLedger{cost: 0.0042}
	h.Ledger, h.Fingerprint = led, "fp1"
	w := getForestWith(h, "word=patience&max_hops=2&fresh=1", map[string]string{"X-Metaforge-Origin": "enrichment"})
	if w.Code != http.StatusOK {
		t.Fatalf("status %d", w.Code)
	}
	if gen.run.ID == "" || gen.run.Origin != "enrichment" || gen.run.Word != "patience" || gen.run.MaxHops != 2 {
		t.Fatalf("generator context run %+v", gen.run)
	}
	if len(led.runs) != 1 {
		t.Fatalf("runs recorded = %d", len(led.runs))
	}
	r := led.runs[0]
	if led.costFor != gen.run.ID {
		t.Errorf("priced run %q, generator ran %q", led.costFor, gen.run.ID)
	}
	if r.ID != gen.run.ID || r.Outcome != "ok" || r.Origin != "enrichment" || r.Fingerprint != "fp1" || r.CostUSD != 0.0042 {
		t.Errorf("run %+v", r)
	}
	var f forest.Forest
	if err := json.Unmarshal(r.Forest, &f); err != nil || f.Endpoints[0].Line != "fresh" {
		t.Errorf("run forest %s (%v)", r.Forest, err)
	}
	if got := w.Header().Get("X-Forest-Cost-USD"); got != "0.004200" {
		t.Errorf("cost header %q", got)
	}
}

func TestForestFailedRunRecorded(t *testing.T) {
	gen := &fakeForestGen{err: errors.New("judge: bad json")}
	h := newForestTestHandler(gen, 4, 30)
	led := &fakeLedger{}
	h.Ledger = led

	getForest(h, "word=patience")
	if len(led.runs) != 1 || led.runs[0].Outcome != "error" || led.runs[0].Origin != "web" || !strings.Contains(led.runs[0].Error, "bad json") {
		t.Fatalf("runs %+v", led.runs)
	}
}

func TestForestOriginIsSanitised(t *testing.T) {
	for in, want := range map[string]string{"": "web", "Enrichment": "enrichment", "<script>": "web", strings.Repeat("a", 40): "web"} {
		gen := &fakeForestGen{forest: forestWithLine("x")}
		h := newForestTestHandler(gen, 4, 30)
		getForestWith(h, "word=patience", map[string]string{"X-Metaforge-Origin": in})
		if gen.run.Origin != want {
			t.Errorf("origin %q became %q, want %q", in, gen.run.Origin, want)
		}
	}
}

func TestBudgetEndpoint(t *testing.T) {
	h := &BudgetHandler{Budget: fakeBudget{st: llmlog.BudgetStatus{CapUSD: 20, SpentUSD: 5, RemainingUSD: 15}}}
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest("GET", "/forge/budget", nil))
	var st llmlog.BudgetStatus
	if w.Code != http.StatusOK || json.Unmarshal(w.Body.Bytes(), &st) != nil || st.RemainingUSD != 15 {
		t.Fatalf("status %d body %s", w.Code, w.Body.String())
	}
}

func TestBudgetEndpointUnconfigured(t *testing.T) {
	w := httptest.NewRecorder()
	(&BudgetHandler{}).ServeHTTP(w, httptest.NewRequest("GET", "/forge/budget", nil))
	if w.Code != http.StatusServiceUnavailable {
		t.Fatalf("status %d", w.Code)
	}
}

// Rule: a cost that could not be read is left out, never reported as zero.
func TestForestCostHeaderOmittedWhenUnknown(t *testing.T) {
	gen := &fakeForestGen{forest: forestWithLine("fresh")}
	h := newForestTestHandler(gen, 4, 30)
	h.Ledger = &fakeLedger{costErr: errors.New("disk")}
	w := getForest(h, "word=patience")
	if w.Code != http.StatusOK || w.Header().Get("X-Forest-Cost-USD") != "" {
		t.Fatalf("status %d cost header %q", w.Code, w.Header().Get("X-Forest-Cost-USD"))
	}
}
