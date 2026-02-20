# Architecture

**Analysis Date:** 2026-02-14

## Pattern Overview

**Overall:** Headless API + Browser Frontend

**Key Characteristics:**
- Backend-agnostic API layer (Go, stateless, self-hostable)
- Frontend-first browser architecture (Lit + TypeScript + 3d-force-graph)
- SQLite lexicon database (WordNet + LLM-enriched properties)
- Distributed state: backend holds graph data, frontend renders + manages interaction

## Layers

**Backend HTTP API (`/api`):**
- Purpose: Serve lexicon data and computed metaphor matches over REST
- Location: `/home/agent/projects/metaforge/api`
- Contains: Go HTTP handlers, database access, core matching algorithm
- Depends on: SQLite (lexicon_v2.db), FastText embeddings
- Used by: Frontend, CLI tooling

**Database Layer (`/api/internal/db`):**
- Purpose: Encapsulate SQLite queries and schema navigation
- Location: `/home/agent/projects/metaforge/api/internal/db`
- Contains: Synset retrieval, property lookup, WordNet relation queries
- Depends on: SQLite driver (`github.com/mattn/go-sqlite3`)
- Used by: Handler layer, Forge/Thesaurus services

**Domain Services (`/api/internal/forge`, `/api/internal/thesaurus`, `/api/internal/embeddings`):**
- Purpose: Implement business logic independent of HTTP
- Location: `/api/internal/{forge,thesaurus,embeddings}`
- Contains: 5-tier matching algorithm, WordNet relation traversal, embedding distance computation
- Depends on: Database layer, no external services
- Used by: HTTP handlers

**HTTP Handler Layer (`/api/internal/handler`):**
- Purpose: HTTP I/O, request parsing, response marshalling
- Location: `/home/agent/projects/metaforge/api/internal/handler`
- Contains: GET /forge/suggest, GET /thesaurus/lookup, GET /strings/{locale}/ui.ftl
- Depends on: Domain services, database, CORS middleware
- Used by: Chi router (entry point)

**Frontend App Shell (`/web/src/components/mf-app.ts`):**
- Purpose: Orchestrate component lifecycle, state management, URL routing
- Location: `/home/agent/projects/metaforge/web/src/components/mf-app.ts`
- Contains: App state machine (idle, loading, ready, error), hash-based routing
- Depends on: API client, string translations, all child components
- Used by: Vite/browser entry point

**API Client (`/web/src/api/client.ts`):**
- Purpose: Fetch abstraction with error handling
- Location: `/home/agent/projects/metaforge/web/src/api/client.ts`
- Contains: `lookupWord()` function, ApiError class, response validation
- Depends on: Fetch API, TypeScript types
- Used by: App shell (mf-app), components

**Graph Transformation (`/web/src/graph/transform.ts`):**
- Purpose: Convert LookupResult API response into force graph node/link structure
- Location: `/home/agent/projects/metaforge/web/src/graph/transform.ts`
- Contains: Deduplication logic, node prioritization, capping at 80 nodes
- Depends on: API types, graph types
- Used by: App shell

**Presentation Components:**
- `mf-force-graph` (`/web/src/components/mf-force-graph.ts`): Renders 3D force graph with Three.js + 3d-force-graph
- `mf-search-bar` (`/web/src/components/mf-search-bar.ts`): Input + form submission
- `mf-results-panel` (`/web/src/components/mf-results-panel.ts`): Displays related words grouped by relation type
- `mf-toast` (`/web/src/components/mf-toast.ts`): Toast notifications (copy feedback, errors)

All extend LitElement with scoped styles and event emission.

## Data Flow

**Thesaurus Lookup Flow (Core MVP):**

1. User enters word in `mf-search-bar`, presses Enter or clicks search
2. `mf-app` calls `lookupWord(word)` via `client.ts`
3. Frontend fetches `GET /thesaurus/lookup?word={word}`
4. Backend `handler.HandleLookup()` calls `thesaurus.GetLookup(db, word)`
5. Thesaurus service queries synsets, synonyms, relations in 2 bulk queries
6. Returns `LookupResult` (word, senses, synonyms, hypernyms, hyponyms, similar)
7. Frontend calls `transformLookupToGraph()` to convert to node/link structure
8. `mf-app` state updates: `graphData`, `result`
9. `mf-force-graph` re-renders with new data
10. User clicks node → single/double-click detection → select (highlight) or navigate

**Forge Metaphor Matching Flow (Sprint Zero):**

