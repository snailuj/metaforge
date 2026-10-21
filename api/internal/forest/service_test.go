package forest

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"reflect"
	"strings"
	"testing"

	"log/slog"

	"github.com/snailuj/metaforge/internal/llm"
	"github.com/snailuj/metaforge/internal/observe"
)

type fakeResult struct {
	resp llm.Response
	err  error
}

// fakeLLM answers calls in order and records every request.
type fakeLLM struct {
	results []fakeResult
	calls   []llm.Request
	panicOn string // when set, Complete panics with this value
}

func (f *fakeLLM) Complete(_ context.Context, req llm.Request) (llm.Response, error) {
	f.calls = append(f.calls, req)
	if f.panicOn != "" {
		panic(f.panicOn)
	}
	if len(f.calls) > len(f.results) {
		return llm.Response{}, errors.New("unexpected extra call")
	}
	r := f.results[len(f.calls)-1]
	return r.resp, r.err
}

func ok(text string, in, out, cache int64) fakeResult {
	return fakeResult{resp: llm.Response{Text: text, StopReason: "end_turn",
		Usage: llm.Usage{InputTokens: in, OutputTokens: out, CacheReadTokens: cache}}}
}

const generatedJSON = `{"facets":[
 {"word":"Dormant Seed","ground":"waits","line":"","branches":[
   {"hops":[{"word":"seed vault","ground":"stays viable"}],"line":"Patience is a seed vault."},
   {"hops":[{"word":"gene bank","ground":""}],"line":"Patience is a gene bank."},
   {"hops":[{"word":"orrery","ground":"turns slowly"}],"line":"Patience is an orrery."}]}]}`

func testService(f *fakeLLM) (*Service, *bytes.Buffer) {
	var logs bytes.Buffer
	s := NewService(f, Config{Model: "gen-model", JudgeModel: "judge-model", Effort: "medium", MinScore: 6})
	s.Logger = slog.New(slog.NewJSONHandler(&logs, &slog.HandlerOptions{Level: slog.LevelDebug}))
	return s, &logs
}

func logRecords(t *testing.T, buf *bytes.Buffer) []map[string]any {
	t.Helper()
	var out []map[string]any
	for _, line := range strings.Split(strings.TrimSpace(buf.String()), "\n") {
		if line == "" {
			continue
		}
		var rec map[string]any
		if err := json.Unmarshal([]byte(line), &rec); err != nil {
			t.Fatalf("log line is not JSON: %q", line)
		}
		out = append(out, rec)
	}
	return out
}

