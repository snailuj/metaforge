package enrich

import (
	"context"
	"errors"
	"path/filepath"
	"testing"
	"time"

	"github.com/snailuj/metaforge/internal/llmlog"
)

type fakeAPI struct {
	budget    llmlog.BudgetStatus
	budgetErr error
	results   []ForestResult
	forestErr error
	asked     []string
}

func (f *fakeAPI) Budget(context.Context) (llmlog.BudgetStatus, error) { return f.budget, f.budgetErr }

func (f *fakeAPI) Forest(_ context.Context, word string, _ int) (ForestResult, error) {
	f.asked = append(f.asked, word)
	if f.forestErr != nil {
		return ForestResult{}, f.forestErr
	}
	r := f.results[0]
	if len(f.results) > 1 {
		f.results = f.results[1:]
	}
	return r, nil
}

type clock struct{ t time.Time }

func (c *clock) now() time.Time { return c.t }

func newTest(t *testing.T, api *fakeAPI, words ...string) (*Enricher, *clock) {
	t.Helper()
	c := &clock{t: time.Date(2026, 11, 4, 0, 0, 0, 0, time.UTC)}
	e, err := New(api, Config{
		Words: words, MaxHops: 3, ReserveUSD: 5, InitialCostUSD: 0.01,
		MinInterval: time.Second, IdleWait: 15 * time.Minute, ErrorWait: time.Minute,
		StatePath: filepath.Join(t.TempDir(), "state.json"),
	}, c.now)
	if err != nil {
		t.Fatal(err)
	}
	return e, c
}

func capped(spent float64) llmlog.BudgetStatus {
	return llmlog.BudgetStatus{CapUSD: 20, SpentUSD: spent, RemainingUSD: 20 - spent}
}

var okForest = ForestResult{Status: 200, CostUSD: 0.002, CostKnown: true, Endpoints: 5}

func TestStepGeneratesAndAdvances(t *testing.T) {
	api := &fakeAPI{budget: capped(1), results: []ForestResult{okForest}}
	e, _ := newTest(t, api, "longing", "dread")
	if _, err := e.Step(context.Background()); err != nil {
		t.Fatal(err)
	}
	if len(api.asked) != 1 || api.asked[0] != "longing" {
		t.Fatalf("asked %v", api.asked)
	}
	st := e.State()
	if st.Index != 1 || st.Forests != 1 || st.SpentUSD != 0.002 {
		t.Errorf("state %+v", st)
	}
	// The estimate moves towards what forests really cost.
	if st.CostEstimateUSD >= 0.01 || st.CostEstimateUSD <= 0.002 {
		t.Errorf("estimate %v did not move towards 0.002", st.CostEstimateUSD)
	}
}

