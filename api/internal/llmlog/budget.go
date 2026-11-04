package llmlog

import (
	"context"
	"errors"
	"time"
)

// BudgetWindow is the rolling window the weekly cap covers.
const BudgetWindow = 7 * 24 * time.Hour

// WriteFailureHold is how long a failed call write stops generation. The
// failed call's spend is invisible to the cap; after the hold one more
// attempt is allowed, and a failing write starts the hold again.
const WriteFailureHold = 5 * time.Minute

type spender interface {
	SpentSince(ctx context.Context, t time.Time) (float64, error)
}

// writeHealth is implemented by a ledger that can lose writes.
type writeHealth interface {
	WriteFailedSince(t time.Time) bool
}

// Budget caps all recorded model spend over a rolling week.
type Budget struct {
	spend  spender
	capUSD float64
	now    func() time.Time
}

// NewBudget with capUSD zero or less applies no cap.
func NewBudget(s spender, capUSD float64, now func() time.Time) *Budget {
	return &Budget{spend: s, capUSD: capUSD, now: now}
}

// BudgetStatus is the JSON GET /forge/budget answers with.
type BudgetStatus struct {
	CapUSD       float64   `json:"cap_usd"` // zero: uncapped
	SpentUSD     float64   `json:"spent_usd"`
	RemainingUSD float64   `json:"remaining_usd"`
	WindowStart  time.Time `json:"window_start"`
	Exhausted    bool      `json:"exhausted"`
}

// Status fails closed: when the ledger cannot be read it reports the budget
// exhausted, alongside the error.
func (b *Budget) Status(ctx context.Context) (BudgetStatus, error) {
	now := b.now()
	start := now.Add(-BudgetWindow)
	st := BudgetStatus{CapUSD: max(b.capUSD, 0), WindowStart: start.UTC()}
	if wh, ok := b.spend.(writeHealth); ok && st.CapUSD > 0 && wh.WriteFailedSince(now.Add(-WriteFailureHold)) {
		st.Exhausted = true
		return st, errors.New("a model call could not be recorded in the last few minutes")
	}
	spent, err := b.spend.SpentSince(ctx, start)
	if err != nil {
		st.Exhausted = st.CapUSD > 0
		return st, err
	}
	st.SpentUSD = spent
	if st.CapUSD > 0 {
		st.RemainingUSD = max(st.CapUSD-spent, 0)
		st.Exhausted = spent >= st.CapUSD
	}
	return st, nil
}
