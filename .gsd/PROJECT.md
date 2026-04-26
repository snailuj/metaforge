# Project

## What This Is

Metaforge is a browser-based visual thesaurus and metaphor generator — a spiritual successor to Visual Thesaurus. Users search a word, it blooms into a 3D force-directed graph of connected meanings (synonyms, antonyms, collocations, register, etymology). Click a neighbour and the graph reshuffles. Bolted on is an experimental metaphor generator surfacing unexpected semantic bridges between words.

Free, open-source, owned by a NZ Charitable Trust. Hosted at metaforge.julianit.me.

## Core Value

A fast, functional thesaurus that works in under 3 seconds — search, find, copy. The 3D graph enhances but never blocks access. If the graph breaks, the HUD panel still works as a complete thesaurus.

## Current State

- **Backend:** Go headless API (chi router), stateless and self-hostable. MVP-complete with thesaurus lookup, autocomplete, forge suggest, and strings endpoints. ~300 automated tests across Go, TypeScript, and Python.
- **Frontend:** Lit + Vite + TypeScript. Basic thesaurus and graph navigation complete. HUD results panel functional. Deployed to staging.
- **Data pipeline:** SQLite database with ~107k synsets, FastText 300d embeddings, Claude-extracted semantic properties. Enrichment pipeline ~70% MVP-ready. Curated vocabulary snapping, concreteness regression, and MRR evaluation in place.
- **Staging:** Live at https://metaforge.julianit.me/ via Caddy + systemd.
- **Forge tuning in progress.** MRR evaluation framework operational but scores need improvement.

## Architecture / Key Patterns

| Layer | Technology | Notes |
|-------|-----------|-------|
| API | Go + chi | Stateless, single binary, binds localhost:8080 |
| Frontend | Lit + Vite + TypeScript | Shadow DOM web components, 3d-force-graph for visualisation |
| Data | SQLite + FastText 300d | Embedded DB, no external services required |
| Properties | Claude-extracted | 10-15 semantic properties per synset, snapped to curated vocabulary |
| Deployment | Caddy + systemd | Auto-HTTPS via Let's Encrypt, reverse proxy to Go API |
| Local storage | IndexedDB | User preferences, no accounts in MVP |

Key conventions: FP over OOP, UK English spelling, TDD with frequent atomic commits, idempotent batch operations.

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Milestone Sequence

- [x] Sprint Zero — Backend API, data pipeline foundations, staging deployment
