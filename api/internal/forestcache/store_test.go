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

// Rule: a pool is one (version, word, max_hops); nothing leaks across.
func TestPoolsAreIsolatedByVersionWordAndHops(t *testing.T) {
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
	if _, ok, _ := other.Random(ctx, "patience", 3); ok {
		t.Error("a new version was served an old version's forest")
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

// Rule: rows from older pipeline versions are kept as a corpus, never
// evicted by another version's pool.
func TestOtherVersionsAreKept(t *testing.T) {
	path := filepath.Join(t.TempDir(), "c.db")
	ctx := context.Background()
	old := openTest(t, path, "v1", 1)
	if err := old.Add(ctx, "patience", 3, sampleForest("old")); err != nil {
		t.Fatalf("Add: %v", err)
	}
	cur := openTest(t, path, "v2", 1)
	for range 3 {
		if err := cur.Add(ctx, "patience", 3, sampleForest("new")); err != nil {
			t.Fatalf("Add: %v", err)
		}
	}
	if n := rows(t, cur, "version = ?", "v1"); n != 1 {
		t.Errorf("%d v1 rows, want the 1 kept", n)
	}
	if n := rows(t, cur, "version = ?", "v2"); n != 1 {
		t.Errorf("%d v2 rows, want a pool of 1", n)
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
