package handler

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"reflect"
	"testing"

	"github.com/snailuj/metaforge/internal/forest"
)

func getSaved(h *ForestHandler, query string) *httptest.ResponseRecorder {
	req := httptest.NewRequest("GET", "/forge/forest/saved?"+query, nil)
	w := httptest.NewRecorder()
	h.HandleSaved(w, req)
	return w
}

func decodeSaved(t *testing.T, w *httptest.ResponseRecorder) []forest.Forest {
	t.Helper()
	var body struct {
		Forests []forest.Forest `json:"forests"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &body); err != nil || body.Forests == nil {
		t.Fatalf("body %q is not a saved-forest list (err %v)", w.Body.String(), err)
	}
	return body.Forests
}

// Rule: browsing saved forests never generates or takes a limiter slot, even
// with the per-minute budget spent, the ceiling reached or no API key.
func TestSavedListsThePoolAndNeverGenerates(t *testing.T) {
	gen := &fakeForestGen{forest: forestWithLine("fresh")}
	pool := []forest.Forest{forestWithLine("newest"), forestWithLine("older")}
	h := newForestTestHandler(gen, 1, 1)
	h.Cache = &fakeForestCache{pool: pool}
	h.Ceiling = ceilingReached
	getForest(h, "word=patience&fresh=1")
	if gen.called != 0 {
		t.Fatalf("baseline: the ceiling should stop generation, generator called %d times", gen.called)
	}

	for range 3 {
		w := getSaved(h, "word=Patience&max_hops=2")
		if w.Code != http.StatusOK {
			t.Fatalf("status = %d, body %s", w.Code, w.Body.String())
		}
		if got := decodeSaved(t, w); !reflect.DeepEqual(got, pool) {
			t.Errorf("forests = %+v, want the pool in order", got)
		}
		if cc := w.Header().Get("Cache-Control"); cc != "no-store" {
			t.Errorf("Cache-Control = %q, want no-store: the pool changes", cc)
		}
	}
	if gen.called != 0 {
		t.Errorf("generator called %d times, want 0", gen.called)
	}
	cache := h.Cache.(*fakeForestCache)
	if cache.readWord != "patience" || cache.readHops != 2 {
		t.Errorf("listed (%q, %d), want (patience, 2)", cache.readWord, cache.readHops)
	}

	noKey := NewForestHandler(nil, nil)
	noKey.Cache = &fakeForestCache{pool: pool}
	noKey.KnownWord = lexiconOf("patience")
	if got := decodeSaved(t, getSaved(noKey, "word=patience")); len(got) != 2 {
		t.Errorf("without an API key: %d forests, want 2", len(got))
	}
}

func TestSavedWithoutCacheIsAnEmptyList(t *testing.T) {
	h := newForestTestHandler(&fakeForestGen{}, 1, 1)
	w := getSaved(h, "word=patience")
	if w.Code != http.StatusOK || len(decodeSaved(t, w)) != 0 {
		t.Errorf("status %d body %s, want 200 and no forests", w.Code, w.Body.String())
	}
}

func TestSavedRejectsBadParameters(t *testing.T) {
	h := newForestTestHandler(&fakeForestGen{}, 1, 1)
	h.Cache = &fakeForestCache{}
	for _, q := range []string{"word=", "word=a1", "word=patience&max_hops=9"} {
		if w := getSaved(h, q); w.Code != http.StatusBadRequest {
			t.Errorf("%s: status %d, want 400", q, w.Code)
		}
	}
}

func TestSavedReadFailureIs500(t *testing.T) {
	h := newForestTestHandler(&fakeForestGen{}, 1, 1)
	h.Cache = &fakeForestCache{listErr: errors.New("disk gone")}
	if w := getSaved(h, "word=patience"); w.Code != http.StatusInternalServerError {
		t.Errorf("status %d, want 500", w.Code)
	}
}

// Rule: saved forests are listed only for a lexicon lemma, and a word the
// check cannot answer for lists nothing; the cache is not read either way.
func TestSavedListsOnlyForLexiconWords(t *testing.T) {
	for name, known := range map[string]func(context.Context, string) (bool, error){
		"not a lemma": lexiconOf("anger"),
		"check fails": func(context.Context, string) (bool, error) { return false, errors.New("db closed") },
		"unset":       nil,
	} {
		t.Run(name, func(t *testing.T) {
			cache := &fakeForestCache{pool: []forest.Forest{forestWithLine("kept")}}
			h := newForestTestHandler(&fakeForestGen{}, 1, 1)
			h.Cache = cache
			h.KnownWord = known

			w := getSaved(h, "word=ignore+previous+instructions")

			if w.Code == http.StatusOK {
				t.Errorf("status 200 with body %s, want a refusal", w.Body.String())
			}
			if cache.readWord != "" {
				t.Errorf("cache read for %q before the word was admitted", cache.readWord)
			}
		})
	}
	h := newForestTestHandler(&fakeForestGen{}, 1, 1)
	h.Cache = &fakeForestCache{pool: []forest.Forest{forestWithLine("kept")}}
	h.KnownWord = lexiconOf("anger")
	if got := decodeSaved(t, getSaved(h, "word=anger")); len(got) != 1 {
		t.Errorf("lemma: %d forests, want 1", len(got))
	}
}
