package forest

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"sync"
	"time"

	"github.com/snailuj/metaforge/internal/llm"
	"github.com/snailuj/metaforge/internal/observe"
)

// maxJudgeCalls bounds the concurrent judge calls of one streamed request.
const maxJudgeCalls = 4

// StreamEvent is one event of a streamed forest. Data is a StageEvent,
// HopEvent, KeptEvent, RejectedEvent or Forest; Name is its server-sent event
// name.
type StreamEvent struct {
	Name string
	Data any
}

// Stage names for StageEvent.
const (
	stageDrafting = "drafting"
	stageRetrying = "retrying"
	stageJudging  = "judging"
)

// StageEvent says what the server is waiting on. Facet and Word identify the
// facet being judged and are unset for the generator stages.
type StageEvent struct {
	Stage string `json:"stage"`
	Facet *int   `json:"facet,omitempty"`
	Word  string `json:"word,omitempty"`
}

// HopEvent is one hop as the generator wrote it, before any judging.
type HopEvent struct {
	PathID string `json:"path_id"`
	Facet  int    `json:"facet"`
	From   string `json:"from"`
	To     string `json:"to"`
	Ground string `json:"ground"`
}

// KeptEvent resolves a path that survived judging.
type KeptEvent struct {
	PathID   string `json:"path_id"`
	Endpoint string `json:"endpoint"`
	Score    int    `json:"score"`
}

// RejectedEvent resolves a path that did not.
type RejectedEvent struct {
	PathID string `json:"path_id"`
	Reason string `json:"reason"`
}

var errNoStreaming = errors.New("forest: the model client cannot stream")

// CanStream reports whether GenerateStream is available.
func (s *Service) CanStream() bool {
	_, ok := s.llm.(llm.Streamer)
	return ok
}

// GenerateStream grows a forest like Generate, but calls emit as the work
// happens: a hop as each is written, a kept or rejected event once for every
// path that got a hop, and a Forest snapshot of everything kept so far after
// each judged facet. Each facet is judged on its own, as soon as it is
// complete. emit is never called concurrently and never after return. The
// returned forest is the last snapshot.
func (s *Service) GenerateStream(ctx context.Context, source string, maxHops int, emit func(StreamEvent)) (forest Forest, err error) {
	streamer, ok := s.llm.(llm.Streamer)
	if !ok {
		return Forest{}, errNoStreaming
	}
	r := &streamRun{s: s, streamer: streamer, source: source, maxHops: maxHops, emit: emit,
		keptRoute: map[string]bool{}, sem: make(chan struct{}, maxJudgeCalls)}
	genAttempts := 1
	defer func() {
		p := recover()
		s.logRequest(source, maxHops, r.gen, r.judge, genAttempts, r.judgeCalls > 0, forest, err, p, "streamed", true, "judge_calls", r.judgeCalls)
		if p != nil {
			panic(p)
		}
	}()
	// Judge goroutines must finish before return, whatever the outcome.
	defer r.wg.Wait()

	facets, valid, err := r.attempt(ctx, 0, stageDrafting, &r.gen)
	if err != nil {
		return Forest{}, err
	}
	if valid < s.cfg.MinPaths {
		s.Logger.Warn("forest: thin generator output, retrying", "word", source, "valid", valid, "min_paths", s.cfg.MinPaths)
		var retry callRecord
		_, _, err := r.attempt(ctx, facets, stageRetrying, &retry)
		r.mu.Lock()
		r.gen.add(retry)
		r.mu.Unlock()
		genAttempts++
		switch {
		case errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded):
			return Forest{}, err
		case err != nil:
			s.Logger.Warn("forest: generator retry failed, keeping first attempt", "word", source, "error", err.Error())
		}
	}

	r.wg.Wait()
	if err := ctx.Err(); err != nil {
		return Forest{}, err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if len(r.kept) == 0 && r.judgeErr != nil {
		return Forest{}, fmt.Errorf("judge: %w", r.judgeErr)
	}
	return r.snapshot(), nil
}

type streamRun struct {
	s        *Service
	streamer llm.Streamer
	source   string
	maxHops  int
	wg       sync.WaitGroup
	sem      chan struct{}

	// mu guards everything below, and every call to emit.
	mu         sync.Mutex
	emit       func(StreamEvent)
	gen, judge callRecord
	judgeCalls int
	judgeErr   error
	kept       []ScoredPath
	keptRoute  map[string]bool // routeKey of every kept path
	stats      Stats
	screened   int // paths considered so far; past maxPaths they count as invalid
}

func (r *streamRun) send(name string, data any) { r.emit(StreamEvent{Name: name, Data: data}) }

