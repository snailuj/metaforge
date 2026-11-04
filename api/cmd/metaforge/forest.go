package main

import (
	"context"
	"log/slog"
	"math"
	"os"
	"slices"
	"strconv"
	"time"

	"github.com/anthropics/anthropic-sdk-go/option"
	"github.com/snailuj/metaforge/internal/forest"
	"github.com/snailuj/metaforge/internal/forestcache"
	"github.com/snailuj/metaforge/internal/handler"
	"github.com/snailuj/metaforge/internal/llm"
	"github.com/snailuj/metaforge/internal/llmlog"
)

const (
	defaultForestModel         = "claude-haiku-5-5"
	defaultForestEffort        = "low" // tuned 2026-10-21: medium was 3-4x slower for no better forests
	defaultForestMinScore      = 6
	defaultForestMinPaths      = 3
	defaultForestMaxConcurrent = 4
	defaultForestPerMinute     = 30
	defaultForestPoolSize      = 10
	// defaultForestPerVisitorHour bounds what one address can spend, so the
	// shared per-minute cap is no longer one stranger's to use up (audit H1,
	// 2026-11-04).
	defaultForestPerVisitorHour = 20
	// forestMaxVisitors bounds the per-visitor table to a few MB; past it,
	// new visitors are refused until idle ones age out.
	forestMaxVisitors = 50_000
	// defaultWeeklyBudgetUSD caps all recorded model spend, live users and
	// enrichment together, over a rolling week (owner, 2026-11-04).
	defaultWeeklyBudgetUSD = 20.0
	// defaultWeeklyCeilingUSD stops all generating, live users included,
	// over the same rolling week: an abuse stop far above normal use
	// (owner, 2026-11-04).
	defaultWeeklyCeilingUSD = 50.0

	// forestWriteTimeout must exceed handler.ForestRequestTimeout so a
	// request that uses its whole deadline can still write its 504.
	forestWriteTimeout = 90 * time.Second
)

var forestEfforts = []string{"low", "medium", "high", "xhigh", "max"}

// forestSettings is the metaphor forest's environment-driven configuration.
type forestSettings struct {
	Config        forest.Config
	MaxConcurrent int
	PerMinute     int
	// PerVisitorHour is how many forests one address may generate an hour.
	PerVisitorHour int
	APIKey         string
	// AnthropicBaseURL is where the API key is sent; empty means the real
	// API. Only the -anthropic-base-url flag sets it.
	AnthropicBaseURL string
	CachePath        string // empty disables the forest cache
	PoolSize         int    // forests kept per (word, max_hops)
	LedgerPath       string // empty: model calls are not recorded and spend is uncapped
	WeeklyCapUSD     float64
	// WeeklyCeilingUSD stops everyone generating; zero switches it off.
	WeeklyCeilingUSD float64
}

func loadForestSettings() forestSettings {
	model := envOrDefault("METAFORGE_FOREST_MODEL", defaultForestModel)
	return forestSettings{
		Config: forest.Config{
			Model:      model,
			JudgeModel: envOrDefault("METAFORGE_FOREST_JUDGE_MODEL", model),
			Effort:     validEffortEnv("METAFORGE_FOREST_EFFORT", defaultForestEffort),
			MinScore:   boundedEnvInt("METAFORGE_FOREST_MIN_SCORE", defaultForestMinScore, 0, 10),
			MinPaths:   boundedEnvInt("METAFORGE_FOREST_MIN_PATHS", defaultForestMinPaths, 0, 24),
		},
		MaxConcurrent:    boundedEnvInt("METAFORGE_FOREST_MAX_CONCURRENT", defaultForestMaxConcurrent, 1, 1<<20),
		PerMinute:        boundedEnvInt("METAFORGE_FOREST_PER_MINUTE", defaultForestPerMinute, 1, 1<<20),
		PerVisitorHour:   boundedEnvInt("METAFORGE_FOREST_PER_VISITOR_HOUR", defaultForestPerVisitorHour, 1, 1<<20),
		APIKey:           os.Getenv("ANTHROPIC_API_KEY"),
		CachePath:        os.Getenv("METAFORGE_FOREST_CACHE"),
		PoolSize:         boundedEnvInt("METAFORGE_FOREST_POOL_SIZE", defaultForestPoolSize, 1, 1000),
		LedgerPath:       os.Getenv("METAFORGE_LLM_LOG"),
		WeeklyCapUSD:     budgetEnv("METAFORGE_WEEKLY_BUDGET_USD", defaultWeeklyBudgetUSD),
		WeeklyCeilingUSD: budgetEnv("METAFORGE_WEEKLY_CEILING_USD", defaultWeeklyCeilingUSD),
	}
}

// budgetEnv reads a non-negative USD amount; zero switches the cap off.
func budgetEnv(key string, fallback float64) float64 {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	f, err := strconv.ParseFloat(v, 64)
	if err != nil || f < 0 || math.IsNaN(f) || math.IsInf(f, 0) {
		slog.Warn("env var is not a USD amount, using default", "key", key, "value", v, "default", fallback)
		return fallback
	}
	return f
}

// validEffortEnv returns the env value if it is a known effort level, else
// the default, with a warning.
func validEffortEnv(key, fallback string) string {
	v := envOrDefault(key, fallback)
	if !slices.Contains(forestEfforts, v) {
		slog.Warn("env var is not a known effort, using default", "key", key, "value", v, "allowed", forestEfforts, "default", fallback)
		return fallback
	}
	return v
}

