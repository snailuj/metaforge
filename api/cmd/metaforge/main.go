// Metaforge API server — Sprint Zero MVP
package main

import (
	"flag"
	"fmt"
	"log"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/snailuj/metaforge/internal/handler"
)

func main() {
	dbPath := flag.String("db", "../data-pipeline/output/lexicon_v2.db", "Path to lexicon_v2.db")
	port := flag.String("port", "8080", "Server port")
	flag.Parse()

	h, err := handler.NewHandler(*dbPath)
	if err != nil {
		log.Fatalf("Failed to initialise: %v", err)
	}
	defer h.Close()

	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	r.Get("/forge/suggest", h.HandleSuggest)
	r.Get("/thesaurus/lookup", h.HandleLookup)
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"status": "ok"}`))
	})

	addr := fmt.Sprintf(":%s", *port)
	fmt.Printf("Metaforge API starting on %s...\n", addr)
	fmt.Printf("  Database: %s\n", *dbPath)
	fmt.Printf("  Try: curl 'http://localhost:%s/thesaurus/lookup?word=fire'\n", *port)
	log.Fatal(http.ListenAndServe(addr, r))
}
