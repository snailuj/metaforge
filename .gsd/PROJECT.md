# Project

## What This Is

Metaforge is a browser-based visual thesaurus and metaphor generator — a spiritual successor to Visual Thesaurus. Users search a word, it blooms into a 3D force-directed graph of connected meanings (synonyms, antonyms, collocations, register, etymology). Click a neighbour and the graph reshuffles. Bolted on is an experimental metaphor generator surfacing unexpected semantic bridges between words.

Free, open-source, owned by a NZ Charitable Trust. Hosted at metaforge.julianit.me.

## Core Value

A fast, functional thesaurus that works in under 3 seconds — search, find, copy. The 3D graph enhances but never blocks access. If the graph breaks, the HUD panel still works as a complete thesaurus.

## Current State

- **Backend:** Go headless API (chi router), stateless and self-hostable. MVP-complete with thesaurus lookup, autocomplete, forge suggest, and strings endpoints. ~300 automated tests across Go, TypeScript, and Python.
- **Frontend:** Lit + Vite + TypeScript. Basic thesaurus and graph navigation complete. HUD results panel functional. Deployed to staging.
- **Data pipeline:** SQLite database with ~107k synsets, FastText 300d embeddings, Claude-extracted semantic properties. **V2 Sonnet enrichment imported** — 12,066 enriched synsets, 6 property_type categories, salience accumulation in `synset_properties_curated`. Curated vocabulary snapping, concreteness regression, and MRR evaluation in place.
- **Eval harness (M001 in flight):** Aptness evaluator (`evaluate_aptness.py`) shipped — salience-weighted Jaccard over shared cluster_ids, calibrated against MUNCH inapt controls (CC BY 4.0, 10,261 apt + 1,447 inapt). Combined V2 baseline recorded at `data-pipeline/output/eval_baseline_v2.json` (MRR 0.0073, separation 0.0103, aptness_rate 0.0849). Separation magnitude below the 0.3 target — closing it is downstream tuning work in S02+.
- **Staging:** Live at https://metaforge.julianit.me/ (production) and https://metaforge-next.julianit.me/ (V2 next). V2 DB now serving on next; forge responses expose `salience_sum`.

## Architecture / Key Patterns

| Layer | Technology | Notes |
|-------|-----------|-------|
| API | Go + chi | Stateless, single binary, binds localhost:8080 |
| Frontend | Lit + Vite + TypeScript | Shadow DOM web components, 3d-force-graph for visualisation |
| Data | SQLite + FastText 300d | Embedded DB, no external services required |
| Properties | Claude-extracted (V2 Sonnet) | 10-15 semantic properties per synset, snapped to curated vocabulary, 6 property types (physical, behaviour, effect, functional, emotional, social) |
| Eval | Python evaluators against DB | MRR via API, aptness via direct DB queries (no API dependency); combined baseline JSON with provenance |
| Deployment | Caddy + systemd | Auto-HTTPS via Let's Encrypt, reverse proxy to Go API |
| Local storage | IndexedDB | User preferences, no accounts in MVP |

Key conventions: FP over OOP, UK English spelling, TDD with frequent atomic commits, idempotent batch operations.

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Milestone Sequence

- [x] Sprint Zero — Backend API, data pipeline foundations, staging deployment
- [ ] M001-yywgwj: Automated Eval Harness — discriminative aptness evaluator + parameter sweep, replacing MRR as primary KPI
  - [x] S01: V2 Foundation + Aptness Evaluator — V2 enrichment imported, MUNCH preprocessed, aptness evaluator + combined baseline shipped, V2 DB live on staging-next
  - [ ] S02: Parameter Sweep Harness
  - [ ] S03: Baseline and Sensitivity Validation
  - [ ] S04: Baseline and Sensitivity Validation
- [ ] M2 (queued): Asymmetric Ortony Scoring — vehicle-side salience weighting in forge scoring
- [ ] M3 (queued): Cascade Gate-and-Rank — concreteness gate → Ortony rank → domain distance re-rank
- [ ] M4 (queued): Type-Aligned Structural Matching — property type diversity bonus in scoring
- [ ] M5 (queued): Novelty Tracking — MuseScorer-style dynamic buckets + creative yield curve
