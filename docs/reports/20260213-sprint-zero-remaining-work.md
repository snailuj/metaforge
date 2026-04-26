# Sprint Zero Review — Remaining Work

**Date:** 2026-02-13
**Cross-referenced against:** `feat-freq-fam` worktree (current HEAD)
**Source:** `reports/sprint-zero-code-review.md`

## Summary

Of the 35 findings (2 Critical, 14 Important, 19 Minor) plus 19 recommendations from the automated review, 7 items are already resolved on `feat-freq-fam`: `getPropertyIDs` dead code removed (I3 partial), `mf-force-graph.test.ts` added with 11 tests (I7), `idf` column present in schema (I11), `spike_property_vocab.py` and `build_experiment_archive.py` removed from the branch (I10, I12 — N/A), C2 `/` shortcut now guards shadow-rooted inputs, and autocomplete has a real endpoint (I5 partially addressed). Everything else below still needs attention.

---

## Critical

| # | Issue | File(s) | Fix |
|---|-------|---------|-----|
| **C1** | **Double-lookup race** — `setWordHash` fires `hashchange` → second `doLookup` on every search. No guard in `handleHashChange`. | `mf-app.ts:144-149, 192` | Compare `word` against `this.result?.word` (or a `currentWord` field) and bail if equal. |

## Important

| # | Issue | File(s) | Fix |
|---|-------|---------|-----|
| **I1** | **Divergent Fluent strings** — `strings/v1/ui.en-GB.ftl` and `web/public/strings/v1/ui.ftl` are out of sync. 13+ IDs missing from the authoritative file; old-naming IDs (`section-hypernyms`) unused. New filter/rarity strings on feat-freq-fam widen the gap further. | Both `.ftl` files | Decide single source of truth. Sync all IDs. Remove the duplicate. |
| **I2** | **`Tier.String()` panics on out-of-range** — array-index approach with no bounds check. Any invalid `Tier` value crashes the server. | `forge/forge.go:18-19` | Add a bounds check or switch statement. |
| **I3** | **Dead code: `ComputeSynsetDistance`** — `getPropertyIDs` was removed, but `ComputeSynsetDistance` still exists in `embeddings.go` and is only exercised by its own test (not called from production code). | `embeddings/embeddings.go:72-95` | Remove if unused in production, or document as utility. |
| **I4** | **Layer violation: `db` imports `embeddings`** — `db.go` imports `embeddings` for `BlobToFloats`. Upward dependency creates circular-dependency risk. | `db/db.go:14` | Move `BlobToFloats` to a shared util package, or return raw `[]byte` from the query. |
| **I6** | **Results panel overlaps search bar on small screens** — panel starts at `top: 2rem`, search bar ends at ~64px. Collision on narrow viewports. | `mf-results-panel.ts:12-13`, `mf-app.ts:33-34` | Offset panel below search bar, or add a media query. |
| **I8** | **Double-click to navigate in results panel** — `@dblclick` is non-standard for link-like list items. Users expect single-click. | `mf-results-panel.ts:139` | Consider `@click` for the flat results list (keep double-click for 3D graph only). |
| **I9** | **Pipeline tests depend on live DB — no skip markers for CI** | `data-pipeline/scripts/test_*.py` | Add `conftest.py` with `@pytest.mark.requires_db` skip fixture. |
| **I13** | **No `conftest.py`** — tests use inconsistent `sys.path.insert` hacks. | `data-pipeline/scripts/` | Create `conftest.py` to centralise path setup + DB skip markers. |
| **I14** | **`rows.Err()` not checked after scan loop in test** | `embeddings_test.go:67-72` | Add `rows.Err()` check after loop. |

## Minor

| # | Issue | File(s) |
|---|-------|---------|
| **M1** | `Synset.Metonyms` and `Synset.Rarity` placeholder fields never populated | `db/db.go:23,27` |
| **M2** | Handler creates new `Handler` per test (slow) | `handler_test.go` |
| **M3** | `HandleStrings` locale hardcoded to `en-GB` | `handler.go:217` |
| **M4** | `json.NewEncoder(w).Encode(resp)` error not checked | `handler.go:172, 194` |
| **M5** | Redundant `property_similarity` table check on every query | `db/db.go:119-128` |
| **M9** | Hardcoded `backgroundColor('#1a1a2e')` in force graph | `mf-force-graph.ts:55` |
| **M10** | `three-spritetext` double-cast workaround (`as unknown as string`) | `mf-force-graph.ts:73` |
| **M11** | `EDGE_COLOUR` and `LABEL_FONT` hardcoded, should use design tokens | `mf-force-graph.ts:10-11` |
| **M12** | API client doesn't distinguish network errors from `ApiError` | `client.ts:19` |
| **M13** | `mf-results-panel.test.ts` doesn't mock strings | `mf-results-panel.test.ts` |
| **M14** | CSS token `--hud-width: 20rem` vs fallback `320px` — fragile if root font-size differs | `mf-results-panel.ts:15` |
| **M15** | Vite proxy for `/strings` redundant (Vite serves from `public/` first) | `vite.config.ts:17` |
| **M16** | Inconsistent shebang lines across pipeline scripts | Various `data-pipeline/scripts/` |
| **M17** | `import random` inside function body in `curate_benchmark.py` | `curate_benchmark.py:55` |
| **M18** | `from collections import Counter` inside function body | `curate_benchmark.py:93` |
| **M19** | O(n²) Python loop in `store_similarities` (fine for current data, won't scale) | `07_compute_property_similarity.py:87-92` |
| **M20** | Unused/dead string IDs in `strings/v1/ui.en-GB.ftl` | `strings/v1/ui.en-GB.ftl` |

## Recommendations (not tied to specific findings)

| # | Area | Recommendation |
|---|------|---------------|
| **R1** | Go API | Document connection pooling rationale (`SetMaxOpenConns(4)` set, `SetMaxIdleConns`/`SetConnMaxLifetime` not). |
| **R2** | Go API | Add `slog.Error` before 500 responses for request-level debugging. |
| **R3** | Go API | Replace bubble sort in `getSynsetsWithSharedPropertiesLegacy` with `sort.Slice`. |
| **R4** | Security | Add Content-Security-Policy headers (Go server or Caddy). |
| **R5** | Security | Add rate limiting (`chi/middleware.Throttle` or similar) if deployed publicly. |
| **R6** | Deploy | Document production CORS origin configuration. |
| **R7** | Deploy | Document HTTPS requirement for clipboard API. |
