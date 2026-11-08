package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"

	"github.com/snailuj/metaforge/internal/enrich"
	"github.com/snailuj/metaforge/internal/handler"
	"github.com/snailuj/metaforge/internal/llmlog"
)

const e2eGenerated = `{"facets":[{"word":"Dormant Seed","ground":"waits","line":"","branches":[
 {"hops":[{"word":"seed vault","ground":"stays viable"}],"line":"Patience is a seed vault."},
 {"hops":[{"word":"orrery","ground":"turns slowly"}],"line":"Patience is an orrery."}]}]}`

const e2eJudged = `{"verdicts":[
 {"index":1,"reason":"ok","broken_hop":false,"drift":false,"literal":false,"cliche":false,"score":8},
 {"index":2,"reason":"ok","broken_hop":false,"drift":false,"literal":false,"cliche":false,"score":7}]}`

// fakeAnthropic answers generator then judge, alternately, with fixed usage.
func fakeAnthropic(t *testing.T) *httptest.Server {
	return httptest.NewServer(fakeAnthropicHandler())
}

func fakeAnthropicHandler() http.Handler {
	var n atomic.Int32
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		text := e2eGenerated
		if n.Add(1)%2 == 0 {
			text = e2eJudged
		}
		b, _ := json.Marshal(text)
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("request-id", fmt.Sprintf("req_%d", n.Load()))
		fmt.Fprintf(w, `{"id":"msg_%d","type":"message","role":"assistant","model":"claude-haiku-5-5",
			"content":[{"type":"text","text":%s}],"stop_reason":"end_turn",
			"usage":{"input_tokens":2000,"output_tokens":3000,"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}`, n.Load(), b)
	})
}

// The whole chain: the enricher asks the API, the API calls the model, every
// call lands in the ledger with its run, the response carries the cost, and
// the weekly cap stops further generation.
func TestEnrichmentThroughTheAPIIsRecordedAndCapped(t *testing.T) {
	model := fakeAnthropic(t)
	defer model.Close()

	clearForestEnv(t)
	dir := t.TempDir()
	ledgerPath := filepath.Join(dir, "llm_calls.db")
	t.Setenv("ANTHROPIC_API_KEY", "sk-test")
	t.Setenv("METAFORGE_FOREST_MIN_PATHS", "0")
	t.Setenv("METAFORGE_FOREST_CACHE", filepath.Join(dir, "forest_cache.db"))
	t.Setenv("METAFORGE_LLM_LOG", ledgerPath)
	// One forest costs 2 * (2000*0.10 + 3000*0.50)/1e6 = $0.0034; a cap of
	// $0.003 lets one forest start (spend is checked before, not during, a
	// forest) and is then spent.
	t.Setenv("METAFORGE_WEEKLY_BUDGET_USD", "0.003")

	settings := loadForestSettings()
	settings.AnthropicBaseURL = model.URL
	fh := newForestHandler(settings, anyWord)
	r := chi.NewRouter()
	r.Get("/forge/forest", fh.HandleForest)
	r.Method("GET", "/forge/budget", &handler.BudgetHandler{Budget: fh.Budget})
	api := httptest.NewServer(r)
	defer api.Close()

	client := enrich.NewClient(api.URL, 10*time.Second)
	res, err := client.Forest(context.Background(), "patience", 3)
	if err != nil {
		t.Fatal(err)
	}
	if res.Status != 200 || res.Endpoints == 0 || res.CostUSD < 0.0033 || res.CostUSD > 0.0035 {
		t.Fatalf("first forest %+v", res)
	}

	ledger, err := llmlog.Open(ledgerPath)
	if err != nil {
		t.Fatal(err)
	}
	defer ledger.Close()
	spent, err := ledger.SpentSince(context.Background(), time.Now().Add(-time.Hour))
	if err != nil || spent < 0.0033 {
		t.Fatalf("ledger spent %v, %v", spent, err)
	}
	for _, id := range []int64{1, 2} {
		c, err := ledger.GetCall(context.Background(), id)
		if err != nil {
			t.Fatal(err)
		}
		if c.Origin != "enrichment" || c.Word != "patience" || c.RunID == "" || !strings.Contains(string(c.ResponseBody), "msg_") {
			t.Errorf("call %d: %+v", id, c)
		}
	}

	// The cap is now spent: the second fresh request is served from the
	// pool, and the enricher waits instead of asking again.
	again, err := client.Forest(context.Background(), "patience", 3)
	if err != nil || !again.BudgetExhausted {
		t.Fatalf("second forest %+v %v", again, err)
	}
	e, err := enrich.New(client, enrich.Config{Words: []string{"hope"}, MaxHops: 3, ReserveUSD: 0, InitialCostUSD: 0.001,
		MinInterval: time.Millisecond, IdleWait: time.Hour, ErrorWait: time.Minute, StatePath: filepath.Join(dir, "state.json")}, time.Now)
	if err != nil {
		t.Fatal(err)
	}
	wait, err := e.Step(context.Background())
	if err != nil || wait != time.Hour || e.State().Forests != 0 {
		t.Fatalf("enricher on a spent budget: wait %v err %v state %+v", wait, err, e.State())
	}
}