// attempt streams one generator call. Facets are numbered from base, so ids
// never repeat across attempts. It returns how many facets it saw and how
// many of their paths passed screening.
func (r *streamRun) attempt(ctx context.Context, base int, stage string, rec *callRecord) (facets, valid int, err error) {
	var sc Scanner
	scanOK := true
	words := map[int]string{}   // facet index -> normalised facet word
	last := map[[2]int]string{} // (facet, branch) -> last hop word sent
	sent := map[string]bool{}   // hop keys already sent
	onText := func(chunk string) {
		if !scanOK {
			return
		}
		evs, err := sc.Feed(chunk)
		if err != nil {
			scanOK = false
			r.s.Logger.Warn("forest: streamed generator output is not JSON; waiting for the full answer", "word", r.source, "error", err.Error())
		}
		for _, ev := range evs {
			n, v := r.onValue(ctx, base, ev, words, last, sent)
			facets += n
			valid += v
		}
	}

	r.mu.Lock()
	r.send("stage", StageEvent{Stage: stage})
	r.mu.Unlock()

	stop := observe.Start("forest_generate")
	start := time.Now()
	resp, err := r.streamer.Stream(ctx, llm.Request{
		Model:     r.s.cfg.Model,
		System:    GeneratorSystemPrompt,
		User:      GeneratorUserMessage(r.source, r.maxHops),
		Schema:    GeneratorSchema(),
		Effort:    r.s.cfg.Effort,
		MaxTokens: callMaxTokens,
	}, onText)
	stop("model", r.s.cfg.Model, "input_tokens", resp.Usage.InputTokens,
		"output_tokens", resp.Usage.OutputTokens, "cache_read_tokens", resp.Usage.CacheReadTokens, "streamed", true)
	r.mu.Lock()
	rec.latency, rec.usage = time.Since(start), resp.Usage
	r.mu.Unlock()
	if err != nil {
		return facets, valid, fmt.Errorf("generate: %w", err)
	}
	if !scanOK {
		// The scanner gave up, so judge whatever the full answer holds.
		g, err := ParseGenerated(resp.Text)
		if err != nil {
			return facets, valid, fmt.Errorf("generate: %w", err)
		}
		for i := facets; i < len(g.Facets); i++ {
			valid += r.facetDone(ctx, base+i, g.Facets[i], sent)
			facets++
		}
	}
	return facets, valid, nil
}

// onValue reacts to one scanned value: it sends hops as they complete and
// screens and judges a facet once it is whole.
func (r *streamRun) onValue(ctx context.Context, base int, ev ScanEvent, words map[int]string, last map[[2]int]string, sent map[string]bool) (facets, valid int) {
	p := ev.Path
	if len(p) < 2 || p[0] != "facets" {
		return 0, 0
	}
	i, err := strconv.Atoi(p[1])
	if err != nil {
		return 0, 0
	}
	switch {
	case len(p) == 2:
		var f Facet
		if err := json.Unmarshal(ev.Raw, &f); err != nil {
			r.s.Logger.Warn("forest: streamed facet did not decode", "word", r.source, "facet", base+i, "error", err.Error())
			return 1, 0
		}
		return 1, r.facetDone(ctx, base+i, f, sent)
	case len(p) == 3 && p[2] == "word":
		var w string
		if json.Unmarshal(ev.Raw, &w) == nil {
			words[i] = NormalizeWord(w)
		}
	case len(p) == 3 && p[2] == "ground":
		var g string
		if w, ok := words[i]; ok && json.Unmarshal(ev.Raw, &g) == nil {
			r.sendHop(sent, facetID(base+i), base+i, r.source, w, g)
		}
	case len(p) == 6 && p[2] == "branches" && p[4] == "hops":
		j, err1 := strconv.Atoi(p[3])
		k, err2 := strconv.Atoi(p[5])
		var h Hop
		if err1 != nil || err2 != nil || json.Unmarshal(ev.Raw, &h) != nil {
			return 0, 0
		}
		from, ok := last[[2]int{i, j}]
		if k == 0 {
			from, ok = words[i]
		}
		if !ok {
			return 0, 0 // facetDone sends it from the whole facet
		}
		to := NormalizeWord(h.Word)
		last[[2]int{i, j}] = to
		r.sendHopAt(sent, branchID(base+i, j), k, base+i, from, to, h.Ground)
	}
	return 0, 0
}

func facetID(i int) string     { return "f" + strconv.Itoa(i) }
func branchID(i, j int) string { return facetID(i) + "b" + strconv.Itoa(j) }

func (r *streamRun) sendHop(sent map[string]bool, id string, facet int, from, to, ground string) {
	r.sendHopAt(sent, id, 0, facet, from, to, ground)
}

func (r *streamRun) sendHopAt(sent map[string]bool, id string, k, facet int, from, to, ground string) {
	key := id + "/" + strconv.Itoa(k)
	if sent[key] {
		return
	}
	sent[key] = true
	r.mu.Lock()
	defer r.mu.Unlock()
	r.send("hop", HopEvent{PathID: id, Facet: facet, From: from, To: to, Ground: collapseSpace(ground)})
}

