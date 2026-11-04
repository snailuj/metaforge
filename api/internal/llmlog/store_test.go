package llmlog

import (
	"context"
	"path/filepath"
	"testing"
	"time"
)

func openTemp(t *testing.T) *Store {
	t.Helper()
	s, err := Open(filepath.Join(t.TempDir(), "calls.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { s.Close() })
	return s
}

func TestStoreKeepsWholeCallAndReadsItBack(t *testing.T) {
	s := openTemp(t)
	ctx := context.Background()
	start := time.Date(2026, 11, 4, 2, 0, 0, 0, time.UTC)
	c := Call{
		Started: start, HeadersAfter: 300 * time.Millisecond, FirstByteAfter: 310 * time.Millisecond, Total: 2 * time.Second,
		RunID: "run1", Origin: "web", Label: "forest_generate", Word: "longing", MaxHops: 3,
		Method: "POST", URL: "https://api.anthropic.com/v1/messages", Model: "claude-haiku-5-5",
		HTTPStatus: 200, RequestID: "req_1", StopReason: "end_turn", MessageID: "msg_1",
		Usage:          Usage{InputTokens: 10, OutputTokens: 20},
		CostUSD:        0.5, PriceKnown: true,
		RequestHeaders: map[string][]string{"Content-Type": {"application/json"}},
		RequestBody:    []byte(`{"model":"claude-haiku-5-5"}`),
		ResponseBody:   []byte(`{"id":"msg_1"}`),
	}
	id, err := s.InsertCall(ctx, c)
	if err != nil {
		t.Fatal(err)
	}
	got, err := s.GetCall(ctx, id)
	if err != nil {
		t.Fatal(err)
	}
	if string(got.RequestBody) != string(c.RequestBody) || string(got.ResponseBody) != string(c.ResponseBody) {
		t.Fatalf("bodies did not round-trip: %q %q", got.RequestBody, got.ResponseBody)
	}
	if got.Word != "longing" || got.Usage != c.Usage || got.Total != c.Total || !got.Started.Equal(start) || got.RequestHeaders["Content-Type"][0] != "application/json" {
		t.Fatalf("columns did not round-trip: %+v", got)
	}
}

func TestSpentSinceCountsOnlyTheWindow(t *testing.T) {
	s := openTemp(t)
	ctx := context.Background()
	now := time.Date(2026, 11, 4, 0, 0, 0, 0, time.UTC)
	for _, c := range []Call{
		{Started: now.Add(-8 * 24 * time.Hour), CostUSD: 100},
		{Started: now.Add(-6 * 24 * time.Hour), CostUSD: 1.25},
		{Started: now.Add(-time.Minute), CostUSD: 0.75},
	} {
		if _, err := s.InsertCall(ctx, c); err != nil {
			t.Fatal(err)
		}
	}
	got, err := s.SpentSince(ctx, now.Add(-7*24*time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	if !near(got, 2.0) {
		t.Fatalf("spent = %v, want 2", got)
	}
}

func TestRunCostSumsRetriesAndJudge(t *testing.T) {
	s := openTemp(t)
	ctx := context.Background()
	for _, c := range []Call{
		{Started: time.Now(), RunID: "a", CostUSD: 0.001},
		{Started: time.Now(), RunID: "a", CostUSD: 0.002},
		{Started: time.Now(), RunID: "b", CostUSD: 9},
	} {
		if _, err := s.InsertCall(ctx, c); err != nil {
			t.Fatal(err)
		}
	}
	got, err := s.RunCost(ctx, "a")
	if err != nil || !near(got, 0.003) {
		t.Fatalf("run cost = %v, %v; want 0.003", got, err)
	}
}

func TestRecordRunKeepsEveryForest(t *testing.T) {
	s := openTemp(t)
	ctx := context.Background()
	for range 3 {
		if err := s.RecordRun(ctx, Run{ID: "r", Started: time.Now(), Word: "dread", MaxHops: 3, Origin: "enrichment", Outcome: "ok", Forest: []byte(`{"endpoints":[]}`)}); err != nil {
			t.Fatal(err)
		}
	}
	var n int
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM forest_runs WHERE word = 'dread'`).Scan(&n); err != nil || n != 3 {
		t.Fatalf("runs = %d, %v; want 3", n, err)
	}
}

func TestOpenTwiceSharesTheFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "calls.db")
	a, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer a.Close()
	b, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer b.Close()
	if _, err := a.InsertCall(context.Background(), Call{Started: time.Now(), CostUSD: 1}); err != nil {
		t.Fatal(err)
	}
	got, err := b.SpentSince(context.Background(), time.Now().Add(-time.Hour))
	if err != nil || !near(got, 1) {
		t.Fatalf("second handle saw %v, %v", got, err)
	}
}
