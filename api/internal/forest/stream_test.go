package forest

import (
	"context"
	"errors"
	"fmt"
	"reflect"
	"regexp"
	"strings"
	"sync"
	"testing"

	"github.com/snailuj/metaforge/internal/llm"
)

// fakeStreamer streams generator answers in small chunks and answers judge
// calls from a score per line, so concurrent judge calls need no ordering.
type fakeStreamer struct {
	mu        sync.Mutex
	gens      []fakeResult // generator answers, in order
	genCalls  int
	scores    map[string]int   // line -> score; a missing line gets 0
	judgeErrs map[string]error // judge fails when its message holds this line
	chunk     int
	sent      int // chunks handed to onText so far, read by emit hooks
	judges    []llm.Request
}

func (f *fakeStreamer) Complete(ctx context.Context, req llm.Request) (llm.Response, error) {
	if req.System != JudgeSystemPrompt {
		return llm.Response{}, errors.New("generator must stream")
	}
	f.mu.Lock()
	f.judges = append(f.judges, req)
	f.mu.Unlock()
	for line, err := range f.judgeErrs {
		if strings.Contains(req.User, "line: "+line) {
			return llm.Response{}, err
		}
	}
	var vs []string
	for i, m := range regexp.MustCompile(`(?m)^   line: (.*)$`).FindAllStringSubmatch(req.User, -1) {
		vs = append(vs, fmt.Sprintf(`{"index":%d,"reason":"r","broken_hop":false,"drift":false,"literal":false,"cliche":false,"score":%d}`, i+1, f.scores[m[1]]))
	}
	return llm.Response{Text: `{"verdicts":[` + strings.Join(vs, ",") + `]}`, Usage: llm.Usage{InputTokens: 5, OutputTokens: 5}}, nil
}

func (f *fakeStreamer) Stream(ctx context.Context, req llm.Request, onText func(string)) (llm.Response, error) {
	f.mu.Lock()
	r := f.gens[f.genCalls]
	f.genCalls++
	f.mu.Unlock()
	if r.err != nil {
		return llm.Response{}, r.err
	}
	text := r.resp.Text
	for i := 0; i < len(text); i += f.chunk {
		onText(text[i:min(i+f.chunk, len(text))])
		f.mu.Lock()
		f.sent++
		f.mu.Unlock()
	}
	return r.resp, nil
}

type recorded struct {
	ev      StreamEvent
	atChunk int
}

func runStream(t *testing.T, f *fakeStreamer, maxHops int, cfg func(*Config)) ([]recorded, Forest, error) {
	t.Helper()
	if f.chunk == 0 {
		f.chunk = 7
	}
	s, _ := testService(&fakeLLM{})
	s.llm = f
	if cfg != nil {
		cfg(&s.cfg)
	}
	var mu sync.Mutex
	var evs []recorded
	forest, err := s.GenerateStream(context.Background(), "patience", maxHops, func(ev StreamEvent) {
		f.mu.Lock()
		at := f.sent
		f.mu.Unlock()
		mu.Lock()
		evs = append(evs, recorded{ev, at})
		mu.Unlock()
	})
	return evs, forest, err
}

// resolutions maps each path id to the names of the events that resolved it.
func resolutions(t *testing.T, evs []recorded) (hops map[string]bool, resolved map[string][]string) {
	t.Helper()
	hops, resolved = map[string]bool{}, map[string][]string{}
	for _, r := range evs {
		switch d := r.ev.Data.(type) {
		case HopEvent:
			hops[d.PathID] = true
		case KeptEvent:
			if !hops[d.PathID] {
				t.Errorf("kept %s before any hop", d.PathID)
			}
			resolved[d.PathID] = append(resolved[d.PathID], "kept")
		case RejectedEvent:
			if !hops[d.PathID] {
				t.Errorf("rejected %s before any hop", d.PathID)
			}
			resolved[d.PathID] = append(resolved[d.PathID], "rejected:"+d.Reason)
		}
	}
	return hops, resolved
}

var streamScores = map[string]int{"Patience is a seed vault.": 8, "Patience is an orrery.": 3}

