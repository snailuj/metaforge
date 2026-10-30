package handler

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/snailuj/metaforge/internal/forest"
)

// fakeStreamGen streams a fixed list of events, then returns its result.
type fakeStreamGen struct {
	fakeForestGen
	events  []forest.StreamEvent
	streams int
	pause   time.Duration // between events
}

func (f *fakeStreamGen) GenerateStream(ctx context.Context, word string, maxHops int, emit func(forest.StreamEvent)) (forest.Forest, error) {
	f.streams++
	for _, ev := range f.events {
		emit(ev)
		if f.pause > 0 {
			select {
			case <-time.After(f.pause):
			case <-ctx.Done():
				return forest.Forest{}, ctx.Err()
			}
		}
	}
	return f.forest, f.err
}

type sseEvent struct{ name, data string }

func parseSSE(t *testing.T, body string) (events []sseEvent, comments int) {
	t.Helper()
	var cur sseEvent
	sc := bufio.NewScanner(strings.NewReader(body))
	for sc.Scan() {
		line := sc.Text()
		switch {
		case line == "":
			if cur.name != "" {
				events = append(events, cur)
			}
			cur = sseEvent{}
		case strings.HasPrefix(line, ":"):
			comments++
		case strings.HasPrefix(line, "event: "):
			cur.name = strings.TrimPrefix(line, "event: ")
		case strings.HasPrefix(line, "data: "):
			if cur.data != "" {
				t.Errorf("event %s has more than one data line", cur.name)
			}
			cur.data = strings.TrimPrefix(line, "data: ")
		default:
			t.Errorf("unexpected SSE line %q", line)
		}
	}
	if cur.name != "" {
		t.Errorf("stream ended mid-event %q", cur.name)
	}
	return events, comments
}

func getForestStream(h *ForestHandler, query string) *httptest.ResponseRecorder {
	r := httptest.NewRequest(http.MethodGet, "/forge/forest?"+query, nil)
	r.Header.Set("Accept", "text/event-stream")
	w := httptest.NewRecorder()
	h.HandleForest(w, r)
	return w
}

func streamEvents() []forest.StreamEvent {
	return []forest.StreamEvent{
		{Name: "hop", Data: forest.HopEvent{PathID: "f0", From: "patience", To: "seed", Ground: "waits"}},
		{Name: "kept", Data: forest.KeptEvent{PathID: "f0", Endpoint: "seed", Score: 7}},
		{Name: "forest", Data: forestWithLine("A.")},
	}
}

// Rule: an event-stream request gets every service event in order, framed as
// server-sent events, then exactly one done carrying the final forest.
func TestForestStreamFramesEventsThenDone(t *testing.T) {
	gen := &fakeStreamGen{events: streamEvents(), fakeForestGen: fakeForestGen{forest: forestWithLine("A.")}}
	w := getForestStream(newForestTestHandler(gen, 4, 30), "word=patience")

	if w.Code != http.StatusOK || w.Header().Get("Content-Type") != "text/event-stream" {
		t.Fatalf("status %d, content-type %q", w.Code, w.Header().Get("Content-Type"))
	}
	if w.Header().Get("Cache-Control") != "no-cache" || w.Header().Get("X-Accel-Buffering") != "no" {
		t.Errorf("headers = %v", w.Header())
	}
	evs, _ := parseSSE(t, w.Body.String())
	var names []string
	for _, e := range evs {
		names = append(names, e.name)
		if !json.Valid([]byte(e.data)) {
			t.Errorf("%s data is not JSON: %q", e.name, e.data)
		}
	}
	if strings.Join(names, ",") != "hop,kept,forest,done" {
		t.Fatalf("events = %v", names)
	}
	var hop forest.HopEvent
	_ = json.Unmarshal([]byte(evs[0].data), &hop)
	if hop.PathID != "f0" || hop.To != "seed" {
		t.Errorf("hop = %+v", hop)
	}
	if got := decodeForest(t, []byte(evs[3].data)); got.Endpoints[0].Line != "A." {
		t.Errorf("done = %+v", got)
	}
	if gen.called != 0 || gen.streams != 1 {
		t.Errorf("Generate called %d, GenerateStream %d", gen.called, gen.streams)
	}
}

// Rule: a stage event reaches the client as `event: stage` with the contract's
// exact JSON; drafting carries no facet or word, judging carries both.
func TestForestStreamFramesStageEvents(t *testing.T) {
	two := 2
	gen := &fakeStreamGen{
		events: []forest.StreamEvent{
			{Name: "stage", Data: forest.StageEvent{Stage: "drafting"}},
			{Name: "stage", Data: forest.StageEvent{Stage: "judging", Facet: &two, Word: "dormant seed"}},
		},
		fakeForestGen: fakeForestGen{forest: forestWithLine("A.")},
	}
	w := getForestStream(newForestTestHandler(gen, 4, 30), "word=patience")
	evs, _ := parseSSE(t, w.Body.String())
	if len(evs) != 3 || evs[0].name != "stage" || evs[1].name != "stage" || evs[2].name != "done" {
		t.Fatalf("events = %+v", evs)
	}
	if evs[0].data != `{"stage":"drafting"}` {
		t.Errorf("drafting data = %s", evs[0].data)
	}
	if evs[1].data != `{"stage":"judging","facet":2,"word":"dormant seed"}` {
		t.Errorf("judging data = %s", evs[1].data)
	}
}

