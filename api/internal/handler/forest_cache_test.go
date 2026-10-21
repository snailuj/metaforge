package handler

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"reflect"
	"testing"

	"github.com/snailuj/metaforge/internal/forest"
)

type fakeForestCache struct {
	pool              []forest.Forest
	readErr, writeErr error
	reads             int
	added             []forest.Forest
	readWord, addWord string
	readHops, addHops int
}

func (c *fakeForestCache) Random(_ context.Context, word string, maxHops int) (forest.Forest, bool, error) {
	c.reads++
	c.readWord, c.readHops = word, maxHops
	if c.readErr != nil || len(c.pool) == 0 {
		return forest.Forest{}, false, c.readErr
	}
	return c.pool[0], true, nil
}

func (c *fakeForestCache) Add(_ context.Context, word string, maxHops int, f forest.Forest) error {
	c.addWord, c.addHops = word, maxHops
	if c.writeErr != nil {
		return c.writeErr
	}
	c.added = append(c.added, f)
	return nil
}

func forestWithLine(line string) forest.Forest {
	return forest.Forest{
		Source: "patience", MaxHops: 3,
		Nodes:     []forest.Node{{ID: "patience", Word: "patience", Role: forest.RoleSource}},
		Endpoints: []forest.Endpoint{{ID: "seed vault", Path: []string{"patience", "seed vault"}, Line: line}},
	}
}

func decodeForest(t *testing.T, body []byte) forest.Forest {
	t.Helper()
	var f forest.Forest
	if err := json.Unmarshal(body, &f); err != nil {
		t.Fatalf("body is not a forest: %v", err)
	}
	return f
}

// Rule: a hit spends nothing: no generator call and no limiter slot, so a
// spent per-minute budget still serves cached forests.
func TestForestCacheHitSkipsGeneratorAndLimiter(t *testing.T) {
	gen := &fakeForestGen{forest: forestWithLine("fresh")}
	cache := &fakeForestCache{pool: []forest.Forest{forestWithLine("cached")}}
	h := newForestTestHandler(gen, 1, 1)
	h.Cache = cache

	for i := range 3 {
		w := getForest(h, "word=Patience&max_hops=2")
		if w.Code != http.StatusOK || w.Header().Get("X-Forest-Cache") != "hit" {
			t.Fatalf("request %d: status %d cache %q", i, w.Code, w.Header().Get("X-Forest-Cache"))
		}
		if got := decodeForest(t, w.Body.Bytes()); got.Endpoints[0].Line != "cached" {
			t.Errorf("served %q, want the cached forest", got.Endpoints[0].Line)
		}
	}
	if gen.called != 0 || cache.readWord != "patience" || cache.readHops != 2 {
		t.Errorf("gen called %d times; cache read %q/%d", gen.called, cache.readWord, cache.readHops)
	}
}

func TestForestCacheMissGeneratesAndStores(t *testing.T) {
	gen := &fakeForestGen{forest: forestWithLine("fresh")}
	cache := &fakeForestCache{}
	h := newForestTestHandler(gen, 4, 30)
	h.Cache = cache

	w := getForest(h, "word=Patience")
	if w.Code != http.StatusOK || w.Header().Get("X-Forest-Cache") != "miss" || gen.called != 1 {
		t.Fatalf("status %d cache %q gen %d", w.Code, w.Header().Get("X-Forest-Cache"), gen.called)
	}
	if len(cache.added) != 1 || !reflect.DeepEqual(cache.added[0], gen.forest) || cache.addWord != "patience" || cache.addHops != 3 {
		t.Errorf("stored %d forests under %q/%d", len(cache.added), cache.addWord, cache.addHops)
	}
}

// Rule: New forest (fresh=1) always generates, and its forest joins the pool.
func TestForestFreshSkipsLookupButStores(t *testing.T) {
	gen := &fakeForestGen{forest: forestWithLine("fresh")}
	cache := &fakeForestCache{pool: []forest.Forest{forestWithLine("cached")}}
	h := newForestTestHandler(gen, 4, 30)
	h.Cache = cache

	w := getForest(h, "word=patience&fresh=1")
	if w.Code != http.StatusOK || w.Header().Get("X-Forest-Cache") != "fresh" {
		t.Fatalf("status %d cache %q", w.Code, w.Header().Get("X-Forest-Cache"))
	}
	if cache.reads != 0 || gen.called != 1 || len(cache.added) != 1 {
		t.Errorf("reads=%d gen=%d added=%d, want 0, 1, 1", cache.reads, gen.called, len(cache.added))
	}
	if got := decodeForest(t, w.Body.Bytes()); got.Endpoints[0].Line != "fresh" {
		t.Errorf("served %q, want the fresh forest", got.Endpoints[0].Line)
	}
}

// Rule: only a forest with endpoints is worth serving again.
func TestForestEmptyOrFailedForestsAreNotStored(t *testing.T) {
	empty := forest.Forest{Source: "patience", MaxHops: 3, Nodes: []forest.Node{{ID: "patience", Word: "patience", Role: forest.RoleSource}}}
	for name, gen := range map[string]*fakeForestGen{
		"empty":  {forest: empty},
		"failed": {err: errors.New("generate: boom")},
	} {
		cache := &fakeForestCache{}
		h := newForestTestHandler(gen, 4, 30)
		h.Cache = cache
		getForest(h, "word=patience")
		if len(cache.added) != 0 {
			t.Errorf("%s forest was stored", name)
		}
	}
}

// Rule: the cache is best-effort; its failures never fail the request.
func TestForestCacheErrorsDegradeToGenerating(t *testing.T) {
	gen := &fakeForestGen{forest: forestWithLine("fresh")}
	cache := &fakeForestCache{readErr: errors.New("disk gone"), writeErr: errors.New("disk gone")}
	h := newForestTestHandler(gen, 4, 30)
	h.Cache = cache

	w := getForest(h, "word=patience")
	if w.Code != http.StatusOK || gen.called != 1 {
		t.Errorf("status %d gen %d, want a generated 200", w.Code, gen.called)
	}
	if got := decodeForest(t, w.Body.Bytes()); got.Endpoints[0].Line != "fresh" {
		t.Errorf("served %q", got.Endpoints[0].Line)
	}
}

// Rule: without an API key the cache still serves what it holds; only a
// miss or a fresh request answers 503.
func TestForestUnconfiguredServesCacheHits(t *testing.T) {
	cache := &fakeForestCache{pool: []forest.Forest{forestWithLine("cached")}}
	h := newForestTestHandler(nil, 4, 30)
	h.Cache = cache

	if w := getForest(h, "word=patience"); w.Code != http.StatusOK {
		t.Errorf("hit without a key: status %d, want 200", w.Code)
	}
	if w := getForest(h, "word=patience&fresh=1"); w.Code != http.StatusServiceUnavailable {
		t.Errorf("fresh without a key: status %d, want 503", w.Code)
	}
	cache.pool = nil
	if w := getForest(h, "word=patience"); w.Code != http.StatusServiceUnavailable {
		t.Errorf("miss without a key: status %d, want 503", w.Code)
	}
}