// Rule: the first hop reaches the client before the generator finishes.
func TestStreamSendsHopsWhileGenerating(t *testing.T) {
	f := &fakeStreamer{gens: []fakeResult{ok(generatedJSON, 1, 1, 0)}, scores: streamScores}
	evs, _, err := runStream(t, f, 3, nil)
	if err != nil {
		t.Fatal(err)
	}
	total := (len(generatedJSON) + f.chunk - 1) / f.chunk
	h := indexOf(evs, func(e StreamEvent) bool { return e.Name == "hop" })
	if h < 0 {
		t.Fatalf("no hop event in %+v", evs)
	}
	if evs[h].atChunk >= total/2 {
		t.Errorf("first hop sent after chunk %d of %d", evs[h].atChunk, total)
	}
	first := evs[h].ev.Data.(HopEvent)
	if first != (HopEvent{PathID: "f0", Facet: 0, From: "patience", To: "dormant seed", Ground: "waits"}) {
		t.Errorf("first hop = %+v", first)
	}
}

// stagesOf returns the stage events in arrival order.
func stagesOf(evs []recorded) (out []StageEvent) {
	for _, r := range evs {
		if d, ok := r.ev.Data.(StageEvent); ok {
			if r.ev.Name != "stage" {
				panic("StageEvent sent as " + r.ev.Name)
			}
			out = append(out, d)
		}
	}
	return out
}

// indexOf returns the position of the first event matching, or -1.
func indexOf(evs []recorded, match func(StreamEvent) bool) int {
	for i, r := range evs {
		if match(r.ev) {
			return i
		}
	}
	return -1
}

// Rule: the client is told the generator call has started before the first
// hop, and only once when no retry runs.
func TestStreamSendsDraftingBeforeFirstHop(t *testing.T) {
	f := &fakeStreamer{gens: []fakeResult{ok(generatedJSON, 1, 1, 0)}, scores: streamScores}
	evs, _, err := runStream(t, f, 3, nil)
	if err != nil {
		t.Fatal(err)
	}
	if got := stagesOf(evs); len(got) == 0 || got[0] != (StageEvent{Stage: "drafting"}) {
		t.Fatalf("stages = %+v, want drafting first", got)
	}
	drafting := indexOf(evs, func(e StreamEvent) bool { return e.Name == "stage" && e.Data.(StageEvent).Stage == "drafting" })
	hop := indexOf(evs, func(e StreamEvent) bool { return e.Name == "hop" })
	if hop < 0 {
		t.Fatal("no hop event: the comparison would be vacuous")
	}
	if drafting != 0 || drafting > hop {
		t.Errorf("drafting at %d, first hop at %d", drafting, hop)
	}
	n := 0
	for _, s := range stagesOf(evs) {
		if s.Stage == "drafting" {
			n++
		}
	}
	if n != 1 {
		t.Errorf("%d drafting events, want 1", n)
	}
}

// Rule: every path that got a hop resolves exactly once, kept or rejected,
// and the outcome matches what the non-streaming pipeline decides.
func TestStreamResolvesEveryPathOnceAndMatchesGenerate(t *testing.T) {
	f := &fakeStreamer{gens: []fakeResult{ok(generatedJSON, 1, 1, 0)}, scores: streamScores}
	evs, forest, err := runStream(t, f, 3, nil)
	if err != nil {
		t.Fatal(err)
	}
	hops, resolved := resolutions(t, evs)
	want := map[string][]string{
		"f0":   {"rejected:invalid"}, // no line of its own
		"f0b0": {"kept"},
		"f0b1": {"rejected:invalid"}, // empty ground
		"f0b2": {"rejected:low_score"},
	}
	if !reflect.DeepEqual(resolved, want) {
		t.Errorf("resolved = %v, want %v", resolved, want)
	}
	if len(hops) != len(want) {
		t.Errorf("hop ids = %v", hops)
	}

	// The same answers through Generate give the same forest.
	judged := `{"verdicts":[{"index":1,"reason":"r","broken_hop":false,"drift":false,"literal":false,"cliche":false,"score":8},` +
		`{"index":2,"reason":"r","broken_hop":false,"drift":false,"literal":false,"cliche":false,"score":3}]}`
	s, _ := testService(&fakeLLM{results: []fakeResult{ok(generatedJSON, 1, 1, 0), ok(judged, 1, 1, 0)}})
	plain, err := s.Generate(context.Background(), "patience", 3)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(forest, plain) {
		t.Errorf("stream forest = %+v\nplain forest = %+v", forest, plain)
	}
}

