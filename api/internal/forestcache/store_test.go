package forestcache

import (
	"context"
	"fmt"
	"path/filepath"
	"reflect"
	"sync"
	"testing"

	"github.com/snailuj/metaforge/internal/forest"
)

func sampleForest(line string) forest.Forest {
	return forest.Forest{
		Source: "patience", MaxHops: 3, Model: "claude-haiku-5-5",
		Nodes: []forest.Node{
			{ID: "patience", Word: "patience", Role: forest.RoleSource},
			{ID: "seed vault", Word: "seed vault", Role: forest.RoleEndpoint},
		},
		Edges: []forest.Edge{{Source: "patience", Target: "seed vault", Grounds: []string{"keeps"}}},
		Endpoints: []forest.Endpoint{{
			ID: "seed vault", Path: []string{"patience", "seed vault"}, Grounds: []string{"keeps"},
			Line: line, Score: 7, Reason: "cold",
		}},
		Stats: forest.Stats{Generated: 3, Kept: 1, Rejected: forest.Rejected{LowScore: 2}},
	}
}

func openTest(t *testing.T, path, version string, poolSize int) *Store {
	t.Helper()
	s, err := Open(path, version, poolSize)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	t.Cleanup(func() { _ = s.Close() })
	return s
}

func rows(t *testing.T, s *Store, where string, args ...any) int {
	t.Helper()
	var n int
	if err := s.db.QueryRow("SELECT COUNT(*) FROM forests WHERE "+where, args...).Scan(&n); err != nil {
		t.Fatalf("count: %v", err)
	}
	return n
}

func TestRandomOnEmptyPoolMisses(t *testing.T) {
	s := openTest(t, filepath.Join(t.TempDir(), "c.db"), "v1", 4)
	_, ok, err := s.Random(context.Background(), "patience", 3)
	if err != nil || ok {
		t.Errorf("ok=%v err=%v, want a clean miss", ok, err)
	}
}

func TestAddThenRandomRoundTrips(t *testing.T) {
	s := openTest(t, filepath.Join(t.TempDir(), "c.db"), "v1", 4)
	want := sampleForest("Patience is a seed vault.")
	if err := s.Add(context.Background(), "patience", 3, want); err != nil {
		t.Fatalf("Add: %v", err)
	}
	got, ok, err := s.Random(context.Background(), "patience", 3)
	if err != nil || !ok || !reflect.DeepEqual(got, want) {
		t.Errorf("Random = %+v ok=%v err=%v, want %+v", got, ok, err, want)
	}
}

// Rule: a pool is (word, max_hops); the version a forest was written under
// never decides whether it is served.
func TestPoolsAreIsolatedByWordAndHopsNotVersion(t *testing.T) {
	path := filepath.Join(t.TempDir(), "c.db")
	s := openTest(t, path, "v1", 4)
	ctx := context.Background()
	if err := s.Add(ctx, "patience", 3, sampleForest("L")); err != nil {
		t.Fatalf("Add: %v", err)
	}
	for _, miss := range []struct {
		word string
		hops int
	}{{"grief", 3}, {"patience", 2}} {
		if _, ok, _ := s.Random(ctx, miss.word, miss.hops); ok {
			t.Errorf("%s/%d hit another pool", miss.word, miss.hops)
		}
	}
	other := openTest(t, path, "v2", 4)
	if _, ok, err := other.Random(ctx, "patience", 3); !ok || err != nil {
		t.Errorf("Random ok=%v err=%v, want the v1 forest served to v2", ok, err)
	}
	if got, err := other.List(ctx, "patience", 3); err != nil || len(got) != 1 {
		t.Errorf("List = %d forests, err %v; want the v1 forest", len(got), err)
	}
	if full, err := other.Full(ctx, "patience", 3); err != nil || full {
		t.Errorf("Full = %v, %v; want a pool of 1 of 4 not full", full, err)
	}
}