// Rule: without an event-stream Accept header the endpoint answers JSON as before.
func TestForestWithoutAcceptStaysJSON(t *testing.T) {
	gen := &fakeStreamGen{events: streamEvents(), fakeForestGen: fakeForestGen{forest: forestWithLine("A.")}}
	w := getForest(newForestTestHandler(gen, 4, 30), "word=patience")
	if w.Code != http.StatusOK || !strings.HasPrefix(w.Header().Get("Content-Type"), "application/json") || gen.streams != 0 {
		t.Fatalf("status %d type %q streams %d", w.Code, w.Header().Get("Content-Type"), gen.streams)
	}
}

// Rule: failures before the stream starts keep their status codes and JSON bodies.
func TestForestStreamRefusalsBeforeStreamKeepStatus(t *testing.T) {
	gen := &fakeStreamGen{}
	if w := getForestStream(newForestTestHandler(gen, 4, 30), "word=%3Cscript%3E"); w.Code != http.StatusBadRequest || errorBody(t, w) == "" {
		t.Errorf("bad word: %d", w.Code)
	}
	if w := getForestStream(newForestTestHandler(nil, 4, 30), "word=patience"); w.Code != http.StatusServiceUnavailable {
		t.Errorf("unconfigured: %d", w.Code)
	}
	h := newForestTestHandler(gen, 4, 1)
	_ = getForestStream(h, "word=patience")
	w := getForestStream(h, "word=patience")
	if w.Code != http.StatusTooManyRequests || w.Header().Get("Retry-After") == "" {
		t.Errorf("rate limited: %d %v", w.Code, w.Header())
	}
}

// Rule: a failure after the stream started ends it with one error event
// naming its kind, after the events already sent.
func TestForestStreamErrorEvent(t *testing.T) {
	for _, tc := range []struct {
		err  error
		kind string
	}{
		{errors.New("judge: overloaded"), "failed"},
		{fmt.Errorf("generate: %w", context.DeadlineExceeded), "timeout"},
	} {
		gen := &fakeStreamGen{events: streamEvents()[:1], fakeForestGen: fakeForestGen{err: tc.err}}
		evs, _ := parseSSE(t, getForestStream(newForestTestHandler(gen, 4, 30), "word=patience").Body.String())
		if len(evs) != 2 || evs[0].name != "hop" || evs[1].name != "error" {
			t.Fatalf("%v: events = %v", tc.err, evs)
		}
		var body map[string]string
		_ = json.Unmarshal([]byte(evs[1].data), &body)
		if body["kind"] != tc.kind || body["error"] == "" {
			t.Errorf("%v: error event = %v", tc.err, body)
		}
	}
}

// Rule: a streamed forest is cached like a JSON one, and a cache hit streams
// as a single done event without spending anything.
func TestForestStreamCache(t *testing.T) {
	gen := &fakeStreamGen{events: streamEvents(), fakeForestGen: fakeForestGen{forest: forestWithLine("A.")}}
	cache := &fakeForestCache{}
	h := newForestTestHandler(gen, 4, 30)
	h.Cache = cache
	w := getForestStream(h, "word=patience")
	if len(cache.added) != 1 || w.Header().Get("X-Forest-Cache") != "miss" {
		t.Fatalf("added %d, X-Forest-Cache %q", len(cache.added), w.Header().Get("X-Forest-Cache"))
	}

	cache.pool = []forest.Forest{forestWithLine("cached.")}
	w = getForestStream(h, "word=patience")
	evs, _ := parseSSE(t, w.Body.String())
	if len(evs) != 1 || evs[0].name != "done" || w.Header().Get("X-Forest-Cache") != "hit" || gen.streams != 1 {
		t.Fatalf("events = %v, cache %q, streams %d", evs, w.Header().Get("X-Forest-Cache"), gen.streams)
	}
	if decodeForest(t, []byte(evs[0].data)).Endpoints[0].Line != "cached." {
		t.Errorf("done = %s", evs[0].data)
	}

	gen.err = errors.New("boom")
	cache.pool = nil
	_ = getForestStream(h, "word=patience")
	if len(cache.added) != 1 {
		t.Errorf("a failed stream was cached")
	}
}

// Rule: an idle stream carries keepalive comments so proxies keep it open.
func TestForestStreamKeepalive(t *testing.T) {
	gen := &fakeStreamGen{events: streamEvents()[:2], pause: 30 * time.Millisecond, fakeForestGen: fakeForestGen{forest: forestWithLine("A.")}}
	h := newForestTestHandler(gen, 4, 30)
	h.Keepalive = 10 * time.Millisecond
	_, comments := parseSSE(t, getForestStream(h, "word=patience").Body.String())
	if comments < 2 {
		t.Errorf("%d keepalive comments, want at least 2", comments)
	}
}

type cannotStream struct{ fakeStreamGen }

func (cannotStream) CanStream() bool { return false }

// Rule: a generator that says it cannot stream is answered as JSON.
func TestForestStreamFallsBackToJSON(t *testing.T) {
	gen := &cannotStream{fakeStreamGen{fakeForestGen: fakeForestGen{forest: forestWithLine("A.")}}}
	w := getForestStream(newForestTestHandler(gen, 4, 30), "word=patience")
	if !strings.HasPrefix(w.Header().Get("Content-Type"), "application/json") || gen.streams != 0 || gen.called != 1 {
		t.Errorf("type %q streams %d called %d", w.Header().Get("Content-Type"), gen.streams, gen.called)
	}
}
