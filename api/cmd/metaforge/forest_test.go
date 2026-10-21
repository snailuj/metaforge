package main

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/snailuj/metaforge/internal/forest"
	"github.com/snailuj/metaforge/internal/handler"
)

var forestEnvVars = []string{
	"ANTHROPIC_API_KEY", "METAFORGE_FOREST_MODEL", "METAFORGE_FOREST_JUDGE_MODEL",
	"METAFORGE_FOREST_EFFORT", "METAFORGE_FOREST_MIN_SCORE", "METAFORGE_FOREST_MIN_PATHS",
	"METAFORGE_FOREST_MAX_CONCURRENT", "METAFORGE_FOREST_PER_MINUTE",
	"METAFORGE_FOREST_CACHE", "METAFORGE_FOREST_POOL_SIZE",
}

// clearForestEnv blanks every variable so no test depends on the ambient
// environment.
func clearForestEnv(t *testing.T) {
	t.Helper()
	for _, k := range forestEnvVars {
		t.Setenv(k, "")
	}
}

func TestLoadForestSettingsDefaults(t *testing.T) {
	clearForestEnv(t)

	s := loadForestSettings()

	want := forestSettings{
		Config:        forest.Config{Model: "claude-haiku-5-5", JudgeModel: "claude-haiku-5-5", Effort: "low", MinScore: 6, MinPaths: 3},
		MaxConcurrent: 4,
		PerMinute:     30,
		PoolSize:      10,
	}
	if s != want {
		t.Errorf("settings = %+v, want %+v", s, want)
	}
}

func TestLoadForestSettingsFromEnv(t *testing.T) {
	clearForestEnv(t)
	t.Setenv("ANTHROPIC_API_KEY", "sk-test")
	t.Setenv("METAFORGE_FOREST_MODEL", "gen-x")
	t.Setenv("METAFORGE_FOREST_JUDGE_MODEL", "judge-y")
	t.Setenv("METAFORGE_FOREST_EFFORT", "high")
	t.Setenv("METAFORGE_FOREST_MIN_SCORE", "7")
	t.Setenv("METAFORGE_FOREST_MIN_PATHS", "0")
	t.Setenv("METAFORGE_FOREST_MAX_CONCURRENT", "2")
	t.Setenv("METAFORGE_FOREST_PER_MINUTE", "10")
	t.Setenv("METAFORGE_FOREST_CACHE", "/var/lib/forest.db")
	t.Setenv("METAFORGE_FOREST_POOL_SIZE", "5")

	s := loadForestSettings()

	want := forestSettings{
		Config:        forest.Config{Model: "gen-x", JudgeModel: "judge-y", Effort: "high", MinScore: 7, MinPaths: 0},
		MaxConcurrent: 2,
		PerMinute:     10,
		APIKey:        "sk-test",
		CachePath:     "/var/lib/forest.db",
		PoolSize:      5,
	}
	if s != want {
		t.Errorf("settings = %+v, want %+v", s, want)
	}
}

// Rule: the judge follows the generator model unless told otherwise.
func TestLoadForestSettingsJudgeFollowsModel(t *testing.T) {
	clearForestEnv(t)
	t.Setenv("METAFORGE_FOREST_MODEL", "gen-x")

	if s := loadForestSettings(); s.Config.JudgeModel != "gen-x" {
		t.Errorf("judge model = %q, want gen-x", s.Config.JudgeModel)
	}
}

// Rule: a malformed or out-of-range number never disables the spend guard
// or the quality gate; it falls back to the default.
func TestLoadForestSettingsRejectsBadNumbers(t *testing.T) {
	for _, bad := range []string{"abc", "0", "-3", "2.5"} {
		clearForestEnv(t)
		t.Setenv("METAFORGE_FOREST_MAX_CONCURRENT", bad)
		t.Setenv("METAFORGE_FOREST_PER_MINUTE", bad)
		if s := loadForestSettings(); s.MaxConcurrent != 4 || s.PerMinute != 30 {
			t.Errorf("%q: caps = %d/%d, want defaults 4/30", bad, s.MaxConcurrent, s.PerMinute)
		}
	}
	for _, bad := range []string{"abc", "-1", "11"} {
		clearForestEnv(t)
		t.Setenv("METAFORGE_FOREST_MIN_SCORE", bad)
		if s := loadForestSettings(); s.Config.MinScore != 6 {
			t.Errorf("%q: min score = %d, want default 6", bad, s.Config.MinScore)
		}
	}
	clearForestEnv(t)
	t.Setenv("METAFORGE_FOREST_MIN_SCORE", "0")
	if s := loadForestSettings(); s.Config.MinScore != 0 {
		t.Errorf("min score 0 is valid, got %d", s.Config.MinScore)
	}
}