// Rule: a pool holds at most poolSize forests; adding past it drops the
// oldest.
func TestAddEvictsOldestBeyondPoolSize(t *testing.T) {
	s := openTest(t, filepath.Join(t.TempDir(), "c.db"), "v1", 3)
	ctx := context.Background()
	for i := range 5 {
		if err := s.Add(ctx, "patience", 3, sampleForest(fmt.Sprintf("L%d", i))); err != nil {
			t.Fatalf("Add %d: %v", i, err)
		}
	}
	if n := rows(t, s, "word = ?", "patience"); n != 3 {
		t.Fatalf("%d forests in the pool, want 3", n)
	}
	for range 30 {
		f, _, _ := s.Random(ctx, "patience", 3)
		if line := f.Endpoints[0].Line; line == "L0" || line == "L1" {
			t.Fatalf("served evicted forest %s", line)
		}
	}
}

// Rule: the pool size bounds the whole pool across versions, so adding under
// a new version evicts the oldest row even when it was written under an old one.
func TestAddEvictsOldestAcrossVersions(t *testing.T) {
	path := filepath.Join(t.TempDir(), "c.db")
	ctx := context.Background()
	old := openTest(t, path, "v1", 2)
	if err := old.Add(ctx, "patience", 3, sampleForest("old")); err != nil {
		t.Fatalf("Add: %v", err)
	}
	cur := openTest(t, path, "v2", 2)
	for _, line := range []string{"new1", "new2"} {
		if err := cur.Add(ctx, "patience", 3, sampleForest(line)); err != nil {
			t.Fatalf("Add: %v", err)
		}
	}
	if n := rows(t, cur, "version = ?", "v1"); n != 0 {
		t.Errorf("%d v1 rows, want the oldest evicted", n)
	}
	if n := rows(t, cur, "version = ?", "v2"); n != 2 {
		t.Errorf("%d v2 rows, want a pool of 2", n)
	}
}

// Rule: every row records the version it was written under.
func TestAddRecordsTheStoreVersion(t *testing.T) {
	s := openTest(t, filepath.Join(t.TempDir(), "c.db"), "v7", 2)
	if err := s.Add(context.Background(), "patience", 3, sampleForest("L")); err != nil {
		t.Fatalf("Add: %v", err)
	}
	if n := rows(t, s, "version = ?", "v7"); n != 1 {
		t.Errorf("%d rows under v7, want 1", n)
	}
}

// Rule: a store opened without a version is for reading and admin only.
func TestAddWithoutVersionIsRefused(t *testing.T) {
	s := openTest(t, filepath.Join(t.TempDir(), "c.db"), "", 2)
	if err := s.Add(context.Background(), "patience", 3, sampleForest("L")); err == nil {
		t.Error("Add succeeded on a store with no version")
	}
	if n := rows(t, s, "1 = 1"); n != 0 {
		t.Errorf("%d rows written, want none", n)
	}
}

func TestForestsSurviveReopen(t *testing.T) {
	path := filepath.Join(t.TempDir(), "c.db")
	s, err := Open(path, "v1", 4)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	if err := s.Add(context.Background(), "patience", 3, sampleForest("L")); err != nil {
		t.Fatalf("Add: %v", err)
	}
	if err := s.Close(); err != nil {
		t.Fatalf("Close: %v", err)
	}
	again := openTest(t, path, "v1", 4)
	if _, ok, err := again.Random(context.Background(), "patience", 3); !ok || err != nil {
		t.Errorf("ok=%v err=%v after reopen, want a hit", ok, err)
	}
}

// Rule: concurrent requests may add to one pool at once.
func TestConcurrentAdds(t *testing.T) {
	s := openTest(t, filepath.Join(t.TempDir(), "c.db"), "v1", 4)
	var wg sync.WaitGroup
	errs := make(chan error, 12)
	for i := range 12 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			errs <- s.Add(context.Background(), "patience", 3, sampleForest(fmt.Sprint(i)))
		}()
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		if err != nil {
			t.Fatalf("Add: %v", err)
		}
	}
	if n := rows(t, s, "word = ?", "patience"); n != 4 {
		t.Errorf("%d forests, want a full pool of 4", n)
	}
}

func TestOpenRejectsNonPositivePoolSize(t *testing.T) {
	if _, err := Open(filepath.Join(t.TempDir(), "c.db"), "v1", 0); err == nil {
		t.Error("pool size 0 was accepted")
	}
}

