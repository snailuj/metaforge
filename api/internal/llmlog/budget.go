package llmlog

import (
	"context"
	"time"
)

// BudgetWindow is the rolling window the weekly cap covers.
const BudgetWindow = 7 * 24 * time.Hour

type spender interface {
	SpentSince(ctx context.Context, t time.Time) (float64, error)
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
	start := b.now().Add(-BudgetWindow)
	st := BudgetStatus{CapUSD: max(b.capUSD, 0), WindowStart: start.UTC()}
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