func TestServiceGenerateHappyPath(t *testing.T) {
	judged := `{"verdicts":[
	  {"index":1,"score":8,"broken_hop":false,"drift":false,"literal":false,"cliche":false,"reason":"cold"},
	  {"index":2,"score":3,"broken_hop":false,"drift":false,"literal":false,"cliche":false,"reason":"flat"},
	  {"index":9,"score":9,"broken_hop":false,"drift":false,"literal":false,"cliche":false,"reason":"phantom"}]}`
	f := &fakeLLM{results: []fakeResult{ok(generatedJSON, 100, 200, 10), ok(judged, 50, 60, 5)}}
	s, logs := testService(f)

	forest, err := s.Generate(context.Background(), "patience", 3)
	if err != nil {
		t.Fatalf("Generate: %v", err)
	}

	// Requests.
	if len(f.calls) != 2 {
		t.Fatalf("%d LLM calls, want 2", len(f.calls))
	}
	gen, judge := f.calls[0], f.calls[1]
	if gen.Model != "gen-model" || gen.System != GeneratorSystemPrompt || gen.Effort != "medium" ||
		gen.User != "SOURCE: patience\nMAX_HOPS: 3" || gen.MaxTokens != 16000 ||
		!reflect.DeepEqual(gen.Schema, GeneratorSchema()) {
		t.Errorf("generator request = %+v", gen)
	}
	// Path 2 (gene bank) has an empty ground, so only 2 paths reach the
	// judge, and verdict 2 refers to the orrery.
	wantUser := "SOURCE: patience\n\n" +
		"1. patience -[waits]-> dormant seed -[stays viable]-> seed vault | Patience is a seed vault.\n" +
		"2. patience -[waits]-> dormant seed -[turns slowly]-> orrery | Patience is an orrery."
	if judge.Model != "judge-model" || judge.System != JudgeSystemPrompt || judge.User != wantUser ||
		judge.Effort != "medium" || judge.MaxTokens != 16000 || !reflect.DeepEqual(judge.Schema, JudgeSchema()) {
		t.Errorf("judge request = %+v", judge)
	}

	// Result.
	if forest.Model != "gen-model" || forest.MaxHops != 3 || forest.Source != "patience" {
		t.Errorf("forest header = %+v", forest)
	}
	if len(forest.Endpoints) != 1 || forest.Endpoints[0].ID != "seed vault" || forest.Endpoints[0].Score != 8 {
		t.Errorf("endpoints = %+v", forest.Endpoints)
	}
	wantStats := Stats{Generated: 3, Kept: 1, Rejected: Rejected{Invalid: 1, LowScore: 1}}
	if forest.Stats != wantStats {
		t.Errorf("stats = %+v, want %+v", forest.Stats, wantStats)
	}

	// One summary line, plus a warning for the phantom verdict index.
	var summary map[string]any
	var warned bool
	for _, rec := range logRecords(t, logs) {
		switch rec["msg"] {
		case "forest request":
			summary = rec
		case "forest: judge verdict ignored":
			warned = rec["level"] == "WARN" && rec["index"] == float64(9)
		}
	}
	if !warned {
		t.Error("unknown verdict index was not logged as a warning")
	}
	want := map[string]any{
		"word": "patience", "max_hops": 3.0, "model": "gen-model", "judge_model": "judge-model",
		"gen_input_tokens": 100.0, "gen_output_tokens": 200.0, "gen_cache_read_tokens": 10.0,
		"judge_input_tokens": 50.0, "judge_output_tokens": 60.0, "judge_cache_read_tokens": 5.0,
		"generated": 3.0, "kept": 1.0, "rejected_invalid": 1.0, "rejected_low_score": 1.0,
		"rejected_broken_hop": 0.0, "rejected_drift": 0.0, "rejected_cliche": 0.0, "rejected_literal": 0.0,
		"outcome": "ok",
	}
	if summary == nil {
		t.Fatal("no summary log line")
	}
	for k, v := range want {
		if summary[k] != v {
			t.Errorf("log %s = %v, want %v", k, summary[k], v)
		}
	}
	for _, k := range []string{"gen_latency_ms", "judge_latency_ms"} {
		if _, present := summary[k]; !present {
			t.Errorf("log lacks %s", k)
		}
	}
}

// Rule: with nothing valid to judge the service spends no judge call and
// still returns the (empty) forest.
func TestServiceSkipsJudgeWhenNothingIsValid(t *testing.T) {
	empty := `{"facets":[]}`
	f := &fakeLLM{results: []fakeResult{ok(empty, 1, 1, 0)}}
	s, _ := testService(f)

	forest, err := s.Generate(context.Background(), "patience", 3)
	if err != nil {
		t.Fatalf("Generate: %v", err)
	}
	if len(f.calls) != 1 {
		t.Errorf("%d calls, want 1", len(f.calls))
	}
	if len(forest.Nodes) != 1 || len(forest.Endpoints) != 0 || forest.Stats.Generated != 0 {
		t.Errorf("forest = %+v", forest)
	}
}

