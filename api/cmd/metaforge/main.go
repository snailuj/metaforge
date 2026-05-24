// Metaforge API server — Sprint Zero MVP
package main

import (
	"flag"
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/snailuj/metaforge/internal/forge"
	"github.com/snailuj/metaforge/internal/handler"
	"github.com/snailuj/metaforge/internal/observe"
)

func main() {
	dbPath := flag.String("db", "../data-pipeline/output/lexicon_v2.db", "Path to lexicon_v2.db")
	stringsDir := flag.String("strings", "../strings", "Path to strings directory")
	corsOrigin := flag.String("cors-origin", "http://localhost:5173", "Allowed CORS origin for dev")
	port := flag.String("port", "8080", "Server port")
	cascade := flag.Bool("cascade", os.Getenv("METAFORGE_FORGE_CASCADE") == "1",
		"Use M03 cascade scorer on /forge/suggest (default: legacy CompositeScore)")
	cascadeTiming := flag.Bool("cascade-timing", os.Getenv("METAFORGE_CASCADE_TIMING") == "1",
		"Emit cascade hot-path timing records (must remain off in production)")
	candidateSources := flag.String("candidate-sources",
		envOrDefault("METAFORGE_FORGE_CANDIDATES", "cluster_only"),
		"Cascade candidate generation paths: cluster_only | embedding_only | union")
	embDMin := flag.Float64("embedding-d-min",
		envFloat("METAFORGE_FORGE_EMB_DMIN", 0.4),
		"Cosine distance lower band for embedding candidates (inclusive)")
	embDMax := flag.Float64("embedding-d-max",
		envFloat("METAFORGE_FORGE_EMB_DMAX", 0.85),
		"Cosine distance upper band for embedding candidates (inclusive)")
	embTopK := flag.Int("embedding-top-k",
		envInt("METAFORGE_FORGE_EMB_TOPK", 100),
		"Cap on embedding candidates per request")
	// Gamma needs a stricter parse than envFloat's Warn-and-default
	// behaviour: a malformed value silently falling back to 0.0 would
	// disable M05 while the operator believes it is set — defeating the
	// whole NewGamma boundary cast. Parse the env var explicitly and
	// log.Fatalf on malformed input, then thread the validated value as
	// the flag default.
	//
	// R3.PR.SFH O4: use LookupEnv to distinguish "set to empty"
	// (METAFORGE_FORGE_GAMMA= in a shell — operator clearing a stale
	// value) from "not set" (no env var at all). An explicit empty
	// string is operationally indistinguishable from malformed input
	// — both should fail loud rather than silently degrade to Gamma=0
	// while the operator believes they have cleared the var.
	//
	// gammaDefault sources from forge.DefaultCascadeConfig() so the
	// ratified production default (M05 Phase 2 sweep, 2026-05-24:
	// Gamma=1.0) flows from a single source of truth. Hardcoding 0.0
	// here would silently override the ratification.
	gammaDefault := forge.DefaultCascadeConfig().Gamma.Value()
	if envGamma, set := os.LookupEnv("METAFORGE_FORGE_GAMMA"); set {
		v, err := strconv.ParseFloat(envGamma, 64)
		if err != nil {
			log.Fatalf("METAFORGE_FORGE_GAMMA is malformed (%q): %v", envGamma, err)
		}
		gammaDefault = v
	}
	gamma := flag.Float64("gamma", gammaDefault,
		"M05 type-diversity bonus weight (additive into final_score). 0 disables M05.")
	flag.Parse()

	observe.Init(*cascadeTiming)

	h, err := handler.NewHandlerWithCascade(*dbPath, *cascade)
	if err != nil {
		log.Fatalf("Failed to initialise: %v", err)
	}
	defer h.Close()
	h.SetStringsDir(*stringsDir)

	cascadeCfg := forge.DefaultCascadeConfig()
	mode, err := forge.ParseCandidateMode(*candidateSources)
	if err != nil {
		log.Fatalf("invalid --candidate-sources value: %v", err)
	}
	cascadeCfg.Mode = mode
	cascadeCfg.EmbeddingDMin = *embDMin
	cascadeCfg.EmbeddingDMax = *embDMax
	cascadeCfg.EmbeddingTopK = *embTopK
	g, err := forge.NewGamma(*gamma)
	if err != nil {
		log.Fatalf("invalid --gamma value: %v", err)
	}
	cascadeCfg.Gamma = g
	if err := h.WithCascadeConfig(cascadeCfg); err != nil {
		log.Fatalf("cascade config: %v", err)
	}

	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(handler.CORSMiddleware(*corsOrigin))

	r.Get("/forge/suggest", h.HandleSuggest)
	r.Get("/thesaurus/lookup", h.HandleLookup)
	r.Get("/thesaurus/autocomplete", h.HandleAutocomplete)
	r.Get("/strings/*", h.HandleStrings)
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"status": "ok"}`))
	})

	addr := fmt.Sprintf("127.0.0.1:%s", *port)
	slog.Info("Metaforge API starting",
		"addr", addr, "db", *dbPath, "strings", *stringsDir, "cors", *corsOrigin,
		"cascade", *cascade, "cascade_timing", *cascadeTiming,
		"candidate_sources", *candidateSources,
		"emb_dmin", *embDMin, "emb_dmax", *embDMax, "emb_topk", *embTopK,
		"forge_gamma", *gamma)

	srv := &http.Server{
		Addr:         addr,
		Handler:      r,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 30 * time.Second,
	}
	log.Fatal(srv.ListenAndServe())
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func envFloat(key string, fallback float64) float64 {
	if v := os.Getenv(key); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
		slog.Warn("malformed env var, using default", "key", key, "value", v, "default", fallback)
	}
	return fallback
}

func envInt(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
		slog.Warn("malformed env var, using default", "key", key, "value", v, "default", fallback)
	}
	return fallback
}
