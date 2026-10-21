package main

import (
	"log/slog"
	"os"
	"slices"
	"time"

	"github.com/anthropics/anthropic-sdk-go/option"
	"github.com/snailuj/metaforge/internal/forest"
	"github.com/snailuj/metaforge/internal/forestcache"
	"github.com/snailuj/metaforge/internal/handler"
	"github.com/snailuj/metaforge/internal/llm"
)

const (
	defaultForestModel         = "claude-haiku-5-5"
	defaultForestEffort        = "low" // tuned 2026-10-21: medium was 3-4x slower for no better forests
	defaultForestMinScore      = 6
	defaultForestMinPaths      = 3
	defaultForestMaxConcurrent = 4
	defaultForestPerMinute     = 30
	defaultForestPoolSize      = 10

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
	APIKey        string
	CachePath     string // empty disables the forest cache
	PoolSize      int    // forests kept per (word, max_hops)
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
		MaxConcurrent: boundedEnvInt("METAFORGE_FOREST_MAX_CONCURRENT", defaultForestMaxConcurrent, 1, 1<<20),
		PerMinute:     boundedEnvInt("METAFORGE_FOREST_PER_MINUTE", defaultForestPerMinute, 1, 1<<20),
		APIKey:        os.Getenv("ANTHROPIC_API_KEY"),
		CachePath:     os.Getenv("METAFORGE_FOREST_CACHE"),
		PoolSize:      boundedEnvInt("METAFORGE_FOREST_POOL_SIZE", defaultForestPoolSize, 1, 1000),
	}
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
func newForestHandler(s forestSettings) *handler.ForestHandler {
	limiter := forest.NewLimiter(s.MaxConcurrent, s.PerMinute, time.Now)
	var h *handler.ForestHandler
	if s.APIKey == "" {
		slog.Warn("ANTHROPIC_API_KEY is empty: /forge/forest will answer 503 except for cached forests")
		h = handler.NewForestHandler(nil, limiter)
	} else {
		svc := forest.NewService(llm.NewAnthropic(option.WithAPIKey(s.APIKey)), s.Config)
		h = handler.NewForestHandler(svc, limiter)
	}
	if cache := openForestCache(s); cache != nil {
		h.Cache = cache
	}
	return h
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