// Rule: every failure is returned to the caller and logged, and a failed
// generator call never reaches the judge.
func TestServiceErrorsAreReturnedAndLogged(t *testing.T) {
	boom := errors.New("boom")
	cases := []struct {
		name      string
		results   []fakeResult
		wantCalls int
		wantIs    error
		wantText  string
	}{
		{"generator call fails", []fakeResult{{err: boom}}, 1, boom, "generate"},
		{"generator output is not JSON", []fakeResult{ok("nope", 1, 1, 0)}, 1, nil, "generate"},
		{"judge call fails", []fakeResult{ok(generatedJSON, 1, 1, 0), {err: boom}}, 2, boom, "judge"},
		{"judge output is not JSON", []fakeResult{ok(generatedJSON, 1, 1, 0), ok("nope", 1, 1, 0)}, 2, nil, "judge"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			f := &fakeLLM{results: tc.results}
			s, logs := testService(f)

			_, err := s.Generate(context.Background(), "patience", 3)

			if err == nil || !strings.Contains(err.Error(), tc.wantText) {
				t.Fatalf("error = %v, want mention of %q", err, tc.wantText)
			}
			if tc.wantIs != nil && !errors.Is(err, tc.wantIs) {
				t.Errorf("error %v does not wrap %v", err, tc.wantIs)
			}
			if len(f.calls) != tc.wantCalls {
				t.Errorf("%d calls, want %d", len(f.calls), tc.wantCalls)
			}
			var logged bool
			for _, rec := range logRecords(t, logs) {
				if rec["msg"] == "forest request" && rec["level"] == "ERROR" && rec["outcome"] == "error" && rec["error"] != nil {
					logged = true
				}
			}
			if !logged {
				t.Errorf("failure was not logged:\n%s", logs)
			}
		})
	}
}

func TestServiceKeepsContextErrorsMatchable(t *testing.T) {
	f := &fakeLLM{results: []fakeResult{{err: context.DeadlineExceeded}}}
	s, _ := testService(f)

	_, err := s.Generate(context.Background(), "patience", 3)
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Errorf("error %v does not wrap DeadlineExceeded", err)
	}
}

// Rule: both LLM calls are timed through observe when timing is on.
func TestServiceTimesBothCallsThroughObserve(t *testing.T) {
	var buf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&buf, nil)))
	observe.Init(true)
	t.Cleanup(func() { observe.Init(false); slog.SetDefault(prev) })

	judged := `{"verdicts":[]}`
	f := &fakeLLM{results: []fakeResult{ok(generatedJSON, 1, 1, 0), ok(judged, 1, 1, 0)}}
	s, _ := testService(f)
	if _, err := s.Generate(context.Background(), "patience", 3); err != nil {
		t.Fatal(err)
	}

	var labels []any
	for _, rec := range logRecords(t, &buf) {
		if rec["msg"] == "timing" {
			labels = append(labels, rec["label"])
		}
	}
	if !reflect.DeepEqual(labels, []any{"forest_generate", "forest_judge"}) {
		t.Errorf("timing labels = %v", labels)
	}
}

// Rule: a client disconnect is not a failure: it logs at Info with
// outcome=canceled and the error is still returned to the caller.
func TestServiceLogsCancellationAtInfo(t *testing.T) {
	f := &fakeLLM{results: []fakeResult{{err: fmt.Errorf("anthropic messages: %w", context.Canceled)}}}
	s, logs := testService(f)

	_, err := s.Generate(context.Background(), "patience", 3)
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("error = %v, want context.Canceled", err)
	}
	for _, rec := range logRecords(t, logs) {
		if rec["level"] == "ERROR" {
			t.Errorf("cancellation logged at Error: %v", rec)
		}
		if rec["msg"] == "forest request" && (rec["level"] != "INFO" || rec["outcome"] != "canceled") {
			t.Errorf("summary = %v, want INFO outcome=canceled", rec)
		}
	}
}

// Rule: a panic is never logged as success; it is logged with
// outcome=panic and then continues to unwind.
func TestServiceLogsPanicAndRepanics(t *testing.T) {
	f := &fakeLLM{panicOn: "kaboom"}
	s, logs := testService(f)

	var recovered any
	func() {
		defer func() { recovered = recover() }()
		_, _ = s.Generate(context.Background(), "patience", 3)
	}()

	if recovered != "kaboom" {
		t.Errorf("recovered %v, want the original panic value", recovered)
	}
	var summaries int
	for _, rec := range logRecords(t, logs) {
		if rec["msg"] != "forest request" {
			continue
		}
		summaries++
		if rec["level"] != "ERROR" || rec["outcome"] != "panic" || rec["panic"] != "kaboom" {
			t.Errorf("summary = %v, want ERROR outcome=panic panic=kaboom", rec)
		}
	}
	if summaries != 1 {
		t.Errorf("%d summary lines, want 1", summaries)
	}
}
