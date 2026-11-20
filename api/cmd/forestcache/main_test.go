package main

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/snailuj/metaforge/internal/forest"
	"github.com/snailuj/metaforge/internal/forestcache"
)

// seed writes one forest per word under the given version.
func seed(t *testing.T, path, version string, words ...string) {
	t.Helper()
	s, err := forestcache.Open(path, version, 9)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	for _, w := range words {
		f := forest.Forest{Source: w, MaxHops: 3, Model: "m"}
		if err := s.Add(context.Background(), w, 3, f); err != nil {
			t.Fatal(err)
		}
	}
}

func count(t *testing.T, path string) int {
	t.Helper()
	s, err := forestcache.Open(path, "", 1)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	stats, err := s.Stats(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	n := 0
	for _, v := range stats {
		n += v.Rows
	}
	return n
}

func runArgs(args ...string) (string, error) {
	var out bytes.Buffer
	err := run(args, &out)
	return out.String(), err
}

// Rule: stats lists every version with its row count and date range.
func TestStatsListsEachVersion(t *testing.T) {
	path := filepath.Join(t.TempDir(), "c.db")
	seed(t, path, "fp-one", "patience", "grief")
	seed(t, path, "fp-two", "dread")
	out, err := runArgs("-db", path, "stats")
	if err != nil {
		t.Fatalf("stats: %v", err)
	}
	for _, want := range []string{"fp-one", "fp-two", "2", "1", "rows", "oldest", "newest"} {
		if !strings.Contains(out, want) {
			t.Errorf("stats output lacks %q:\n%s", want, out)
		}
	}
}

// Rule: clear reports how many rows it deleted and deletes only the match.
func TestClearPrintsTheNumberDeleted(t *testing.T) {
	path := filepath.Join(t.TempDir(), "c.db")
	seed(t, path, "fp", "patience", "grief", "dread")
	out, err := runArgs("-db", path, "clear", "-word", "grief")
	if err != nil {
		t.Fatalf("clear: %v", err)
	}
	if !strings.Contains(out, "deleted 1 ") {
		t.Errorf("output %q does not report 1 deleted", out)
	}
	if n := count(t, path); n != 2 {
		t.Errorf("%d rows left, want 2", n)
	}
	out, err = runArgs("-db", path, "clear", "-all")
	if err != nil || !strings.Contains(out, "deleted 2 ") || count(t, path) != 0 {
		t.Errorf("clear -all: out %q err %v, %d left", out, err, count(t, path))
	}
}

// Rule: a clear with no filter, or a bad date, deletes nothing.
func TestClearWithoutFilterErrorsAndDeletesNothing(t *testing.T) {
	path := filepath.Join(t.TempDir(), "c.db")
	seed(t, path, "fp", "patience", "grief")
	for _, args := range [][]string{
		{"-db", path, "clear"},
		{"-db", path, "clear", "-before", "yesterday"},
	} {
		if _, err := runArgs(args...); err == nil {
			t.Errorf("%v: want an error", args)
		}
	}
	if n := count(t, path); n != 2 {
		t.Errorf("%d rows left, want 2 untouched", n)
	}
}

// Rule: a mistyped path is an error, not a new empty cache file.
func TestMissingFileIsNotCreated(t *testing.T) {
	path := filepath.Join(t.TempDir(), "typo.db")
	if _, err := runArgs("-db", path, "stats"); err == nil {
		t.Error("stats on a missing file succeeded")
	}
	if _, err := os.Stat(path); err == nil {
		t.Error("the missing cache file was created")
	}
}

func TestBadInvocationsError(t *testing.T) {
	path := filepath.Join(t.TempDir(), "c.db")
	seed(t, path, "fp", "patience")
	for name, args := range map[string][]string{
		"missing -db":        {"stats"},
		"no subcommand":      {"-db", path},
		"unknown subcommand": {"-db", path, "purge"},
		"unknown clear flag": {"-db", path, "clear", "-nope"},
	} {
		if _, err := runArgs(args...); err == nil {
			t.Errorf("%s: want an error", name)
		}
	}
}