1. User sees results panel with related words
2. (Parked: Will later expose `/forge/suggest` for metaphor discovery)
3. Backend handles property-based fuzzy matching + embedding distance computation
4. Returns tier-classified matches (legendary, interesting, strong, obvious, unlikely)

**State Management:**

- Backend: Stateless (all state in SQLite)
- Frontend: Component-level state in `mf-app`:
  - `appState`: 'idle' | 'loading' | 'ready' | 'error'
  - `result`: LookupResult | null
  - `graphData`: GraphData (nodes + links)
  - `errorMessage`: string

No global state manager; Lit reactive properties drive re-renders.

## Key Abstractions

**Synset:**
- Purpose: WordNet concept with enriched properties
- Examples: `api/internal/db/db.go` (Synset struct)
- Pattern: Read-only value object with optional enrichment fields (connotation, register, usage_example)

**Match (Forge):**
- Purpose: Ranked metaphor candidate
- Examples: `api/internal/forge/forge.go` (Match struct)
- Pattern: Contains shared properties, distance score, tier classification

**LookupResult (API Contract):**
- Purpose: API response shape for thesaurus lookup
- Examples: `web/src/types/api.ts`
- Pattern: Nested JSON: word → senses → (synset + synonyms + relations)

**GraphData / GraphNode / GraphLink:**
- Purpose: 3d-force-graph-compatible structure
- Examples: `web/src/graph/types.ts`
- Pattern: Flat node list + edge list with relation type tags

**GraphNode Relation Types:**
- `central`: The searched word (larger, gold)
- `synonym`: Same sense, interchangeable
- `hypernym`: More general (e.g., "tree" for "oak")
- `hyponym`: More specific (e.g., "oak" for "tree")
- `similar`: Related by meaning (WordNet "similar" relation)

## Entry Points

**Backend:**
- Location: `/home/agent/projects/metaforge/api/cmd/metaforge/main.go`
- Triggers: `go run ./cmd/metaforge/main.go`
- Responsibilities: Parse flags, open SQLite, initialize handler, start Chi router on port 8080

**Frontend:**
- Location: `/home/agent/projects/metaforge/web/src/main.ts`
- Triggers: `npm run dev` (Vite dev server) or `npm run build` (production bundle)
- Responsibilities: Import mf-app component (registers it), Vite wires entry point to index.html

**Development Proxy:**
- Vite dev server proxies `/thesaurus/*`, `/forge/*`, `/strings/*`, `/health` to `http://localhost:8080`
- Config: `web/vite.config.ts`

## Error Handling

**Strategy:** Propagate errors up to UI with user-facing messages

**Patterns:**

Backend:
- DB queries return `error` or result
- HTTP handlers check errors, respond with `http.Error()` and appropriate status code
- `handler.go` validates required tables exist on startup
- Panic recovery via `middleware.Recoverer` in Chi

Frontend:
- `ApiError` exception wraps status code + message
- `lookupWord()` validates response shape before returning
- `mf-app` catches errors, sets `appState = 'error'` and `errorMessage`
- Error message displayed in `.status-message` overlay
- Toast component for transient feedback (copy, retries)

All errors logged via `slog` (backend) or `console.error()` (frontend).

## Cross-Cutting Concerns

**Logging:**
- Backend: `log/slog` structured logging with "addr", "db", "strings", "cors" context
- Frontend: `console.error()` on fetch failures, bundle parse errors

**Validation:**
- Backend: Handler validates query parameters (threshold [0, 1], limit > 0 and ≤ 200)
- Frontend: API client validates LookupResult shape (word is string, senses is array)

**Authentication:**
- None. MVP is read-only, no user accounts or API keys.

**CORS:**
- Backend: `handler.CORSMiddleware()` allows configured origin (dev: `http://localhost:5173`)
- Frontend: Same-origin in production (served by same Caddy instance)

**Localisation:**
- Fluent (Mozilla's i18n framework) for UI strings
- Single `ui.en-GB.ftl` file (UK English only)
- Frontend calls `/strings/v1/ui.ftl` to fetch at startup
- Backend maps `v1/ui.ftl` → `strings/v1/ui.en-GB.ftl`, sets immutable cache headers

**Caching:**
- Static .ftl strings: `Cache-Control: public, max-age=31536000, immutable` (1 year)
- SQLite: read-only mode (`mode=ro`), max 4 open connections

---

*Architecture analysis: 2026-02-14*