// Rule: a forest snapshot only ever holds kept paths, and grows.
func TestStreamSnapshotsHoldOnlyKeptPaths(t *testing.T) {
	two := `{"facets":[
	 {"word":"seed","ground":"waits","line":"Patience is a seed.","branches":[
	   {"hops":[{"word":"seed vault","ground":"keeps"}],"line":"Patience is a seed vault."}]},
	 {"word":"glacier","ground":"slow","line":"Patience is a glacier.","branches":[
	   {"hops":[{"word":"orrery","ground":"turns"}],"line":"Patience is an orrery."}]}]}`
	scores := map[string]int{"Patience is a seed vault.": 8, "Patience is a glacier.": 7, "Patience is a seed.": 2, "Patience is an orrery.": 1}
	f := &fakeStreamer{gens: []fakeResult{ok(two, 1, 1, 0)}, scores: scores}
	evs, forest, err := runStream(t, f, 3, nil)
	if err != nil {
		t.Fatal(err)
	}
	kept := map[string]bool{}
	snapshots := 0
	for _, r := range evs {
		switch d := r.ev.Data.(type) {
		case KeptEvent:
			kept[d.Endpoint] = true
		case Forest:
			snapshots++
			for _, e := range d.Endpoints {
				if !kept[e.ID] {
					t.Errorf("snapshot holds %q before it was kept", e.ID)
				}
			}
			if len(d.Endpoints) != len(kept) {
				t.Errorf("snapshot has %d endpoints, %d kept so far", len(d.Endpoints), len(kept))
			}
		}
	}
	if snapshots != 2 || len(forest.Endpoints) != 2 {
		t.Errorf("snapshots=%d final endpoints=%d, want 2 and 2", snapshots, len(forest.Endpoints))
	}
	if len(f.judges) != 2 {
		t.Errorf("%d judge calls, want one per facet", len(f.judges))
	}
}

// Rule: across facets every distinct route to an endpoint is kept; only a
// path with the same words as one already kept is a duplicate.
func TestStreamKeepsEveryRouteToAnEndpoint(t *testing.T) {
	routes := `{"facets":[
	 {"word":"seed","ground":"waits","line":"","branches":[{"hops":[{"word":"vault","ground":"keeps"}],"line":"A."}]},
	 {"word":"bank","ground":"holds","line":"","branches":[{"hops":[{"word":"vault","ground":"locks"}],"line":"B."}]},
	 {"word":"seed","ground":"sleeps","line":"","branches":[{"hops":[{"word":"vault","ground":"guards"}],"line":"C."}]}]}`
	f := &fakeStreamer{gens: []fakeResult{ok(routes, 1, 1, 0)}, scores: map[string]int{"A.": 7, "B.": 9, "C.": 8}}
	evs, forest, err := runStream(t, f, 3, nil)
	if err != nil {
		t.Fatal(err)
	}
	_, resolved := resolutions(t, evs)
	if resolved["f1b0"][0] != "kept" {
		t.Errorf("a second route to vault was not kept: %v", resolved)
	}
	a, c := resolved["f0b0"][0], resolved["f2b0"][0]
	if !((a == "kept" && c == "rejected:duplicate") || (a == "rejected:duplicate" && c == "kept")) {
		t.Errorf("resolved = %v, want one of the two seed>vault routes kept", resolved)
	}
	if len(forest.Endpoints) != 2 || forest.Endpoints[0].ID != "vault" || forest.Endpoints[1].ID != "vault" || forest.Stats.Rejected.Duplicate != 1 {
		t.Errorf("forest = %+v", forest)
	}
}