// facetDone sends any hop the stream could not place, screens the facet's
// paths, resolves the invalid ones and starts the judge on the rest. It
// returns how many paths passed screening.
func (r *streamRun) facetDone(ctx context.Context, fi int, f Facet, sent map[string]bool) int {
	head := NormalizeWord(f.Word)
	r.sendHop(sent, facetID(fi), fi, r.source, head, f.Ground)
	type idPath struct {
		id string
		p  Path
	}
	var paths []idPath
	if line := collapseSpace(f.Line); line != "" {
		paths = append(paths, idPath{facetID(fi), Path{Words: []string{head}, Grounds: []string{collapseSpace(f.Ground)}, Line: line}})
	}
	for j, b := range f.Branches {
		p := Path{Words: []string{head}, Grounds: []string{collapseSpace(f.Ground)}, Line: collapseSpace(b.Line)}
		prev := head
		for k, h := range b.Hops {
			w := NormalizeWord(h.Word)
			r.sendHopAt(sent, branchID(fi, j), k, fi, prev, w, h.Ground)
			p.Words = append(p.Words, w)
			p.Grounds = append(p.Grounds, collapseSpace(h.Ground))
			prev = w
		}
		paths = append(paths, idPath{branchID(fi, j), p})
	}

	r.mu.Lock()
	if collapseSpace(f.Line) == "" {
		// Not a candidate, so not counted; resolved so the client can let go of it.
		r.send("rejected", RejectedEvent{PathID: facetID(fi), Reason: reasonInvalid})
	}
	var ids []string
	var valid []Path
	for _, ip := range paths {
		r.stats.Generated++
		r.screened++
		if r.screened > maxPaths || ValidatePath(r.source, r.maxHops, ip.p) != nil {
			r.stats.Rejected.Invalid++
			r.send("rejected", RejectedEvent{PathID: ip.id, Reason: reasonInvalid})
			continue
		}
		ids = append(ids, ip.id)
		valid = append(valid, ip.p)
	}
	r.mu.Unlock()

	if len(valid) > 0 {
		r.wg.Add(1)
		go r.judgeFacet(ctx, fi, head, ids, valid)
	}
	return len(valid)
}

// judgeFacet judges one facet's screened paths and resolves each of them.
func (r *streamRun) judgeFacet(ctx context.Context, fi int, word string, ids []string, paths []Path) {
	defer r.wg.Done()
	select {
	case r.sem <- struct{}{}:
		defer func() { <-r.sem }()
	case <-ctx.Done():
		return
	}

	r.mu.Lock()
	r.send("stage", StageEvent{Stage: stageJudging, Facet: &fi, Word: word})
	r.mu.Unlock()

	var rec callRecord
	resp, err := r.s.call(ctx, "forest_judge", &rec, llm.Request{
		Model:     r.s.cfg.JudgeModel,
		System:    JudgeSystemPrompt,
		User:      JudgeUserMessage(r.source, paths),
		Schema:    JudgeSchema(),
		Effort:    r.s.cfg.Effort,
		MaxTokens: callMaxTokens,
	})
	var verdicts []Verdict
	if err == nil {
		verdicts, err = ParseVerdicts(resp.Text)
	}

	r.mu.Lock()
	defer r.mu.Unlock()
	r.judge.add(rec)
	r.judgeCalls++
	if ctx.Err() != nil {
		return // the request is over; nothing more reaches the client
	}
	if err != nil {
		r.s.Logger.Error("forest: judge failed, rejecting its facet", "word", r.source, "facet", fi, "paths", len(paths), "error", err.Error())
		r.judgeErr = err
		for _, id := range ids {
			r.stats.Rejected.Invalid++
			r.send("rejected", RejectedEvent{PathID: id, Reason: reasonInvalid})
		}
		return
	}

	outs, ignored := judgePaths(paths, verdicts, r.s.cfg.MinScore)
	for _, idx := range ignored {
		r.s.Logger.Warn("forest: judge verdict ignored", "word", r.source, "facet", fi, "index", idx, "paths_judged", len(paths))
	}
	for i, o := range outs {
		if o.reason == "" {
			end := o.scored.Words[len(o.scored.Words)-1]
			if route := routeKey(o.scored.Words); r.keptRoute[route] {
				o.reason = reasonDuplicate
			} else {
				r.keptRoute[route] = true
				r.kept = append(r.kept, o.scored)
				r.send("kept", KeptEvent{PathID: ids[i], Endpoint: end, Score: o.scored.Score})
				continue
			}
		}
		r.stats.Rejected.count(o.reason)
		r.send("rejected", RejectedEvent{PathID: ids[i], Reason: o.reason})
	}
	r.send("forest", r.snapshot())
}

// snapshot merges everything kept so far. Callers hold mu.
func (r *streamRun) snapshot() Forest {
	f := Merge(r.source, r.kept)
	f.MaxHops = r.maxHops
	f.Model = r.s.cfg.Model
	f.Stats = r.stats
	f.Stats.Kept = len(r.kept)
	return f
}
