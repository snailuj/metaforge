package main

import (
	"log/slog"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/snailuj/metaforge/internal/forest"
	"github.com/snailuj/metaforge/internal/handler"
)

// Per-visitor allowances a minute on the routes that query the lexicon. One
// visitor is one address, and a school puts a classroom behind one: a search
// is about 80 lookups with its glimpses (each click adds up to 30), so 25
// pupils searching once a minute is about 2,000 lookups, and autocomplete
// fires up to about 2 a second each (200 ms debounce, 3 letters minimum).
// The limits only stop one address hogging the server; the global gate
// bounds the load whoever sends it. /forge/suggest has no caller in the web
// app, only API users.
const (
	defaultAutocompletePerVisitorMinute = 600
	defaultLookupPerVisitorMinute       = 1500
	defaultSuggestPerVisitorMinute      = 150
	// Forest requests are one click each, and a cache hit costs a lemma check.
	defaultForestReadPerVisitorMinute = 120

	// databaseGateSize is twice the lexicon pool: enough that the pool is
	// never idle while requests wait, small enough that a flood queues
	// briefly instead of piling up on it.
	databaseGateSize = 2 * handler.DBMaxOpenConns
	// databaseGateWait is how long a request waits for a slot before a 503.
	databaseGateWait = 2 * time.Second
	// routeMaxVisitors bounds each route's visitor table; see
	// forest.VisitorLimiter for what happens when it fills.
	routeMaxVisitors = 50_000
)

type routeLimitSettings struct {
	Autocomplete, Lookup, Suggest, Forest int
}

func loadRouteLimits() routeLimitSettings {
	return routeLimitSettings{
		Autocomplete: boundedEnvInt("METAFORGE_AUTOCOMPLETE_PER_VISITOR_MINUTE", defaultAutocompletePerVisitorMinute, 1, 1<<20),
		Lookup:       boundedEnvInt("METAFORGE_LOOKUP_PER_VISITOR_MINUTE", defaultLookupPerVisitorMinute, 1, 1<<20),
		Suggest:      boundedEnvInt("METAFORGE_SUGGEST_PER_VISITOR_MINUTE", defaultSuggestPerVisitorMinute, 1, 1<<20),
		Forest:       boundedEnvInt("METAFORGE_FOREST_READ_PER_VISITOR_MINUTE", defaultForestReadPerVisitorMinute, 1, 1<<20),
	}
}

// newDatabaseGate is the in-flight cap shared by every route that reads the
// lexicon.
func newDatabaseGate() *handler.Gate {
	slog.Info("database routes capped in flight", "size", databaseGateSize, "wait", databaseGateWait.String())
	return handler.NewGate(databaseGateSize, databaseGateWait, time.Now)
}

// routeLimit gives one route its own per-visitor limiter. These routes are
// free reads behind the gate, so a full visitor table admits new visitors
// rather than locking real users out.
func routeLimit(route string, perMinute int) func(http.Handler) http.Handler {
	l := forest.NewWindowedLimiter(route, perMinute, routeMaxVisitors, time.Minute, time.Now).FailOpenWhenFull()
	slog.Info("route limited per visitor", "route", route, "per_minute", perMinute, "max_visitors", routeMaxVisitors)
	return handler.VisitorRateLimit(route, l, time.Now)
}

// registerDatabaseRoutes mounts the routes that query the lexicon, each
// behind its own per-visitor limit and then the shared gate.
func registerDatabaseRoutes(r chi.Router, h *handler.Handler, limits routeLimitSettings, gate *handler.Gate) {
	r.With(routeLimit("suggest", limits.Suggest), gate.Middleware).Get("/forge/suggest", h.HandleSuggest)
	r.With(routeLimit("lookup", limits.Lookup), gate.Middleware).Get("/thesaurus/lookup", h.HandleLookup)
	r.With(routeLimit("autocomplete", limits.Autocomplete), gate.Middleware).Get("/thesaurus/autocomplete", h.HandleAutocomplete)
}

// registerForestRoute mounts /forge/forest and /forge/forest/saved behind
// their own per-visitor read limit, ahead of the handler's lemma check. The gate is not middleware here:
// a forest request holds no slot through its model calls, so the handler's
// KnownWord takes one (Gate.WrapKnownWord) only for the check.
func registerForestRoute(r chi.Router, fh *handler.ForestHandler, limits routeLimitSettings) {
	limited := r.With(routeLimit("forest", limits.Forest))
	limited.Get("/forge/forest", fh.HandleForest)
	limited.Get("/forge/forest/saved", fh.HandleSaved)
}