// Rule: a failed judge call rejects only its facet; with nothing kept the
// stream fails rather than ending on an empty forest.
func TestStreamJudgeFailureRejectsItsFacet(t *testing.T) {
	two := `{"facets":[
	 {"word":"seed","ground":"waits","line":"A.","branches":[]},
	 {"word":"glacier","ground":"slow","line":"B.","branches":[]}]}`
	f := &fakeStreamer{gens: []fakeResult{ok(two, 1, 1, 0)}, scores: map[string]int{"A.": 8, "B.": 8},
		judgeErrs: map[string]error{"B.": errors.New("overloaded")}}
	evs, forest, err := runStream(t, f, 3, nil)
	if err != nil {
		t.Fatal(err)
	}
	_, resolved := resolutions(t, evs)
	if !reflect.DeepEqual(resolved, map[string][]string{"f0": {"kept"}, "f1": {"rejected:invalid"}}) {
		t.Errorf("resolved = %v", resolved)
	}
	if len(forest.Endpoints) != 1 {
		t.Errorf("endpoints = %+v", forest.Endpoints)
	}

	f = &fakeStreamer{gens: []fakeResult{ok(two, 1, 1, 0)}, judgeErrs: map[string]error{"A.": errors.New("overloaded"), "B.": errors.New("overloaded")}}
	if _, _, err := runStream(t, f, 3, nil); err == nil {
		t.Error("every judge failed: want an error")
	}
}

// Rule: path ids never repeat across the thin-output retry, and both
// attempts' paths can be kept.
func TestStreamRetryContinuesFacetNumbering(t *testing.T) {
	f := &fakeStreamer{gens: []fakeResult{ok(stubJSON, 1, 1, 0), ok(generatedJSON, 1, 1, 0)}, scores: streamScores}
	evs, forest, err := runStream(t, f, 3, func(c *Config) { c.MinPaths = 2 })
	if err != nil {
		t.Fatal(err)
	}
	_, resolved := resolutions(t, evs)
	for id, rs := range resolved {
		if len(rs) != 1 {
			t.Errorf("%s resolved %d times", id, len(rs))
		}
	}
	if resolved["f0"] == nil || resolved["f1b0"] == nil || resolved["f1b0"][0] != "kept" {
		t.Errorf("resolved = %v, want the stub as f0 and the retry from f1", resolved)
	}
	if f.genCalls != 2 || len(forest.Endpoints) != 1 {
		t.Errorf("genCalls=%d endpoints=%d", f.genCalls, len(forest.Endpoints))
	}
}

// Rule: "retrying" is sent when the thin-output retry starts its generator
// call, before that call's first hop, and never when no retry runs.
func TestStreamSendsRetryingOnlyWhenRetryRuns(t *testing.T) {
	f := &fakeStreamer{gens: []fakeResult{ok(stubJSON, 1, 1, 0), ok(generatedJSON, 1, 1, 0)}, scores: streamScores}
	evs, _, err := runStream(t, f, 3, func(c *Config) { c.MinPaths = 2 })
	if err != nil {
		t.Fatal(err)
	}
	want := []StageEvent{{Stage: "drafting"}, {Stage: "retrying"}}
	if got := stagesOf(evs); !reflect.DeepEqual(got, want) {
		t.Fatalf("stages = %+v, want %+v", got, want)
	}
	retrying := indexOf(evs, func(e StreamEvent) bool { return e.Name == "stage" && e.Data.(StageEvent).Stage == "retrying" })
	retryHop := indexOf(evs, func(e StreamEvent) bool { h, ok := e.Data.(HopEvent); return ok && h.PathID == "f1" })
	if retryHop < 0 {
		t.Fatal("the retry sent no hop: the comparison would be vacuous")
	}
	if retrying > retryHop {
		t.Errorf("retrying at %d, after the retry's first hop at %d", retrying, retryHop)
	}

	f = &fakeStreamer{gens: []fakeResult{ok(generatedJSON, 1, 1, 0)}, scores: streamScores}
	evs, _, err = runStream(t, f, 3, func(c *Config) { c.MinPaths = 1 })
	if err != nil {
		t.Fatal(err)
	}
	if f.genCalls != 1 {
		t.Fatalf("genCalls = %d, want no retry", f.genCalls)
	}
	for _, s := range stagesOf(evs) {
		if s.Stage == "retrying" {
			t.Errorf("retrying sent without a retry: %+v", stagesOf(evs))
		}
	}
}

func TestStreamGeneratorErrorIsReturned(t *testing.T) {
	f := &fakeStreamer{gens: []fakeResult{{err: context.DeadlineExceeded}}}
	if _, _, err := runStream(t, f, 3, nil); !errors.Is(err, context.DeadlineExceeded) {
		t.Errorf("err = %v, want DeadlineExceeded", err)
	}
}