// Rule: a pool is full once it holds poolSize forests of this word and
// max_hops; enrichment skips full pools.
func TestFullReportsAPoolAtPoolSize(t *testing.T) {
	ctx := context.Background()
	s := openTest(t, filepath.Join(t.TempDir(), "c.db"), "v1", 2)
	check := func(word string, hops int, want bool) {
		t.Helper()
		if full, err := s.Full(ctx, word, hops); err != nil || full != want {
			t.Fatalf("Full(%q, %d) = %v, %v; want %v", word, hops, full, err, want)
		}
	}
	check("patience", 3, false)
	if err := s.Add(ctx, "patience", 3, sampleForest("one")); err != nil {
		t.Fatal(err)
	}
	check("patience", 3, false)
	if err := s.Add(ctx, "patience", 3, sampleForest("two")); err != nil {
		t.Fatal(err)
	}
	check("patience", 3, true)
	check("patience", 2, false)
	check("dread", 3, false)
}

// Rule: List returns the pool for the word and hops, newest first, never more
// than poolSize.
func TestListReturnsThePoolNewestFirst(t *testing.T) {
	ctx := context.Background()
	path := filepath.Join(t.TempDir(), "c.db")
	s := openTest(t, path, "v1", 2)
	if got, err := s.List(ctx, "patience", 3); err != nil || len(got) != 0 {
		t.Fatalf("empty pool: got %d forests, err %v; want none", len(got), err)
	}
	for _, line := range []string{"first", "second", "third"} {
		if err := s.Add(ctx, "patience", 3, sampleForest(line)); err != nil {
			t.Fatal(err)
		}
	}
	if err := s.Add(ctx, "patience", 2, sampleForest("other hops")); err != nil {
		t.Fatal(err)
	}
	if err := s.Add(ctx, "time", 3, sampleForest("other word")); err != nil {
		t.Fatal(err)
	}

	got, err := s.List(ctx, "patience", 3)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	var lines []string
	for _, f := range got {
		lines = append(lines, f.Endpoints[0].Line)
	}
	if want := []string{"third", "second"}; !reflect.DeepEqual(lines, want) {
		t.Errorf("lines = %v, want %v", lines, want)
	}
	if !reflect.DeepEqual(got[0], sampleForest("third")) {
		t.Errorf("listed forest does not round-trip: %+v", got[0])
	}
}

func setCreatedAt(t *testing.T, s *Store, line, createdAt string) {
	t.Helper()
	res, err := s.db.Exec(`UPDATE forests SET created_at = ? WHERE body LIKE ?`, createdAt, `%"line":"`+line+`"%`)
	if err != nil {
		t.Fatalf("set created_at: %v", err)
	}
	if n, _ := res.RowsAffected(); n != 1 {
		t.Fatalf("set created_at for %q touched %d rows, want 1", line, n)
	}
}

// Rule: Stats reports each version's row count and created_at range, oldest
// version first.
func TestStatsGroupsByVersionOldestFirst(t *testing.T) {
	ctx := context.Background()
	path := filepath.Join(t.TempDir(), "c.db")
	a := openTest(t, path, "vA", 9)
	b := openTest(t, path, "vB", 9)
	for _, add := range []struct {
		s    *Store
		word string
		line string
	}{{b, "grief", "b1"}, {a, "patience", "a1"}, {a, "patience", "a2"}} {
		if err := add.s.Add(ctx, add.word, 3, sampleForest(add.line)); err != nil {
			t.Fatal(err)
		}
	}
	setCreatedAt(t, a, "a1", "2026-10-20T08:00:00Z")
	setCreatedAt(t, a, "a2", "2026-10-21T08:00:00Z")
	setCreatedAt(t, b, "b1", "2026-10-19T08:00:00Z")

	got, err := a.Stats(ctx)
	if err != nil {
		t.Fatalf("Stats: %v", err)
	}
	want := []VersionStats{
		{Version: "vB", Rows: 1, Oldest: "2026-10-19T08:00:00Z", Newest: "2026-10-19T08:00:00Z"},
		{Version: "vA", Rows: 2, Oldest: "2026-10-20T08:00:00Z", Newest: "2026-10-21T08:00:00Z"},
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("Stats = %+v, want %+v", got, want)
	}
}