// boundedEnvInt keeps a value that parses but falls outside [lo, hi] from
// disabling a guard: it logs and returns the default.
func boundedEnvInt(key string, fallback, lo, hi int) int {
	n := envInt(key, fallback)
	if n < lo || n > hi {
		slog.Warn("env var out of range, using default", "key", key, "value", n, "min", lo, "max", hi, "default", fallback)
		return fallback
	}
	return n
}

// newForestHandler builds the route. With no API key the route still exists
// and answers 503, except that a cache keeps serving the forests it holds.
// known says which words may be generated (the lexicon's lemmas).
func newForestHandler(s forestSettings, known func(context.Context, string) (bool, error)) *handler.ForestHandler {
	limiter := forest.NewLimiter(s.MaxConcurrent, s.PerMinute, time.Now)
	ledger, ledgerOK := openLedger(s)
	var h *handler.ForestHandler
	switch {
	case s.APIKey == "":
		slog.Warn("ANTHROPIC_API_KEY is empty: /forge/forest will answer 503 except for cached forests")
		h = handler.NewForestHandler(nil, limiter)
	case !ledgerOK:
		slog.Error("llm call log will not open: /forge/forest serves cached forests only", "path", s.LedgerPath)
		h = handler.NewForestHandler(nil, limiter)
	default:
		baseURL := s.AnthropicBaseURL
		if baseURL == "" {
			baseURL = llm.DefaultBaseURL
		}
		opts := []option.RequestOption{option.WithAPIKey(s.APIKey), option.WithBaseURL(baseURL)}
		if ledger != nil {
			opts = append(opts, option.WithMiddleware(ledger.Middleware()))
		}
		svc := forest.NewService(llm.NewAnthropic(opts...), s.Config)
		h = handler.NewForestHandler(svc, limiter)
	}
	if ledger != nil {
		h.Ledger = ledger
		h.Budget = llmlog.NewBudget(ledger, s.WeeklyCapUSD, time.Now)
		h.Fingerprint = forest.Fingerprint(s.Config)
		slog.Info("model spend capped", "weekly_cap_usd", s.WeeklyCapUSD, "window", llmlog.BudgetWindow.String())
		h.Ceiling = newCeiling(ledger, s)
	}
	h.KnownWord = known
	h.Visitors = forest.NewVisitorLimiter(s.PerVisitorHour, forestMaxVisitors, time.Now)
	slog.Info("forests limited per visitor", "per_hour", s.PerVisitorHour, "max_visitors", forestMaxVisitors)
	if cache := openForestCache(s); cache != nil {
		h.Cache = cache
	}
	return h
}

// newCeiling returns nil, not a zero-cap budget, when the ceiling is off:
// the handler treats an unreadable budget as spent, which must not stop
// generation that no ceiling asked to stop.
func newCeiling(ledger *llmlog.Store, s forestSettings) handler.ForestBudget {
	if s.WeeklyCeilingUSD <= 0 {
		slog.Warn("METAFORGE_WEEKLY_CEILING_USD is 0: live model spend has no ceiling")
		return nil
	}
	if s.WeeklyCapUSD > 0 && s.WeeklyCeilingUSD < s.WeeklyCapUSD {
		slog.Warn("weekly ceiling is below the weekly cap, so it stops live users before enrichment yields",
			"weekly_ceiling_usd", s.WeeklyCeilingUSD, "weekly_cap_usd", s.WeeklyCapUSD)
	}
	slog.Info("all model spend stops at a ceiling", "weekly_ceiling_usd", s.WeeklyCeilingUSD, "window", llmlog.BudgetWindow.String())
	return llmlog.NewBudget(ledger, s.WeeklyCeilingUSD, time.Now)
}

// openLedger returns ok false only when a path is set and will not open:
// generation must then stop, since spend could be neither kept nor capped.
// No path (local development) records nothing and caps nothing.
func openLedger(s forestSettings) (*llmlog.Store, bool) {
	if s.LedgerPath == "" {
		slog.Warn("METAFORGE_LLM_LOG is unset: model calls are not recorded and spend is not capped")
		return nil, true
	}
	store, err := llmlog.Open(s.LedgerPath)
	if err != nil {
		slog.Error("llm call log unavailable", "path", s.LedgerPath, "err", err)
		return nil, false
	}
	return store, true
}

// openForestCache returns nil when no path is set or the file will not
// open; the cache is an optimisation, so its failure is logged, not fatal.
// The store lives for the process, which never shuts down gracefully.
func openForestCache(s forestSettings) *forestcache.Store {
	if s.CachePath == "" {
		slog.Info("METAFORGE_FOREST_CACHE is unset: every forest is generated")
		return nil
	}
	store, err := forestcache.Open(s.CachePath, forest.Fingerprint(s.Config), s.PoolSize)
	if err != nil {
		slog.Error("forest cache unavailable, every forest will be generated", "path", s.CachePath, "err", err)
		return nil
	}
	return store
}

// The live service must satisfy the handler's streaming interface, or
// event-stream requests would silently fall back to JSON.
var _ handler.ForestStreamer = (*forest.Service)(nil)
