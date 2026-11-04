package enrich

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestClientForestAsksForAFreshEnrichmentForest(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		if r.URL.Path != "/forge/forest" || q.Get("word") != "dread" || q.Get("max_hops") != "3" || q.Get("fresh") != "1" ||
			r.Header.Get("X-Metaforge-Origin") != "enrichment" {
			t.Errorf("unexpected request %s %v", r.URL, r.Header)
		}
		w.Header().Set("X-Forest-Cost-USD", "0.001234")
		fmt.Fprint(w, `{"source":"dread","endpoints":[{"id":"a"},{"id":"b"}]}`)
	}))
	defer srv.Close()

	res, err := NewClient(srv.URL, time.Second).Forest(context.Background(), "dread", 3)
	if err != nil {
		t.Fatal(err)
	}
	if res.Status != 200 || res.CostUSD != 0.001234 || !res.CostKnown || res.Endpoints != 2 || res.BudgetExhausted {
		t.Fatalf("result %+v", res)
	}
}

func TestClientForestReadsRefusals(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Query().Get("word") {
		case "busy":
			w.Header().Set("Retry-After", "9")
			w.WriteHeader(429)
		case "spent":
			w.Header().Set("X-Forest-Budget", "exhausted")
			w.WriteHeader(503)
		case "full":
			w.Header().Set("X-Forest-Pool", "full")
		}
		fmt.Fprint(w, `{"error":"x"}`)
	}))
	defer srv.Close()
	c := NewClient(srv.URL, time.Second)

	busy, err := c.Forest(context.Background(), "busy", 3)
	if err != nil || busy.Status != 429 || busy.RetryAfter != 9*time.Second || busy.CostKnown {
		t.Errorf("busy %+v %v", busy, err)
	}
	spent, err := c.Forest(context.Background(), "spent", 3)
	if err != nil || spent.Status != 503 || !spent.BudgetExhausted {
		t.Errorf("spent %+v %v", spent, err)
	}
	full, err := c.Forest(context.Background(), "full", 3)
	if err != nil || full.Status != 200 || !full.PoolFull {
		t.Errorf("full %+v %v", full, err)
	}
}

func TestClientBudget(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/forge/budget" {
			w.WriteHeader(404)
			return
		}
		fmt.Fprint(w, `{"cap_usd":20,"spent_usd":3.5,"remaining_usd":16.5,"window_start":"2026-10-28T00:00:00Z","exhausted":false}`)
	}))
	defer srv.Close()

	st, err := NewClient(srv.URL, time.Second).Budget(context.Background())
	if err != nil || st.CapUSD != 20 || st.SpentUSD != 3.5 {
		t.Fatalf("budget %+v %v", st, err)
	}
}

func TestClientBudgetErrorsOnNon200(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(503) }))
	defer srv.Close()
	if _, err := NewClient(srv.URL, time.Second).Budget(context.Background()); err == nil {
		t.Fatal("want an error")
	}
}