// Rule: only an effort the API knows can reach it; anything else is
// replaced by the default rather than turning every request into a 502.
func TestLoadForestSettingsValidatesEffort(t *testing.T) {
	for _, good := range []string{"low", "medium", "high", "xhigh", "max"} {
		clearForestEnv(t)
		t.Setenv("METAFORGE_FOREST_EFFORT", good)
		if s := loadForestSettings(); s.Config.Effort != good {
			t.Errorf("effort %q was changed to %q", good, s.Config.Effort)
		}
	}
	for _, bad := range []string{"turbo", "Medium", "HIGH", "0", " high"} {
		clearForestEnv(t)
		t.Setenv("METAFORGE_FOREST_EFFORT", bad)
		if s := loadForestSettings(); s.Config.Effort != defaultForestEffort {
			t.Errorf("effort %q gave %q, want the default %q", bad, s.Config.Effort, defaultForestEffort)
		}
	}
}

func TestForestRouteWithoutKeyAnswers503(t *testing.T) {
	clearForestEnv(t)
	h := newForestHandler(loadForestSettings())

	w := httptest.NewRecorder()
	h.HandleForest(w, httptest.NewRequest("GET", "/forge/forest?word=anger", nil))

	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("status = %d, want 503", w.Code)
	}
}

func TestForestRouteWithKeyIsConfigured(t *testing.T) {
	clearForestEnv(t)
	t.Setenv("ANTHROPIC_API_KEY", "sk-test")
	h := newForestHandler(loadForestSettings())

	// A bad word is answered 400 only once the route is configured; with
	// no key the same request would be 503.
	w := httptest.NewRecorder()
	h.HandleForest(w, httptest.NewRequest("GET", "/forge/forest?word=", nil))

	if w.Code != http.StatusBadRequest {
		t.Errorf("status = %d, want 400", w.Code)
	}
}

// Rule: the server can always write the response to a request that used
// its whole deadline, including the 504.
func TestWriteTimeoutOutlastsForestDeadline(t *testing.T) {
	if forestWriteTimeout <= handler.ForestRequestTimeout {
		t.Errorf("write timeout %v must exceed request deadline %v", forestWriteTimeout, handler.ForestRequestTimeout)
	}
}

// Rule: a configured cache path opens a cache keyed on the pipeline
// fingerprint; without a path there is no cache.
func TestForestHandlerOpensConfiguredCache(t *testing.T) {
	clearForestEnv(t)
	path := filepath.Join(t.TempDir(), "forest_cache.db")
	t.Setenv("METAFORGE_FOREST_CACHE", path)

	h := newForestHandler(loadForestSettings())
	if h.Cache == nil {
		t.Fatal("no cache on the handler")
	}
	if _, err := os.Stat(path); err != nil {
		t.Errorf("cache file not created: %v", err)
	}

	clearForestEnv(t)
	if h := newForestHandler(loadForestSettings()); h.Cache != nil {
		t.Error("cache opened with no path configured")
	}
}

// Rule: a cache that will not open is logged and skipped; the forest route
// and the rest of the API keep working.
func TestForestHandlerRunsWithoutUnopenableCache(t *testing.T) {
	clearForestEnv(t)
	t.Setenv("ANTHROPIC_API_KEY", "sk-test")
	t.Setenv("METAFORGE_FOREST_CACHE", filepath.Join(t.TempDir(), "missing-dir", "forest_cache.db"))

	h := newForestHandler(loadForestSettings())
	if h.Cache != nil {
		t.Error("handler holds a cache that failed to open")
	}
	w := httptest.NewRecorder()
	h.HandleForest(w, httptest.NewRequest("GET", "/forge/forest?word=", nil))
	if w.Code != http.StatusBadRequest {
		t.Errorf("status = %d, want the configured route's 400", w.Code)
	}
}