// Rule: forests are paced so the enricher alone spends at most
// (cap - reserve) per week: one forest per cost / weekly allowance.
func TestStepPacesToTheWeeklyAllowance(t *testing.T) {
	api := &fakeAPI{budget: capped(1), results: []ForestResult{okForest}}
	e, c := newTest(t, api, "longing", "dread")
	if _, err := e.Step(context.Background()); err != nil {
		t.Fatal(err)
	}
	wait, err := e.Step(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	est := e.State().CostEstimateUSD
	want := time.Duration(est / 15 * float64(7*24*time.Hour))
	if len(api.asked) != 1 || absDur(wait-want) > time.Millisecond {
		t.Fatalf("asked %v, wait %v, want %v", api.asked, wait, want)
	}
	c.t = c.t.Add(want)
	if _, err := e.Step(context.Background()); err != nil {
		t.Fatal(err)
	}
	if len(api.asked) != 2 || api.asked[1] != "dread" {
		t.Fatalf("after the wait asked %v", api.asked)
	}
}

func absDur(d time.Duration) time.Duration {
	if d < 0 {
		return -d
	}
	return d
}

// Rule: the reserve is left for live users; enrichment stops short of it.
func TestStepWaitsWhenOnlyTheReserveIsLeft(t *testing.T) {
	api := &fakeAPI{budget: capped(15)}
	e, _ := newTest(t, api, "longing")
	wait, err := e.Step(context.Background())
	if err != nil || wait != 15*time.Minute || len(api.asked) != 0 {
		t.Fatalf("wait %v err %v asked %v", wait, err, api.asked)
	}
}

func TestStepRefusesAnUncappedServer(t *testing.T) {
	api := &fakeAPI{budget: llmlog.BudgetStatus{CapUSD: 0}}
	e, _ := newTest(t, api, "longing")
	if _, err := e.Step(context.Background()); !errors.Is(err, ErrUncapped) {
		t.Fatalf("err %v, want ErrUncapped", err)
	}
}

func TestStepRefusesAReserveAtOrOverTheCap(t *testing.T) {
	api := &fakeAPI{budget: llmlog.BudgetStatus{CapUSD: 4}}
	e, _ := newTest(t, api, "longing")
	if _, err := e.Step(context.Background()); !errors.Is(err, ErrNoAllowance) {
		t.Fatalf("err %v, want ErrNoAllowance", err)
	}
}

func TestStepBacksOffWhenBudgetUnreadable(t *testing.T) {
	api := &fakeAPI{budgetErr: errors.New("connection refused")}
	e, _ := newTest(t, api, "longing")
	wait, err := e.Step(context.Background())
	if err != nil || wait != time.Minute || len(api.asked) != 0 {
		t.Fatalf("wait %v err %v", wait, err)
	}
}

func TestStepKeepsTheWordOnTransientFailures(t *testing.T) {
	for name, tc := range map[string]struct {
		res  ForestResult
		err  error
		wait time.Duration
	}{
		"network":      {err: errors.New("reset"), wait: time.Minute},
		"rate limited": {res: ForestResult{Status: 429, RetryAfter: 7 * time.Second}, wait: 7 * time.Second},
		"budget spent": {res: ForestResult{Status: 200, BudgetExhausted: true}, wait: 15 * time.Minute},
		"refused 503":  {res: ForestResult{Status: 503, BudgetExhausted: true}, wait: 15 * time.Minute},
	} {
		t.Run(name, func(t *testing.T) {
			api := &fakeAPI{budget: capped(1), results: []ForestResult{tc.res}, forestErr: tc.err}
			e, _ := newTest(t, api, "longing", "dread")
			wait, err := e.Step(context.Background())
			if err != nil || wait != tc.wait || e.State().Index != 0 || e.State().Forests != 0 {
				t.Fatalf("wait %v err %v state %+v", wait, err, e.State())
			}
		})
	}
}

func TestStepMovesOnFromABadWordOrFailedForest(t *testing.T) {
	for _, status := range []int{400, 502, 504} {
		api := &fakeAPI{budget: capped(1), results: []ForestResult{{Status: status}}}
		e, _ := newTest(t, api, "longing", "dread")
		if _, err := e.Step(context.Background()); err != nil {
			t.Fatal(err)
		}
		if st := e.State(); st.Index != 1 || st.Forests != 0 || st.Failed != 1 {
			t.Errorf("status %d: state %+v", status, st)
		}
	}
}

func TestPassesWrapAndFinish(t *testing.T) {
	api := &fakeAPI{budget: capped(1), results: []ForestResult{okForest}}
	e, c := newTest(t, api, "a", "b")
	e.cfg.Passes = 2
	var err error
	for i := 0; i < 10 && !errors.Is(err, ErrDone); i++ {
		var wait time.Duration
		wait, err = e.Step(context.Background())
		c.t = c.t.Add(wait)
	}
	if !errors.Is(err, ErrDone) || len(api.asked) != 4 || e.State().Pass != 2 {
		t.Fatalf("err %v asked %v state %+v", err, api.asked, e.State())
	}
}

// Rule: progress survives a restart, so no forest is bought twice.
func TestStateResumesAfterRestart(t *testing.T) {
	api := &fakeAPI{budget: capped(1), results: []ForestResult{okForest}}
	e, _ := newTest(t, api, "longing", "dread")
	if _, err := e.Step(context.Background()); err != nil {
		t.Fatal(err)
	}
	again, err := New(api, e.cfg, e.now)
	if err != nil {
		t.Fatal(err)
	}
	if again.State().Index != 1 || again.State().Forests != 1 {
		t.Fatalf("resumed state %+v", again.State())
	}
}

func TestChangedWordListRestartsThePass(t *testing.T) {
	api := &fakeAPI{budget: capped(1), results: []ForestResult{okForest}}
	e, _ := newTest(t, api, "longing", "dread")
	if _, err := e.Step(context.Background()); err != nil {
		t.Fatal(err)
	}
	cfg := e.cfg
	cfg.Words = []string{"hope", "fear", "joy"}
	again, err := New(api, cfg, e.now)
	if err != nil {
		t.Fatal(err)
	}
	if again.State().Index != 0 || again.State().Forests != 1 {
		t.Fatalf("state %+v", again.State())
	}
}

// Rule: a forest whose cost the server could not report leaves the pacing
// estimate where it was.
func TestStepIgnoresAnUnknownCost(t *testing.T) {
	api := &fakeAPI{budget: capped(1), results: []ForestResult{{Status: 200, Endpoints: 3}}}
	e, _ := newTest(t, api, "longing")
	if _, err := e.Step(context.Background()); err != nil {
		t.Fatal(err)
	}
	if st := e.State(); st.CostEstimateUSD != 0.01 || st.Forests != 1 {
		t.Fatalf("state %+v", st)
	}
}
