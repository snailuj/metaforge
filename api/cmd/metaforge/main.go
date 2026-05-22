// Metaforge API server — Sprint Zero MVP
package main

import (
	"flag"
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"os"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
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
	flag.Parse()

	observe.Init(*cascadeTiming)

	h, err := handler.NewHandlerWithCascade(*dbPath, *cascade)
	if err != nil {
		log.Fatalf("Failed to initialise: %v", err)
	}
	defer h.Close()
	h.SetStringsDir(*stringsDir)

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
	slog.Info("Metaforge API starting", "addr", addr, "db", *dbPath, "strings", *stringsDir, "cors", *corsOrigin, "cascade", *cascade, "cascade_timing", *cascadeTiming)

	srv := &http.Server{
		Addr:         addr,
		Handler:      r,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 30 * time.Second,
	}
	log.Fatal(srv.ListenAndServe())
}
