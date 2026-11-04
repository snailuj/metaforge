// Package enrich grows the metaphor forest cache by asking the Metaforge
// API for new forests, one word at a time, paced so that enrichment never
// spends more than the weekly cap minus a reserve kept for live users.
package enrich

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/snailuj/metaforge/internal/llmlog"
)

var (
	ErrDone        = errors.New("all passes done")
	ErrUncapped    = errors.New("the API reports no weekly cap, so enrichment cannot be paced; set METAFORGE_WEEKLY_BUDGET_USD on the server")
	ErrNoAllowance = errors.New("the reserve leaves no weekly allowance for enrichment")
)

// costSmoothing weights the newest forest cost in the running estimate.
const costSmoothing = 0.2

// API is the slice of the Metaforge API the enricher uses.
type API interface {
	Budget(ctx context.Context) (llmlog.BudgetStatus, error)
	Forest(ctx context.Context, word string, maxHops int) (ForestResult, error)
}

// ForestResult is one /forge/forest answer, reduced to what pacing needs.
type ForestResult struct {
	Status          int
	CostUSD         float64
	CostKnown       bool // false when the server could not price the forest
	BudgetExhausted bool
	RetryAfter      time.Duration
	Endpoints       int
}

type Config struct {
	Words          []string
	MaxHops        int
	Passes         int     // stop after this many passes over Words; 0 runs forever
	ReserveUSD     float64 // left in each week for live users
	InitialCostUSD float64 // cost estimate before the first forest is priced
	MinInterval    time.Duration
	IdleWait       time.Duration // when the allowance is spent
	ErrorWait      time.Duration // after a failure worth retrying
	StatePath      string
}

// State is the progress kept on disk between runs.
type State struct {
	WordsHash       string    `json:"words_hash"`
	Pass            int       `json:"pass"`
	Index           int       `json:"index"`
	Forests         int       `json:"forests"`
	Failed          int       `json:"failed"`
	SpentUSD        float64   `json:"spent_usd"`
	CostEstimateUSD float64   `json:"cost_estimate_usd"`
	LastRequest     time.Time `json:"last_request"`
}

type Enricher struct {
	api   API
	cfg   Config
	now   func() time.Time
	state State
}

// New loads saved progress. A changed word list keeps the totals but
// starts the pass again from its first word.
func New(api API, cfg Config, now func() time.Time) (*Enricher, error) {
	if len(cfg.Words) == 0 {
		return nil, errors.New("no words to enrich")
	}
	e := &Enricher{api: api, cfg: cfg, now: now}
	hash := wordsHash(cfg.Words)
	b, err := os.ReadFile(cfg.StatePath)
	switch {
	case errors.Is(err, os.ErrNotExist):
		e.state = State{WordsHash: hash, CostEstimateUSD: cfg.InitialCostUSD}
		slog.Info("enrich: starting fresh", "words", len(cfg.Words), "state", cfg.StatePath)
	case err != nil:
		return nil, fmt.Errorf("read enrich state %s: %w", cfg.StatePath, err)
	default:
		if err := json.Unmarshal(b, &e.state); err != nil {
			return nil, fmt.Errorf("decode enrich state %s: %w", cfg.StatePath, err)
		}
		if e.state.WordsHash != hash {
			slog.Warn("enrich: word list changed, restarting the pass", "was_index", e.state.Index, "pass", e.state.Pass)
			e.state.WordsHash, e.state.Index = hash, 0
		}
		if e.state.CostEstimateUSD <= 0 {
			e.state.CostEstimateUSD = cfg.InitialCostUSD
		}
		slog.Info("enrich: resuming", "pass", e.state.Pass, "index", e.state.Index, "forests", e.state.Forests,
			"spent_usd", e.state.SpentUSD, "cost_estimate_usd", e.state.CostEstimateUSD)
	}
	return e, nil
}

func (e *Enricher) State() State { return e.state }

// Run steps until the passes are done, ctx ends or a step fails for good.
func (e *Enricher) Run(ctx context.Context) error {
	for {
		wait, err := e.Step(ctx)
		if err != nil {
			return err
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(wait):
		}
	}
}

