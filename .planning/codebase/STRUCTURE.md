# Codebase Structure

**Analysis Date:** 2026-02-14

## Directory Layout

```
metaforge/
├── api/                           # Go backend API
│   ├── cmd/metaforge/             # Binary entry point
│   │   └── main.go                # Server startup
│   ├── internal/                  # Private packages (not importable by other modules)
│   │   ├── db/                    # SQLite access layer
│   │   ├── embeddings/            # Cosine distance computation
│   │   ├── forge/                 # 5-tier matching algorithm
│   │   ├── handler/               # HTTP handlers + middleware
│   │   └── thesaurus/             # WordNet relation lookup
│   ├── go.mod                     # Go module definition
│   └── go.sum                     # Go dependency lock
│
├── web/                           # TypeScript/Lit frontend
│   ├── src/
│   │   ├── api/                   # HTTP client
│   │   ├── components/            # Lit web components
│   │   ├── graph/                 # Graph transformation + colours
│   │   ├── lib/                   # Utilities (strings, etc.)
│   │   ├── styles/                # Shared CSS (if any)
│   │   ├── types/                 # TypeScript interfaces
│   │   ├── main.ts                # Entry point (imports mf-app)
│   │   └── index.html             # HTML template
│   ├── package.json               # Node dependencies
│   ├── package-lock.json          # Node lock file
│   ├── tsconfig.json              # TypeScript config
│   ├── vite.config.ts             # Vite build + dev proxy
│   └── vitest.config.ts           # Test runner config (if exists)
│
├── data-pipeline/                 # Python data processing
│   ├── scripts/                   # Data processing scripts
│   ├── output/
│   │   └── lexicon_v2.db          # SQLite database (gitignored)
│   │   └── lexicon_v2.sql         # Schema + data dump (for version control)
│   └── requirements.txt           # Python dependencies
│
├── strings/                       # Fluent i18n files
│   └── v1/
│       └── ui.en-GB.ftl           # UI messages (UK English)
│
├── docs/
│   ├── designs/                   # Feature design docs
│   │   ├── README.md              # Index of design docs
│   │   └── metaphor-forge.md      # Forge feature spec
│   ├── plans/                     # Implementation plans
│   │   ├── 2026-01-26-sprint-zero.md
│   │   └── 2026-01-28-performance-tuning.md
│   └── ...
│
├── .planning/                     # GSD artefacts (auto-created)
│   └── codebase/                  # Generated analysis documents
│       ├── ARCHITECTURE.md        # This document
│       ├── STRUCTURE.md           # File/directory guide
│       ├── CONVENTIONS.md         # Code style guide
│       └── ...
│
├── CLAUDE.md                      # Project context for Claude
├── Metaforge-PRD-2.md             # Product requirements
└── .gitignore                     # Excludes .db, node_modules, etc.
```

## Directory Purposes

**`api/`:**
- Purpose: Go REST API server
- Contains: HTTP handlers, database queries, domain logic
- Key files: `cmd/metaforge/main.go` (entry), `internal/handler/handler.go` (routes)

**`api/internal/`:**
- Purpose: Private Go packages (Go convention: not importable by other modules)
- Contains: Core logic separated by concern
- Key files: `db/db.go` (queries), `forge/forge.go` (matching), `thesaurus/thesaurus.go` (lookup)

**`web/src/`:**
- Purpose: TypeScript/Lit source (transpiled to ES modules)
- Contains: Components, utilities, types
- Key files: `main.ts` (entry), `components/mf-app.ts` (app shell)

**`web/src/components/`:**
- Purpose: Lit web components (custom HTML elements)
- Contains: `mf-app.ts`, `mf-search-bar.ts`, `mf-force-graph.ts`, `mf-results-panel.ts`, `mf-toast.ts`
- Pattern: One component per file (or `.ts` + `.test.ts` pair)

**`web/src/api/`:**
- Purpose: Fetch abstraction for HTTP communication
- Contains: `client.ts` (lookupWord function), API error handling

