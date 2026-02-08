---
name: project-metaforge-context
description: Use when working on Metaforge and need context about current state or next steps. Phase 1 MVP browser-tested — 3D force graph with labels, debounced search, hit-test fix. Integration bugs resolved. Ready for PR to main.
triggers: thesaurus, frontend, Go API, design system, metaforge context
---

# Metaforge Context

> **MULTI-AGENT FILE:** This context is shared between agents on different machines (local dev + Claudius remote). Read before writing. Merge your updates — do NOT overwrite. Preserve other agents' notes, decisions, and open questions.

**Last saved:** 2026-02-08 (Claudius — integration bug fixes + new features)

## Current State

**Phase 1 MVP browser-tested on `sprint-zero` branch.** User completed manual integration testing — 3 bugs fixed, 2 missing features added.

- **81 tests passing** (32 TypeScript via vitest, 49 Go)
- **TypeScript coverage:** 44% statements (100% on API client + graph transform; 0% on WebGL/app shell — expected)
- **Go coverage:** forge 89%, handler 87%, thesaurus 86%, embeddings 90%, db 57%
- **Vite build:** 1352 kB (Three.js + three-spritetext — code-splitting is future optimisation)
- **All code review findings addressed + integration bugs fixed**
- **DB restored** from SQL dump (20 tables, 107K synsets, 185K lemmas)

### Stack
- **Backend:** Go + SQLite + GloVe embeddings + pre-computed similarity matrix
- **Frontend:** Lit + Vite + TypeScript + `3d-force-graph` + `three-spritetext` + `@fluent/bundle`
- **DB restore:** `data-pipeline/scripts/restore_db.sh` (87 MB SQL dump)

### Key files
- Phase 1 plan: `docs/plans/20260207-phase1-force-graph-mvp.md`
- PRD: `Metaforge-PRD-2.md` (authoritative)
- Reports: `reports/` (task reports + code review)
- Coverage docs: `TESTING.md`

## Key Decisions

| Decision | Detail |
|----------|--------|
| Synonyms as RelatedWord | `[]RelatedWord{Word, SynsetID}` not `[]string` — needed for navigation |
| Fluent for all UI strings | `web/public/strings/v1/ui.ftl`, components use `getString()` via property threading |
| Hash routing | `#/word/<term>` for deep linking, no router library |
| Fly controls | 3D navigation (not orbit) per PRD; mouse look requires button hold (user-approved deviation) |
| 200ms dblclick threshold | Reduced from 300ms, named constant `DBLCLICK_THRESHOLD_MS` |
| Word-as-node-ID | MVP simplification; synset disambiguation deferred |
| TDD enforced | Red/green for all testable components; WebGL exempt (Playwright later) |
| Explicit renderer sizing | Must call `.width()/.height()` + ResizeObserver — library defaults to window dimensions |
| Debounced search | 300ms debounce, min 3 chars; Enter bypasses for immediate submit |
| stopPropagation on search input | Prevents FlyControls WASD capture while typing |
| three-spritetext for labels | Always-visible word labels above nodes, coloured by relation type |

## Open Questions

- **Bundle size** — 1352 kB due to Three.js; needs code-splitting before production
- **db coverage at 57%** — legacy fallback path untestable without v1 DB fixture
- **I3 — single lemma per relation target:** Intentional or needs fix?
- **Antonyms:** `lexrelations` not imported — fast-follow after MVP
- **SUBTLEX-UK:** Needs re-downloading for frequency/rarity data

## Next Steps

1. **PR sprint-zero -> main** — integration testing complete, ready for PR
2. **Playwright e2e tests** — for WebGL components (mf-force-graph, mf-app)
3. **Code-splitting** — lazy-load Three.js to reduce initial bundle
4. **Phase 2 features** — Constellation view, Word Hunt (both parked in PRD-2)
5. Download SUBTLEX-UK, restore frequency import
6. Decide prompt direction for 20K enrichment