// Step makes at most one forest request and returns how long to wait
// before the next step. An error ends the run.
func (e *Enricher) Step(ctx context.Context) (time.Duration, error) {
	if e.cfg.Passes > 0 && e.state.Pass >= e.cfg.Passes {
		return 0, ErrDone
	}
	st, err := e.api.Budget(ctx)
	if err != nil {
		slog.Warn("enrich: budget unreadable, backing off", "err", err, "wait", e.cfg.ErrorWait)
		return e.cfg.ErrorWait, nil
	}
	if st.CapUSD <= 0 {
		return 0, ErrUncapped
	}
	allowance := st.CapUSD - e.cfg.ReserveUSD
	if allowance <= 0 {
		return 0, fmt.Errorf("%w: cap %.2f, reserve %.2f", ErrNoAllowance, st.CapUSD, e.cfg.ReserveUSD)
	}
	if st.SpentUSD >= allowance {
		slog.Info("enrich: weekly allowance spent, waiting", "spent_usd", st.SpentUSD, "allowance_usd", allowance, "wait", e.cfg.IdleWait)
		return e.cfg.IdleWait, nil
	}

	interval := max(e.cfg.MinInterval, time.Duration(e.state.CostEstimateUSD/allowance*float64(llmlog.BudgetWindow)))
	if since := e.now().Sub(e.state.LastRequest); since < interval {
		return interval - since, nil
	}

	word := e.cfg.Words[e.state.Index]
	e.state.LastRequest = e.now()
	res, err := e.api.Forest(ctx, word, e.cfg.MaxHops)
	wait, advance := e.judge(word, res, err)
	if advance {
		e.advance()
	}
	if err := e.save(); err != nil {
		return 0, err
	}
	if e.cfg.Passes > 0 && e.state.Pass >= e.cfg.Passes {
		return 0, ErrDone
	}
	return wait, nil
}

// judge reads one forest answer: how long to wait, and whether the word is
// finished with for this pass.
func (e *Enricher) judge(word string, res ForestResult, err error) (time.Duration, bool) {
	switch {
	case err != nil:
		slog.Warn("enrich: forest request failed, retrying the word", "word", word, "err", err)
		return e.cfg.ErrorWait, false
	case res.BudgetExhausted:
		slog.Info("enrich: server says the weekly budget is spent", "word", word, "status", res.Status)
		return e.cfg.IdleWait, false
	case res.Status == 429:
		return max(res.RetryAfter, e.cfg.MinInterval), false
	case res.Status == 200:
		e.state.Forests++
		e.state.SpentUSD += res.CostUSD
		if res.CostKnown {
			e.state.CostEstimateUSD = (1-costSmoothing)*e.state.CostEstimateUSD + costSmoothing*res.CostUSD
		} else {
			slog.Warn("enrich: forest cost unknown, estimate kept", "word", word)
		}
		slog.Info("enrich: forest grown", "word", word, "pass", e.state.Pass, "index", e.state.Index,
			"endpoints", res.Endpoints, "cost_usd", res.CostUSD, "cost_estimate_usd", e.state.CostEstimateUSD,
			"forests", e.state.Forests, "spent_usd", e.state.SpentUSD)
		return 0, true
	case res.Status == 503:
		slog.Warn("enrich: forest route unavailable, waiting", "word", word)
		return e.cfg.IdleWait, false
	default:
		// A bad word or a failed generation: moving on keeps one word from
		// spending the week. The next pass tries it again.
		e.state.Failed++
		slog.Warn("enrich: forest not grown, moving on", "word", word, "status", res.Status)
		return 0, true
	}
}

func (e *Enricher) advance() {
	e.state.Index++
	if e.state.Index >= len(e.cfg.Words) {
		e.state.Index = 0
		e.state.Pass++
		slog.Info("enrich: pass complete", "pass", e.state.Pass, "forests", e.state.Forests, "spent_usd", e.state.SpentUSD)
	}
}

// save writes the state atomically, so a crash never leaves half a file.
// A crash between a forest and this save repeats that word on restart, so
// resumption costs at most one extra forest.
func (e *Enricher) save() error {
	b, err := json.MarshalIndent(e.state, "", "  ")
	if err != nil {
		return fmt.Errorf("encode enrich state: %w", err)
	}
	tmp, err := os.CreateTemp(filepath.Dir(e.cfg.StatePath), ".enrich-state-*")
	if err != nil {
		return fmt.Errorf("write enrich state: %w", err)
	}
	defer os.Remove(tmp.Name()) // no-op after the rename
	if _, err := tmp.Write(b); err != nil {
		tmp.Close()
		return fmt.Errorf("write enrich state: %w", err)
	}
	// Without a sync, a power cut can put the rename on disk before the
	// data and leave an empty state file.
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return fmt.Errorf("sync enrich state: %w", err)
	}
	if err := tmp.Close(); err != nil {
		return fmt.Errorf("write enrich state: %w", err)
	}
	if err := os.Rename(tmp.Name(), e.cfg.StatePath); err != nil {
		return fmt.Errorf("write enrich state: %w", err)
	}
	return nil
}

func wordsHash(words []string) string {
	h := sha256.Sum256([]byte(strings.Join(words, "\n")))
	return hex.EncodeToString(h[:8])
}