**`web/src/graph/`:**
- Purpose: Graph data transformation and visualization setup
- Contains: `transform.ts` (LookupResult → GraphData), `types.ts` (type definitions), `colours.ts` (node colour map)

**`web/src/lib/`:**
- Purpose: Shared utilities not tied to a component
- Contains: `strings.ts` (Fluent i18n loader)

**`web/src/types/`:**
- Purpose: Shared TypeScript interfaces
- Contains: `api.ts` (API response shapes), `3d-force-graph.d.ts` (type stubs for 3d-force-graph)

**`data-pipeline/`:**
- Purpose: Python scripts to import WordNet, compute embeddings, enrich with Gemini
- Contains: Extraction scripts, SQL dumps for version control
- Key files: `output/lexicon_v2.sql` (schema + data)

**`strings/`:**
- Purpose: Localisation files (Fluent format)
- Contains: `v1/ui.en-GB.ftl` (UI messages in UK English)
- Backend serves via GET `/strings/v1/ui.ftl` (maps to locale file)

**`docs/`:**
- Purpose: Design docs, implementation plans, notes
- Contains: Feature specs (`designs/`), phase plans (`plans/`)

## Key File Locations

**Entry Points:**

| File | Purpose | Trigger |
|------|---------|---------|
| `api/cmd/metaforge/main.go` | Backend server startup | `go run ./cmd/metaforge/main.go` |
| `web/src/main.ts` | Frontend component registration | Vite imports from `index.html` |
| `web/index.html` | HTML shell | Served by Vite/Caddy |

**Configuration:**

| File | Purpose |
|------|---------|
| `api/go.mod` | Go module definition (dependencies: chi, sqlite3) |
| `web/package.json` | Node dependencies (Lit, 3d-force-graph, Vite, Vitest) |
| `web/tsconfig.json` | TypeScript compiler settings |
| `web/vite.config.ts` | Build config + dev proxy to `:8080` |
| `strings/v1/ui.en-GB.ftl` | UI message translations |

**Core Logic:**

