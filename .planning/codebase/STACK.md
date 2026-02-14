# Technology Stack

**Analysis Date:** 2026-02-14

## Languages

**Primary:**
- Go 1.22 - Backend API and core business logic
- TypeScript 5.7 - Frontend web application
- Python 3 - Data pipeline and enrichment scripts

**Secondary:**
- SQL - Database schema and queries
- Fluent (FTL) - Internationalization and localization strings

## Runtime

**Environment:**
- Go 1.22.5 - Backend execution environment
- Node.js (ES2022 target) - Frontend development and build
- Python 3.x - Data pipeline execution

**Package Manager:**
- Go modules - `github.com/snailuj/metaforge`
- npm - Lockfile: `web/package-lock.json` (present)

## Frameworks

**Core:**
- Lit 3.2.0 - Frontend web components framework
- `3d-force-graph` 1.77.0 - 3D force-directed graph visualization using Three.js
- Three.js types included via `@types/three` 0.182.0 - 3D rendering library types
- chi/v5 5.2.5 - Go HTTP router and middleware framework

**Testing:**
- Vitest 3.0.0 - Frontend unit testing framework
- Go's built-in `testing` package - Backend unit testing

**Build/Dev:**
- Vite 6.1.0 - Frontend bundler and dev server
- TypeScript compiler 5.7.0 - Type checking and transpilation
- `@vitest/coverage-v8` 3.2.4 - Code coverage reporting

**Internationalization:**
- `@fluent/bundle` 0.18.0 - Fluent (FTL) message processing and localization

## Key Dependencies

**Critical:**
- `github.com/mattn/go-sqlite3` 1.14.33 - SQLite driver for Go (embedded database)
- `github.com/go-chi/chi/v5` 5.2.5 - HTTP routing and middleware (API backbone)
- Lit 3.2.0 - Component framework (UI structure)
- `3d-force-graph` 1.77.0 - Graph visualization library (core feature)

**Infrastructure:**
- happy-dom 17.0.0 - Lightweight DOM implementation for testing
- three-spritetext 1.10.0 - Text rendering in Three.js scenes

## Configuration

**Environment:**
- Environment variables for backend configuration:
  - `DB_PATH` - Path to SQLite database (default: `../data-pipeline/output/lexicon_v2.db`)
  - `STRINGS_DIR` - Path to FTL strings directory (default: `../strings`)
  - `CORS_ORIGIN` - CORS origin for dev (default: `http://localhost:5173`)
  - `PORT` - Server port (default: `8080`)

**Build:**
- TypeScript: `web/tsconfig.json` - Strict mode, ES2022 target, path aliases (`@/*`)
- Vite: `web/vite.config.ts` - Port 5173, proxy config to backend on port 8080, test environment setup
- Vitest configuration in `vite.config.ts` - happy-dom environment, coverage via v8

## Platform Requirements

**Development:**
- Go 1.22+ with toolchain go1.22.5
- Node.js 18+ (for npm and Vite)
- Python 3.x (for data pipeline scripts)
- SQLite3 CLI optional (for database inspection)
- Claude CLI tool (for data enrichment scripts)

**Production:**
- Go stateless API deployment (self-hostable)
- Static frontend assets served via CDN or web server
- SQLite database on shared storage or local filesystem (read-only mode)
- Backend accessible at configurable port (default 8080)
- Frontend accessible via web browser, proxies to backend API

## Database

**Type:** SQLite embedded database
- Read-only connection mode with immutable flag (`mode=ro&immutable=1`)
- Location: `data-pipeline/output/lexicon_v2.db` (binary, gitignored)
- Schema dump: `data-pipeline/output/lexicon_v2.sql` (SQL text, committed)
- Restore script: `data-pipeline/scripts/restore_db.sh` (idempotent)

**Required tables:**
- `synsets` - WordNet synset definitions
- `lemmas` - Lemma entries linked to synsets
- `synset_properties` - LLM-enriched properties junction table
- `property_vocabulary` - Property metadata
- `synset_centroids` - Embedding centroids for similarity
- `frequencies` - Word frequency data

## API Endpoints

**Core Endpoints (all proxied through Vite dev server to port 8080):**
- `GET /forge/suggest` - Metaphor forge suggestions
- `GET /thesaurus/lookup` - Word lookup with definitions and relations
- `GET /thesaurus/autocomplete` - Prefix-based autocomplete search
- `GET /strings/*` - Fluent (FTL) localization strings
- `GET /health` - Health check endpoint

## Development Workflow

**Frontend:**
```bash
npm run dev          # Vite dev server (port 5173) with backend proxy
npm run build        # TypeScript check + Vite build to dist/
npm run test         # Run Vitest suite
npm run test:watch   # Watch mode
npm run test:coverage # Coverage report
```

**Backend:**
```bash
go test ./...        # Run all tests
go run ./cmd/metaforge/main.go -db [path] -port 8080
```

---

*Stack analysis: 2026-02-14*
