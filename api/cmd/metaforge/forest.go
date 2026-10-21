package main

import (
	"log/slog"
	"os"
	"slices"
	"time"

	"github.com/anthropics/anthropic-sdk-go/option"
	"github.com/snailuj/metaforge/internal/forest"
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
// and answers 503.
func newForestHandler(s forestSettings) *handler.ForestHandler {
	limiter := forest.NewLimiter(s.MaxConcurrent, s.PerMinute, time.Now)
	if s.APIKey == "" {
		slog.Warn("ANTHROPIC_API_KEY is empty: /forge/forest will answer 503")
		return handler.NewForestHandler(nil, limiter)
	}
	svc := forest.NewService(llm.NewAnthropic(option.WithAPIKey(s.APIKey)), s.Config)
	return handler.NewForestHandler(svc, limiter)
}