func TestStatsOnEmptyCacheIsEmpty(t *testing.T) {
	s := openTest(t, filepath.Join(t.TempDir(), "c.db"), "", 1)
	if got, err := s.Stats(context.Background()); err != nil || len(got) != 0 {
		t.Errorf("Stats = %+v, %v; want none", got, err)
	}
}

// seedClear fills a cache with four forests that differ by word and age.
func seedClear(t *testing.T) *Store {
	t.Helper()
	ctx := context.Background()
	s := openTest(t, filepath.Join(t.TempDir(), "c.db"), "v1", 9)
	for _, row := range []struct{ word, line, at string }{
		{"patience", "old-patience", "2026-10-21T23:59:59Z"},
		{"patience", "new-patience", "2026-10-22T00:00:00Z"},
		{"grief", "old-grief", "2026-10-01T00:00:00Z"},
		{"grief", "new-grief", "2026-11-01T00:00:00Z"},
	} {
		if err := s.Add(ctx, row.word, 3, sampleForest(row.line)); err != nil {
			t.Fatal(err)
		}
		setCreatedAt(t, s, row.line, row.at)
	}
	return s
}

// Rule: Before is a UTC calendar date; a row stamped before midnight starting
// that date is cleared, one stamped at or after it is kept.
func TestClearBeforeIsExclusiveAtUTCMidnight(t *testing.T) {
	ctx := context.Background()
	s := seedClear(t)
	n, err := s.Clear(ctx, ClearFilter{Before: "2026-10-22"})
	if err != nil || n != 2 {
		t.Fatalf("Clear = %d, %v; want 2 rows (old-patience, old-grief)", n, err)
	}
	if c := rows(t, s, `body LIKE '%"line":"old-patience"%'`); c != 0 {
		t.Error("the 23:59:59Z row was kept")
	}
	if c := rows(t, s, `body LIKE '%"line":"new-patience"%'`); c != 1 {
		t.Error("the 00:00:00Z row was cleared")
	}
}

// Rule: filters combine with AND; All clears every row.
func TestClearCombinesFiltersWithAnd(t *testing.T) {
	ctx := context.Background()
	s := seedClear(t)
	if n, err := s.Clear(ctx, ClearFilter{Word: "patience", Before: "2026-10-22"}); err != nil || n != 1 {
		t.Fatalf("word+before Clear = %d, %v; want 1", n, err)
	}
	if n, err := s.Clear(ctx, ClearFilter{Word: "grief"}); err != nil || n != 2 {
		t.Fatalf("word Clear = %d, %v; want 2", n, err)
	}
	if n, err := s.Clear(ctx, ClearFilter{All: true}); err != nil || n != 1 {
		t.Fatalf("all Clear = %d, %v; want the last 1", n, err)
	}
	if c := rows(t, s, "1 = 1"); c != 0 {
		t.Errorf("%d rows left after Clear All", c)
	}
}

// Rule: a clear without any filter deletes nothing, and a malformed date
// deletes nothing.
func TestClearRefusesNoFilterAndBadDate(t *testing.T) {
	ctx := context.Background()
	s := seedClear(t)
	for name, f := range map[string]ClearFilter{
		"no filter":    {},
		"bad date":     {Before: "22/10/2026"},
		"timestamp":    {Before: "2026-10-22T00:00:00Z"},
		"word and bad": {Word: "patience", Before: "soon"},
	} {
		if n, err := s.Clear(ctx, f); err == nil || n != 0 {
			t.Errorf("%s: Clear = %d, %v; want an error and 0", name, n, err)
		}
	}
	if c := rows(t, s, "1 = 1"); c != 4 {
		t.Errorf("%d rows left, want all 4 untouched", c)
	}
}

// Rule: clearing is idempotent; repeating it deletes nothing more.
func TestClearTwiceDeletesNothingSecondTime(t *testing.T) {
	ctx := context.Background()
	s := seedClear(t)
	f := ClearFilter{Word: "grief"}
	if n, err := s.Clear(ctx, f); err != nil || n != 2 {
		t.Fatalf("first Clear = %d, %v; want 2", n, err)
	}
	if n, err := s.Clear(ctx, f); err != nil || n != 0 {
		t.Errorf("second Clear = %d, %v; want 0", n, err)
	}
}
