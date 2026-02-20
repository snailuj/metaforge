# External Integrations

**Analysis Date:** 2026-02-14

## APIs & External Services

**Claude LLM (via CLI):**
- Used for data enrichment during pipeline execution
- SDK/Client: Claude CLI (`claude` command line tool)
- Auth: API key loaded from environment (not committed)
- Invocation: Python subprocess integration in `lib/claude_client.py`
- Purpose: Extract sensory/behavioural properties from WordNet synsets
- Model targets: haiku, opus (configurable via scripts)
- Rate limiting: Automatic retry with configurable delays

**WordNet (Local):**
- Public lexical database imported into SQLite
- No API integration - data is pre-processed and loaded
- Used for synset definitions, lemmas, and base relationships

## Data Storage

**Databases:**
- SQLite (embedded)
  - Connection: Read-only mode via `database/sql` (Go) with immutable flag
  - Path configured via `DB_PATH` environment variable
  - Client: Go's `github.com/mattn/go-sqlite3` v1.14.33
  - No ORM - raw SQL queries in `api/internal/db/db.go`

**File Storage:**
- Local filesystem only
  - Database: `data-pipeline/output/lexicon_v2.db`
  - Localization strings: Fluent (.ftl) files in `strings/` directory
  - Frontendbuilt assets served statically after Vite build

**Caching:**
- None configured for backend
- Frontend: HTTP cache headers (`cache: 'no-cache'` for FTL strings to revalidate on deploy)

## Authentication & Identity

**Auth Provider:**
- None - No user accounts in MVP
- Public API endpoints (no authentication required)
- CORS restricted to configured origin (default: `http://localhost:5173` for dev)

## Monitoring & Observability

**Error Tracking:**
- None detected - No Sentry, LogRocket, or error tracking service integrated

**Logs:**
- Backend: `log/slog` package (standard Go structured logging)
  - Level: Info and higher logged to stdout
  - Typical output: startup config, request logging via chi middleware
- Frontend: Console logging only (via Lit component lifecycle)
- Data pipeline: Python logging module with configurable verbosity

## CI/CD & Deployment

**Hosting:**
- Not yet deployed - Sprint Zero backend complete, frontend not yet deployed
- Designed for: Stateless Go API (self-hostable on any platform with SQLite support)
- Frontend: Static asset deployment (Vite build output)

**CI Pipeline:**
- Not detected - Repository structure suggests manual local development
- No GitHub Actions, GitLab CI, or other CI service configured
- Test suite: `npm run test` and `go test ./...` for local execution

## Environment Configuration

**Required env vars:**
- `DB_PATH` - Path to SQLite database (default: `../data-pipeline/output/lexicon_v2.db`)
- `STRINGS_DIR` - Path to FTL strings directory (default: `../strings`)
- `CORS_ORIGIN` - CORS origin for frontend (default: `http://localhost:5173`)
- `PORT` - Server port (default: `8080`)

**Optional env vars:**
- Claude API key (when running data enrichment scripts, loaded at runtime, never committed)

**Secrets location:**
- Not committed to repository
- Claude CLI handles API key management internally
- Environment variables should be sourced from shell profile or `.env` (gitignored)

## Webhooks & Callbacks

**Incoming:**
- None - No webhook listeners configured

**Outgoing:**
- None - No external service callbacks

## Data Pipeline Integrations

**Upstream sources (pre-processed into SQLite):**
- OEWN (Open English WordNet) - Synset definitions and lemmas
- SynTagNet - Syntagmatic relationships (placeholder for future integration)
- FastText embeddings - Pre-computed word embeddings for similarity
- Subtlex frequency corpus - Word frequency data
- Gemini API - Used historically for property extraction (replaced by Claude CLI)

**Python enrichment scripts:**
- Location: `data-pipeline/scripts/`
- Claude integration: `lib/claude_client.py`
- Key scripts:
  - `enrich_properties.py` - Extract sensory/behavioural properties via Claude
  - `bradley_terry.py` - Ranking algorithm for properties
  - `import_*.py` - Import external data sources into SQLite

## Frontend API Communication

**Backend communication:**
- Vite dev proxy: Proxies `/thesaurus/*`, `/forge/*`, `/health`, `/strings/*` to `http://localhost:8080`
- Production: Direct fetch requests (no proxy needed)
- Client library: `web/src/api/client.ts`
  - `lookupWord(word: string)` - Query `/thesaurus/lookup?word=...`
  - `autocompleteWord(prefix: string, limit: number)` - Query `/thesaurus/autocomplete?prefix=...&limit=...`
- Error handling: Custom `ApiError` class wraps HTTP errors

## Internationalization (i18n)

**Localization system:**
- Framework: Fluent (FTL) message format via `@fluent/bundle` 0.18.0
- Strings source: `strings/v1/ui.ftl`
- Loading: `web/src/lib/strings.ts` fetches via HTTP with `cache: 'no-cache'`
- Fallback: Message IDs used as fallback if fetch fails

## Frontend Dependencies (Third-Party Components)

**Three.js ecosystem:**
- `3d-force-graph` 1.77.0 - Graph rendering (primary visualization)
- `three-spritetext` 1.10.0 - Text rendering in 3D scenes
- `@types/three` 0.182.0 - Type definitions for Three.js

---

*Integration audit: 2026-02-14*
