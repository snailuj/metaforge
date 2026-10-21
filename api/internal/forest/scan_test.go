package forest

import (
	"encoding/json"
	"fmt"
	"reflect"
	"strings"
	"testing"
)

const scanDoc = `{"facets": [
  {"word": "dormant {seed}", "ground": "waits \"intact\" ]", "line": "", "branches": [
    {"hops": [{"word": "seed vault", "ground": "stays viable"}], "line": "x"},
    {"hops": [], "line": "y\\"}
  ]},
  {"word": "glacier", "ground": "moves é slowly", "line": "z", "branches": []}
], "n": -1.5e3, "t": true, "f": false, "z": null}`

type scanned struct {
	Path string
	Raw  string
}

func collect(chunks []string) ([]scanned, error) {
	var s Scanner
	var out []scanned
	for _, c := range chunks {
		evs, err := s.Feed(c)
		if err != nil {
			return out, err
		}
		for _, e := range evs {
			out = append(out, scanned{e.PathString(), string(e.Raw)})
		}
	}
	return out, nil
}

// Rule: the scanner reports every value of the document exactly once, with its
// path and exact raw text, however the stream is split into chunks.
func TestScannerSplitAnywhereGivesSameValues(t *testing.T) {
	whole, err := collect([]string{scanDoc})
	if err != nil {
		t.Fatal(err)
	}
	// Baseline is real: the scanner saw the deep hop and every scalar kind.
	want := map[string]string{
		"facets/0/branches/0/hops/0": `{"word": "seed vault", "ground": "stays viable"}`,
		"facets/0/word":              `"dormant {seed}"`,
		"facets/0/ground":            `"waits \"intact\" ]"`,
		"facets/0/branches/1/line":   `"y\\"`,
		"facets/1/ground":            `"moves é slowly"`,
		"n":                          `-1.5e3`,
		"t":                          `true`,
		"z":                          `null`,
	}
	got := map[string]string{}
	for _, v := range whole {
		got[v.Path] = v.Raw
	}
	for p, raw := range want {
		if got[p] != raw {
			t.Errorf("path %s: got %q, want %q", p, got[p], raw)
		}
	}
	if got[""] != scanDoc {
		t.Errorf("root value not reported whole")
	}
	for _, v := range whole {
		if !json.Valid([]byte(v.Raw)) {
			t.Errorf("path %s: raw %q is not valid JSON", v.Path, v.Raw)
		}
	}

	for i := 1; i < len(scanDoc); i++ {
		split, err := collect([]string{scanDoc[:i], scanDoc[i:]})
		if err != nil {
			t.Fatalf("split at %d: %v", i, err)
		}
		if !reflect.DeepEqual(split, whole) {
			t.Fatalf("split at %d: values differ", i)
		}
	}
	bytes := strings.Split(scanDoc, "")
	byByte, err := collect(bytes)
	if err != nil || !reflect.DeepEqual(byByte, whole) {
		t.Fatalf("byte-by-byte feed differs: %v", err)
	}
}

// Rule: a value is reported as soon as its last byte arrives, before anything
// after it, so a consumer can act on a hop while the facet is still streaming.
func TestScannerReportsValuesInCompletionOrder(t *testing.T) {
	var s Scanner
	evs, err := s.Feed(`{"facets": [{"word": "a", "ground": "b", "branches": [{"hops": [{"word": "c", "ground": "d"}`)
	if err != nil {
		t.Fatal(err)
	}
	var paths []string
	for _, e := range evs {
		paths = append(paths, e.PathString())
	}
	want := []string{
		"facets/0/word", "facets/0/ground",
		"facets/0/branches/0/hops/0/word", "facets/0/branches/0/hops/0/ground",
		"facets/0/branches/0/hops/0",
	}
	if !reflect.DeepEqual(paths, want) {
		t.Fatalf("got %v, want %v", paths, want)
	}
}

func TestScannerRejectsMalformedInput(t *testing.T) {
	for _, doc := range []string{`{"a": 1]`, `[1, }`, `{"a" 1}`, `}`, `{"a": tru e}`} {
		var s Scanner
		if _, err := s.Feed(doc); err == nil {
			t.Errorf("%s: want error", doc)
		}
	}
}

func ExampleScanner() {
	var s Scanner
	evs, _ := s.Feed(`{"facets": [{"word": "seed"}]}`)
	for _, e := range evs {
		fmt.Println(e.PathString(), string(e.Raw))
	}
	// Output:
	// facets/0/word "seed"
	// facets/0 {"word": "seed"}
	// facets [{"word": "seed"}]
	//  {"facets": [{"word": "seed"}]}
}
