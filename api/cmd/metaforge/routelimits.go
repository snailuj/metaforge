package main

import (
	"log/slog"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/snailuj/metaforge/internal/forest"
	"github.com/snailuj/metaforge/internal/handler"
)

// Per-visitor allowances a minute on the routes that query the lexicon. A
// real session never reaches them: autocomplete fires at most about 2 a
// second (200 ms debounce, 3 letters minimum); one search lookup plus its
// glimpses is about 80 lookups and each click adds up to 30 more, so a hard
// exploring minute stays near 230. /forge/suggest has no caller in the web
// app, only API users.
const (
	defaultAutocompletePerVisitorMinute = 120
	defaultLookupPerVisitorMinute       = 300
	defaultSuggestPerVisitorMinute      = 30
	// routeMaxVisitors bounds each route's visitor table; see
	// forest.VisitorLimiter for what happens when it fills.
	routeMaxVisitors = 50_000
)

type routeLimitSettings struct {
	Autocomplete, Lookup, Suggest int
}

func loadRouteLimits() routeLimitSettings {
	return routeLimitSettings{
		Autocomplete: boundedEnvInt("METAFORGE_AUTOCOMPLETE_PER_VISITOR_MINUTE", defaultAutocompletePerVisitorMinute, 1, 1<<20),
		Lookup:       boundedEnvInt("METAFORGE_LOOKUP_PER_VISITOR_MINUTE", defaultLookupPerVisitorMinute, 1, 1<<20),
		Suggest:      boundedEnvInt("METAFORGE_SUGGEST_PER_VISITOR_MINUTE", defaultSuggestPerVisitorMinute, 1, 1<<20),
	}
}

// routeLimit gives one route its own per-visitor limiter.
func routeLimit(route string, perMinute int) func(http.Handler) http.Handler {
	l := forest.NewWindowedLimiter(route, perMinute, routeMaxVisitors, time.Minute, time.Now)
	slog.Info("route limited per visitor", "route", route, "per_minute", perMinute, "max_visitors", routeMaxVisitors)
	return handler.VisitorRateLimit(route, l, time.Now)
}

// registerDatabaseRoutes mounts the routes that query the lexicon, each
// behind its own per-visitor limit.
func registerDatabaseRoutes(r chi.Router, h *handler.Handler, limits routeLimitSettings) {
	r.With(routeLimit("suggest", limits.Suggest)).Get("/forge/suggest", h.HandleSuggest)
	r.With(routeLimit("lookup", limits.Lookup)).Get("/thesaurus/lookup", h.HandleLookup)
	r.With(routeLimit("autocomplete", limits.Autocomplete)).Get("/thesaurus/autocomplete", h.HandleAutocomplete)
}