| File | Purpose |
|------|---------|
| `api/internal/handler/handler.go` | HTTP route handlers: /forge/suggest, /thesaurus/lookup, /strings/* |
| `api/internal/db/db.go` | SQLite queries: GetSynset, GetSynsetIDForLemma, GetForgeMatches |
| `api/internal/forge/forge.go` | 5-tier matching algorithm: ClassifyTier, NormaliseDistances, SortByTier |
| `api/internal/thesaurus/thesaurus.go` | WordNet traversal: GetLookup, querySenses, queryRelations |
| `web/src/api/client.ts` | HTTP client: lookupWord, ApiError |
| `web/src/graph/transform.ts` | LookupResult → GraphData transformation |
| `web/src/components/mf-app.ts` | App orchestration: state machine, routing, error handling |
| `web/src/components/mf-force-graph.ts` | 3D graph rendering with click/hover interactions |

**Testing:**

| File | Pattern |
|------|---------|
| `api/internal/*/..._test.go` | Go tests (standard library testing) |
| `web/src/**/*.test.ts` | TypeScript tests (Vitest, happy-dom) |

## Naming Conventions

**Files:**

- Go: `snake_case.go` (e.g., `embeddings.go`, `handler_test.go`)
- TypeScript: `kebab-case.ts` (e.g., `mf-app.ts`, `mf-search-bar.ts`)
- Fluent: `snake_case.en-GB.ftl` (e.g., `ui.en-GB.ftl`)
- SQL dumps: `lexicon_v{version}.sql` (e.g., `lexicon_v2.sql`)

**Directories:**

- Go packages: `snake_case` (e.g., `internal/handler`, `internal/db`)
- Web components: `{feature-name}` (e.g., `components/`)
- Domain areas: Semantic names (e.g., `graph/`, `api/`, `lib/`)

**Web Components (Lit):**

- Custom element tag: `mf-{feature}` (e.g., `mf-app`, `mf-force-graph`)
- Class name: PascalCase (e.g., `MfApp`, `MfForceGraph`)
- File: `mf-{feature}.ts`
- Test: `mf-{feature}.test.ts`

**Go Functions/Types:**

- Type names: PascalCase (e.g., `Handler`, `Synset`, `Match`)
- Function names: PascalCase (e.g., `NewHandler`, `HandleSuggest`, `GetLookup`)
- Constants: `PascalCase` or `ALL_CAPS` (e.g., `DefaultThreshold`, `HIGH_DISTANCE_THRESHOLD`)

**TypeScript Functions/Types:**

- Type names: PascalCase (e.g., `LookupResult`, `GraphNode`)
- Function names: camelCase (e.g., `transformLookupToGraph`, `lookupWord`)
- Constants: `camelCase` (e.g., `DEFAULT_MAX_NODES`)

## Where to Add New Code

**New Backend Endpoint:**

1. Create handler method in `api/internal/handler/handler.go`
   - Pattern: `func (h *Handler) HandleFeature(w http.ResponseWriter, r *http.Request)`
2. Register route in `api/cmd/metaforge/main.go`
   - Pattern: `r.Get("/feature/endpoint", h.HandleFeature)`
3. Add domain logic to appropriate service (e.g., `api/internal/forge/`, `api/internal/thesaurus/`)
4. Add tests:
   - Service logic: `api/internal/*/..._test.go` (use standard library testing)
   - HTTP handler: `api/internal/handler/*_test.go` (use httptest)

**New Frontend Component:**

1. Create component file: `web/src/components/mf-{feature}.ts`
   - Extend `LitElement`, use `@customElement('mf-{feature}')`
   - Add styles via `static styles = css\`...\``
   - Add tests: `web/src/components/mf-{feature}.test.ts` (Vitest)
2. Import and register in `mf-app.ts` (or relevant parent)
3. Emit custom events (bubbling, composed) for parent communication
4. Use `@property()` for inputs, `@state()` for internal state

**New Utility Function:**

- **Shared backend logic:** Add to appropriate `api/internal/*/` package
- **Shared frontend logic:** Add to `web/src/lib/` (e.g., `web/src/lib/utils.ts`)
- **Type definitions:** Add to `web/src/types/` or inline in relevant file

**New Database Query:**

1. Add query function to `api/internal/db/db.go`
2. Pattern: Prepare query, scan into struct/slice, handle sql.ErrNoRows
3. Add test: `api/internal/db/db_test.go`

## Special Directories

**`api/internal/`:**
- Purpose: Go convention for private packages
- Generated: No (hand-written)
- Committed: Yes
- Note: Packages here cannot be imported by external modules; only `cmd/metaforge/main.go` imports them

**`web/node_modules/`:**
- Purpose: Installed Node dependencies
- Generated: Yes (by `npm install`)
- Committed: No (in .gitignore)

**`data-pipeline/.venv/`:**
- Purpose: Python virtual environment
- Generated: Yes (by `python -m venv .venv`)
- Committed: No (in .gitignore)

**`data-pipeline/output/`:**
- Purpose: Generated artefacts (SQLite database, SQL dumps)
- Generated: Partially (`.db` is generated, `.sql` is both generated and committed)
- Committed: `.sql` files only (`.db` is gitignored)
- Note: Restore database from `.sql` via `data-pipeline/scripts/restore_db.sh`

**`.planning/codebase/`:**
- Purpose: Auto-generated GSD analysis documents
- Generated: Yes (by GSD mapping tools)
- Committed: No (in .gitignore, but can be)
- Note: Consumed by GSD plan/execute phases

**`strings/v1/`:**
- Purpose: Fluent i18n files
- Generated: No (hand-written)
- Committed: Yes
- Note: Backend serves `.ftl` files with immutable cache headers

---

*Structure analysis: 2026-02-14*
