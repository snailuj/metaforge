package llmlog

import (
	"context"
	"errors"
	"testing"
	"time"
)

type fakeSpend struct {
	usd   float64
	err   error
	since time.Time
}

func (f *fakeSpend) SpentSince(_ context.Context, t time.Time) (float64, error) {
	f.since = t
	return f.usd, f.err
}

func TestBudgetStatusOverRollingWeek(t *testing.T) {
	now := time.Date(2026, 11, 4, 12, 0, 0, 0, time.UTC)
	sp := &fakeSpend{usd: 12.5}
	b := NewBudget(sp, 20, func() time.Time { return now })
	st, err := b.Status(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if !sp.since.Equal(now.Add(-7 * 24 * time.Hour)) {
		t.Errorf("window starts %v", sp.since)
	}
	if st.CapUSD != 20 || st.SpentUSD != 12.5 || st.RemainingUSD != 7.5 || st.Exhausted {
		t.Errorf("status %+v", st)
	}
}

func TestBudgetExhaustedAtCap(t *testing.T) {
	b := NewBudget(&fakeSpend{usd: 20}, 20, time.Now)
	st, _ := b.Status(context.Background())
	if !st.Exhausted || st.RemainingUSD != 0 {
		t.Errorf("status %+v, want exhausted", st)
	}
}

func TestBudgetZeroCapIsUncapped(t *testing.T) {
	b := NewBudget(&fakeSpend{usd: 1e6}, 0, time.Now)
	st, _ := b.Status(context.Background())
	if st.Exhausted {
		t.Errorf("a zero cap must not stop spending: %+v", st)
	}
}

// A ledger that cannot be read cannot prove there is money left.
func TestBudgetFailsClosed(t *testing.T) {
	b := NewBudget(&fakeSpend{err: errors.New("disk")}, 20, time.Now)
	st, err := b.Status(context.Background())
	if err == nil || !st.Exhausted {
		t.Errorf("status %+v err %v, want exhausted with error", st, err)
	}
}
