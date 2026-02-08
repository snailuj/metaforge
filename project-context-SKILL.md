---
name: project-metaforge-context
description: Use when working on Metaforge and need context about current state or next steps. Phase 1 MVP frontend complete — 3D force graph + HUD wired to Go API. All code review issues addressed. Includes prioritised next steps.
triggers: thesaurus, frontend, Go API, design system, metaforge context
---

# Metaforge Context

> **MULTI-AGENT FILE:** This context is shared between agents on different machines (local dev + Claudius remote). Read before writing. Merge your updates — do NOT overwrite. Preserve other agents' notes, decisions, and open questions.

**Last saved:** 2026-02-07 (Claudius — Phase 1 MVP complete)

## Current State

**Phase 1 MVP frontend complete on `sprint-zero` branch.** Browser-based visual thesaurus with 3D force-directed graph + HUD results panel, wired to existing Go headless API.

- **75 tests passing** (26 TypeScript via vitest, 49 Go)
- **TypeScript coverage:** 44% statements (100% on API client + graph transform; 0% on WebGL/app shell — expected)
- **Go coverage:** forge 89%, handler 87%, thesaurus 86%, embeddings 90%, db 57%
- **Vite build:** 1340 kB (Three.js dominates — code-splitting is a future optimisation)
- **All code review findings addressed:** C1-C3, M1-M6, m1-m8, N6
- **DB restored** from SQL dump (20 tables, 107K synsets, 185K lemmas)

### Stack
- **Backend:** Go + SQLite + GloVe embeddings + pre-computed similarity matrix
- **Frontend:** Lit + Vite + TypeScript + `3d-force-graph` + `@fluent/bundle`
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
| Fly controls | 3D navigation (not orbit) per PRD |
| 200ms dblclick threshold | Reduced from 300ms, named constant `DBLCLICK_THRESHOLD_MS` |
| Word-as-node-ID | MVP simplification; synset disambiguation deferred |
| `/strings` proxy removed | .ftl served as static asset from `web/public/`, not Go backend |
| TDD enforced | Red/green for all testable components; WebGL exempt (Playwright later) |
| Parallel subagents | Used git worktrees for Tasks 4-9, merged cleanly into sprint-zero |

## Open Questions

- **Browser integration testing** — user testing locally; Playwright e2e planned for future
- **Bundle size** — 1340 kB due to Three.js; needs code-splitting before production
- **db coverage at 57%** — legacy fallback path untestable without v1 DB fixture
- **I3 — single lemma per relation target:** Intentional or needs fix?
- **Antonyms:** `lexrelations` not imported — fast-follow after MVP
- **SUBTLEX-UK:** Needs re-downloading for frequency/rarity data

## Next Steps

1. **Browser integration test** — user testing locally now (Go backend + Vite dev server)
2. **PR sprint-zero -> main** — once integration testing passes
3. **Playwright e2e tests** — for WebGL components (mf-force-graph, mf-app)
4. **Code-splitting** — lazy-load Three.js to reduce initial bundle
5. **Phase 2 features** — Constellation view, Word Hunt (both parked in PRD-2)
6. Download SUBTLEX-UK, restore frequency import
7. Decide prompt direction for 20K enrichment
