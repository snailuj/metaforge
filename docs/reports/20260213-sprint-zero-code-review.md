# Sprint Zero Code Review — Automated Agent Review

**Date:** 2026-02-13
**Scope:** 92 files, ~11,000 lines of code across Go API, Lit/TS frontend, Python pipeline
**Methodology:** 4-agent parallel review using superpowers:code-reviewer criteria. Each agent read every file in their domain and produced an independent report. A team lead consolidated findings.

| Agent | Domain | Files Reviewed |
|-------|--------|----------------|
| go-reviewer | Go API (`api/`) | ~14 files (handlers, db, forge, thesaurus, embeddings) |
| frontend-reviewer | Frontend (`web/src/`) | ~25 files (Lit components, graph, API client, strings) |
| pipeline-reviewer | Data Pipeline (`data-pipeline/`) | ~25 files (Python scripts, tests, shell scripts) |
| cross-cutting-reviewer | Security + Integration | All files (security scan, API contracts, Fluent strings, config) |

---

## Summary

| Severity | Count |
|----------|-------|
| **Critical** | 2 |
| **Important** | 14 |
| **Minor** | 19 |

**Overall verdict: Ready to merge with fixes.**

No security vulnerabilities found. No data loss risks. Architecture is sound across all three layers. The implementation significantly exceeds the Sprint Zero plan scope with performance optimisations, i18n, and a thesaurus endpoint.

---

## Consolidated Findings

### Critical Issues (2)

| # | Area | Issue | Impact |
|---|------|-------|--------|
| **C1** | Frontend | **Double-lookup race** -- `setWordHash` triggers `hashchange` -> second `doLookup` on every search | Doubled API calls, graph jitter on every search |
| **C2** | Frontend | **`/` shortcut steals focus** from shadow-rooted inputs -- `document.activeElement` doesn't recurse into Shadow DOM | Will break any future shadow-rooted text input |

### Important Issues (14)

| # | Area | Issue |
|---|------|-------|
| **I1** | Cross-cutting | **Divergent Fluent strings files** -- `strings/v1/ui.en-GB.ftl` missing 13 IDs the frontend uses. Production would show raw IDs |
| **I2** | Go API | `Tier.String()` panics on out-of-range values |
| **I3** | Go API | Dead code: `getPropertyIDs` and `ComputeSynsetDistance` unused |
| **I4** | Go API | Layer violation: `db` imports `embeddings` (upward dependency) |
| **I5** | Frontend | `suggest` flag wired through but no lightweight endpoint -- full lookup on every debounced keystroke |
| **I6** | Frontend | Results panel overlaps search bar on small screens |
| **I7** | Frontend | No test file for `mf-force-graph` -- click timer logic untested |
| **I8** | Frontend | Double-click to navigate in results panel is non-standard (single-click expected for link-like elements) |
| **I9** | Pipeline | Tests depend on live DB -- no skip markers for CI |
| **I10** | Pipeline | Connection leak in `spike_property_vocab.py` -- no `try/finally` |
| **I11** | Pipeline | `ALTER TABLE ADD COLUMN` for `idf` not in schema definition |
| **I12** | Pipeline | Dead code in `build_experiment_archive.py` (importlib block) |
| **I13** | Pipeline | No `conftest.py` -- tests use `sys.path.insert` inconsistently |
| **I14** | Go API | `rows.Err()` not checked after scan loop in `embeddings_test.go` |

### Minor Issues (19)

Across all areas -- code style, hardcoded colours/fonts that should use tokens, unused strings in `.ftl`, inconsistent shebangs, etc. Full details in individual reviewer sections below.

---

## Recommended Fix Priority

**Before merge:**
1. Fix C1 (double-lookup) -- guard `handleHashChange` against current word
2. Fix I1 (sync Fluent strings) -- single source of truth for string IDs

**Fast-follow:**
3. Fix C2 (`/` shortcut shadow DOM recursion)
4. Fix I2 (Tier.String panic guard)
5. Remove dead code (I3, I12)
6. Add `mf-force-graph.test.ts` (I7)
7. Add pipeline `conftest.py` with skip markers (I9, I13)
8. Fix connection leak (I10)

---

## Strengths Highlighted Across All Reviews

- **Security posture is excellent** -- parameterised SQL everywhere, no secrets in code, XSS mitigated by Lit auto-escaping, server bound to localhost, CORS scoped
- **Go mega-query** eliminated the N+1 pattern from the original plan -- major performance win
- **Test coverage is strong** -- 38+ Go tests, 54+ frontend tests, comprehensive pipeline tests
- **Clean architecture** -- well-separated packages/components with single responsibilities
- **Production-aware** -- server timeouts, graceful error handling, memory leak prevention in Three.js cleanup, idempotent pipeline operations

---

---

## Go API Review (go-reviewer)

### Strengths

1. **Clean package structure** -- `db`, `embeddings`, `forge`, `handler`, `thesaurus` are well separated. Each package has a single responsibility and clean interfaces between them. The `internal/` directory prevents external imports.

2. **Evolved past the Sprint Zero plan** -- The implementation significantly improved on the original plan:
   - `GetForgeMatches` (`db/db.go:293-386`) is a **mega-query** that eliminates the N+1 pattern the plan originally prescribed (plan Task 4 showed per-candidate `GetSynset` + `GetLemmaForSynset` + `ComputePropertySetDistance` calls). This is a major performance win.
   - `NormaliseDistances` (`forge/forge.go:70-98`) addresses the real-world clustering issue where shared-property candidates naturally cluster near each other in embedding space, making absolute distance thresholds meaningless.
   - Pre-computed `synset_centroids` and `property_similarity` tables moved heavy computation into the data pipeline where it belongs.

3. **Robust NULL handling** -- `db/db.go:41-69` properly uses `sql.NullString` for nullable enrichment fields (connotation, register, usage_example). The original plan had these scanned directly into strings, which would panic on NULL.

4. **Solid error handling throughout** -- Errors are wrapped with context (`fmt.Errorf("...: %w", err)`) consistently. `rows.Err()` is checked after iteration in `db.go:92-94`, `embeddings.go:122-124`, and `thesaurus.go:129`. The `slog.Warn` for non-fatal scan errors (e.g. `db.go:86`, `embeddings.go:114`) is appropriate -- one bad row shouldn't kill the whole request.

5. **Security-conscious design**:
   - Server binds to `127.0.0.1` only (`main.go:44`), not `0.0.0.0`.
   - Database opened read-only (`db.go:33`: `?mode=ro`).
   - Directory traversal protection in `HandleStrings` (`handler.go:208-210`).
   - CORS properly scoped to a single configurable origin (`handler.go:231-246`).
   - All SQL uses parameterised queries -- no injection risk.
   - Server has `ReadTimeout` and `WriteTimeout` (`main.go:48-49`).

6. **Thesaurus implementation is efficient** -- `thesaurus.go` uses only 2 queries total: one for senses+synonyms via GROUP_CONCAT, one bulk query for all relations. Properly builds IN clause with parameterised placeholders (`thesaurus.go:139-146`).

7. **Excellent test coverage** -- 38+ tests covering:
   - Happy paths, error cases (not found, empty, whitespace)
   - Edge cases (`BlobToFloatsNil`, `BlobToFloatsWrongSize`, `CosineDistanceZeroVector`, `CosineDistanceOppositeVectors`)
   - Integration tests against real database
   - Structural validation (deduplication, sort order, limit respected)
   - Security tests (directory traversal, CORS preflight)
   - Input validation (invalid/negative threshold, non-numeric limit, zero limit)

8. **Table validation at startup** -- `handler.go:41-49` checks all required tables exist before serving, giving a clear error message rather than cryptic SQL failures.

### Issues

#### Critical (Must Fix)

**None found.** No bugs, security holes, or data loss risks identified.

#### Important (Should Fix)

1. **`Tier.String()` panics on out-of-range values** -- `forge/forge.go:18-20`
   - `[...]string{...}[t]` will panic with an index-out-of-range if `t` is ever an unexpected value (e.g. from future code changes or deserialization).
   - **Why it matters:** Runtime panic crashes the server.
   - **Fix:** Add bounds checking or use a switch statement.

2. **`getSynsetsWithSharedPropertiesLegacy` uses bubble sort** -- `db/db.go:241-247`
   - Bubble sort is O(n^2). The comment says "adequate for small result sets" but the legacy path scans ALL enrichment rows, so `matches` could be large.
   - **Why it matters:** Performance degradation if legacy path is ever hit with large datasets.
   - **Fix:** Use `sort.Slice` (already used elsewhere in the codebase, e.g. `forge.go:105`).

3. **`getPropertyIDs` is unused** -- `db/db.go:346-364`
   - This function remains from the original plan but was superseded by the mega-query and similarity-matrix approach. It's dead code.
   - **Why it matters:** Dead code increases maintenance burden and confusion.
   - **Fix:** Remove it.

4. **`db` package imports `embeddings` package** -- `db/db.go:15`
   - `db.go` imports `embeddings` to call `BlobToFloats` in `GetForgeMatches`. This creates a dependency from the lower-level `db` layer up to `embeddings`, coupling database access to embedding logic.
   - **Why it matters:** Makes it harder to test `db` in isolation and creates a circular dependency risk if `embeddings` ever needs `db` (which it already does for `GetPropertyEmbedding`).
   - **Fix:** Move `BlobToFloats` to a shared utility package, or have `GetForgeMatches` return raw `[]byte` blobs and let the caller decode them.

5. **`ComputeSynsetDistance` in `embeddings.go:76-95` appears unused** -- it was the original approach before the mega-query with pre-computed centroids. The handler now computes distances in-memory from centroids returned by `GetForgeMatches`.
   - **Why it matters:** Dead code. The function also makes N+1 DB queries per call.
   - **Fix:** Remove if no longer needed, or mark as utility for future use.

6. **No `rows.Err()` check after `TestComputeSynsetDistance` scan loop** -- `embeddings_test.go:67-72`
   - The test scans rows but doesn't check `rows.Err()` after iteration.
   - **Why it matters:** Silent test failures if row iteration errors occur.
   - **Fix:** Add `if err := rows.Err(); err != nil { t.Fatalf(...) }` after the loop.

#### Minor (Nice to Have)

1. **`Synset.Metonyms` and `Synset.Rarity` placeholder fields** -- `db/db.go:23,27`
   - These fields are declared with comments saying "Placeholder: ... pending" but are never populated.
   - **Why it matters:** Adds noise to the API response (though `omitempty` prevents them from appearing in JSON).
   - **Suggestion:** Keep as-is if the data pipeline will soon populate them; otherwise consider removing.

2. **Handler creates new `Handler` per test** -- `handler_test.go` creates a new `NewHandler(testDBPath)` in every test function.
   - **Why it matters:** Opens and validates the DB connection 15+ times. Tests would run faster with `TestMain` setup/teardown.
   - **Suggestion:** Low priority since tests are integration tests and the DB is read-only.

3. **`HandleStrings` locale is hardcoded to `en-GB`** -- `handler.go:217`
   - The `.en-GB.ftl` suffix is hardcoded. No `Accept-Language` header parsing.
   - **Why it matters:** Only matters when i18n is needed. Fine for MVP.

4. **`json.NewEncoder(w).Encode(resp)` error not checked** -- `handler.go:172`, `handler.go:194`
   - `Encode` can return errors (e.g. if the connection is closed).
   - **Why it matters:** Very unlikely to cause real problems, but violates the "all errors checked" principle.

5. **`GetSynsetsWithSharedProperties` checks for `property_similarity` table at query time** -- `db/db.go:119-128`
   - This check runs on every call to `GetSynsetsWithSharedProperties`. Since the handler already validates table existence at startup, this is redundant for the normal path.
   - **Suggestion:** Could be removed since `NewHandler` already validates, or cached as a one-time check.

6. **CosineDistance uses `float64(a[i]) * float64(b[i])` for precision** -- `embeddings.go:59`
   - Good precision approach. The original plan had `float64(a[i] * b[i])` which multiplies in float32 precision first, then widens. The current code correctly widens before multiplying.

### Requirements Check (Sprint Zero Plan)

| Deliverable | Status |
|------------|--------|
| DB layer for lexicon_v2.db junction table | **Complete** -- plus evolved to mega-query |
| FastText 300d embeddings layer | **Complete** -- plus pre-computed centroids |
| 5-tier matching algorithm | **Complete** -- plus normalised distances |
| `/forge/suggest` HTTP endpoint | **Complete** -- with `threshold` and `limit` params |
| Main server with chi router | **Complete** -- with timeouts, CORS, structured logging |
| `/thesaurus/lookup` endpoint | **Complete** -- not in original Sprint Zero plan, bonus |
| `/strings/*` endpoint | **Complete** -- not in original plan, supports i18n |
| `/health` endpoint | **Complete** |
| All tests passing | **38+ tests** across all packages |

The implementation exceeds the Sprint Zero plan scope in positive ways (thesaurus endpoint, strings endpoint, mega-query optimisation, normalised distances, pre-computed centroids, input validation, CORS, structured logging).

### Recommendations

1. **Remove dead code** -- `getPropertyIDs` and potentially `ComputeSynsetDistance` are no longer used by any production path.
2. **Break the `db` -> `embeddings` import** -- Move `BlobToFloats` to avoid layering violation.
3. **Add a panic guard to `Tier.String()`** -- Bounds check or switch.
4. **Consider connection pooling configuration** -- `SetMaxOpenConns(4)` is set but `SetMaxIdleConns` and `SetConnMaxLifetime` are not. For read-only SQLite this is fine, but worth documenting the reasoning.
5. **Add request-level logging** -- The chi `middleware.Logger` logs requests, but error responses don't log the underlying error (e.g. `handler.go:114` returns 500 but doesn't log what `GetSynset` returned). Adding `slog.Error` before error responses would help debugging.

### Assessment

**Ready to merge?** Yes, with minor fixes.

**Reasoning:** The code is production-quality with clean architecture, solid error handling, comprehensive tests, and no security issues. The implementation significantly improved on the Sprint Zero plan with performance optimisations (mega-query, pre-computed centroids, normalised distances). The important issues (dead code, Tier.String panic risk, layer coupling) are non-blocking but should be addressed in follow-up commits. The codebase is well-structured for the Phase 1 frontend work to build on.

---

## Frontend Review (frontend-reviewer)

### Strengths

1. **Clean component architecture** -- Clear separation into `mf-app` (orchestrator), `mf-search-bar` (input), `mf-force-graph` (3D visualisation), `mf-results-panel` (HUD), and `mf-toast` (notifications). Each component has a single well-defined responsibility. (`web/src/components/`)

2. **Proper Lit patterns** -- Correct use of `@state()` for private reactive state and `@property()` for public API. Events use `bubbles: true, composed: true` correctly for crossing Shadow DOM boundaries. (`mf-search-bar.ts:138-144`, `mf-results-panel.ts:105-111`)

3. **Shadow DOM awareness** -- The `/` keyboard shortcut handler in `mf-search-bar.ts:69-82` explicitly accounts for Shadow DOM's `activeElement` behaviour, with a clear comment explaining why. This is a common footgun handled correctly.

4. **FlyControls isolation** -- `mf-search-bar.ts:106-107,127-129` stops both `keydown` and `keyup` propagation from the input to prevent 3D camera controls from capturing keyboard events. Both are needed since FlyControls listens to both. Well thought through.

5. **Graph transform is well-tested** -- `transform.test.ts` covers central node creation, deduplication, self-reference filtering, priority-based capping, and empty input. 8 test cases with meaningful assertions. (`web/src/graph/transform.test.ts`)

6. **Fluent i18n from day one** -- All user-visible strings go through `getString()` with `@fluent/bundle`. Graceful degradation: returns the message ID if the bundle isn't loaded. (`web/src/lib/strings.ts:34-44`)

7. **API client validates response shape** -- `client.ts:27-29` checks for `data.word` string and `data.senses` array before casting. Protects against upstream API changes.

8. **Design tokens well-structured** -- `tokens.css` defines a complete token set. CSS fallbacks are provided inline in component styles (e.g. `var(--colour-bg-primary, #1a1a2e)`), so components work even without the token stylesheet.

9. **Hash-based routing** -- `mf-app.ts:94-99,107-124` supports `#/word/fire` deep linking with proper encoding/decoding. Cleanup on `disconnectedCallback`.

10. **Thorough test coverage** -- Search bar tests (`mf-search-bar.test.ts`) cover debounce timing, Enter bypass, Escape cancellation, event propagation blocking, empty input rejection, and timer reset. 10 test cases. Toast tests cover show/hide lifecycle, custom duration, timer reset on multiple calls.

11. **WebGL mock strategy** -- The `chainable` Proxy in `mf-app.test.ts:6` is an elegant solution for mocking the 3d-force-graph fluent API without WebGL. Any chained method call returns the proxy itself.

12. **Memory leak prevention** -- `mf-force-graph.ts:132-145` properly cleans up: clears click timer, disconnects ResizeObserver, pauses animation, and disposes the Three.js renderer.

### Issues

#### Critical (Must Fix)

**1. Double-lookup race on search -- `mf-app.ts:94-99,107-112,119-124,146-168`**

When `doLookup` succeeds, it calls `this.setWordHash(word)` at line 157. This triggers the `hashchange` listener at line 107, which calls `doLookup` again with the same word. Every successful search fires the API call **twice**.

- **Why it matters:** Doubled network requests, potential flicker, wasted bandwidth. On slow connections the second lookup could resolve after the user has navigated elsewhere, causing a stale state.
- **How to fix:** Guard against re-lookup of the current word. Add a check in `handleHashChange` comparing against `this.result?.word`, or store a `currentWord` state to skip redundant lookups. The test at `mf-app.test.ts:78` already works around this by using `mockResolvedValue` (not `Once`) with a comment acknowledging the double-call.

**2. No `/` shortcut guard for shadow-rooted inputs other than self -- `mf-search-bar.ts:69-82`**

The global `/` handler checks `document.activeElement` for `HTMLInputElement`, `HTMLTextAreaElement`, and `contenteditable`. But if another Shadow DOM component (e.g. a future modal or form) has a focused input, `document.activeElement` will point to that component's host element, NOT the inner input. The check on lines 73-76 won't match, and `/` will steal focus.

- **Why it matters:** As the app grows, any shadow-rooted text input will lose focus when the user types `/`.
- **How to fix:** Check `document.activeElement?.shadowRoot?.activeElement` recursively, or use a simpler approach like only activating `/` when no element has focus (i.e., `document.activeElement === document.body`).

#### Important (Should Fix)

**3. `suggest` parameter ignored by API client -- `mf-app.ts:127,146`**

`handleSearch` receives `e.detail.suggest` and passes it to `doLookup`, but `doLookup` only uses it to control the loading state (lines 147-150) and error handling (line 160). The actual `lookupWord()` call at line 153 always calls the same `/thesaurus/lookup` endpoint. The debounced "suggest" mode sends a full lookup request rather than a lighter autocomplete/suggest endpoint.

- **Why it matters:** Every keystroke (after 3 chars + 200ms debounce) fires a full thesaurus lookup. This could be expensive on the backend. The `suggest` flag implies there should be a lighter endpoint.
- **How to fix:** Either implement a dedicated `/thesaurus/suggest` endpoint for lightweight autocomplete, or document that full lookups are intentional for the MVP and remove the suggest flag to avoid confusion.

**4. Results panel overlaps search bar on small screens -- CSS layout**

`mf-results-panel.ts:12-13` positions the panel at `top: var(--space-xl, 2rem)` from the top. `mf-app.ts:33-34` positions the search bar at `top: var(--space-md, 1rem)`. On any screen, the results panel and search bar will overlap vertically since they start at nearly the same Y position.

- **Why it matters:** On screens narrower than ~800px, the 320px panel + search bar will compete for space. Even on wider screens, the panel header overlaps the search bar's vertical space.
- **How to fix:** Position the results panel below the search bar (e.g. `top: calc(var(--space-md) + 4rem)`), or use a media query to reposition on small screens.

**5. No test for `mf-force-graph` -- `web/src/components/`**

The force graph component has no test file. While WebGL makes unit testing hard, the component contains testable business logic: the double-click vs single-click timer logic (lines 66-86), resize syncing, and cleanup. The mock in `mf-app.test.ts` only proves the component can be instantiated.

- **Why it matters:** The click timer logic is subtle (300ms threshold) and could regress. The cleanup logic (disposing renderer, disconnecting observer) is critical for memory leaks.
- **How to fix:** Create `mf-force-graph.test.ts` using the same chainable proxy mock. Test: (a) single click fires `mf-node-select` after 300ms, (b) double click fires `mf-node-navigate` without `mf-node-select`, (c) right click fires `mf-node-copy`, (d) `disconnectedCallback` cleans up timers/observers.

**6. `mf-results-panel` word chips use `@dblclick` requiring mouse -- `mf-results-panel.ts:139`**

The word chips require a double-click to navigate. The `keydown` handler (line 141) maps Enter to the same action, which is good for accessibility. However, single-click does nothing -- users will expect a single click to navigate (standard web behaviour). Double-click is non-standard for link-like elements.

- **Why it matters:** UX confusion. Users will click a word chip once and nothing happens. The double-click convention from the 3D graph (where it makes sense to distinguish select vs navigate) doesn't translate well to a flat list.
- **How to fix:** Consider using single-click (`@click`) for navigation in the results panel, reserving double-click only for the 3D graph nodes.

**7. No loading/error state for the strings fetch -- `mf-app.ts:88-91`**

`initStrings()` is awaited in `connectedCallback`. If the strings fetch fails (network error, 404), `getString()` silently returns message IDs as fallback text, but there's no retry mechanism and no user indication that the UI is degraded.

- **Why it matters:** Users would see raw message IDs like "search-placeholder" instead of actual text. In production behind a CDN this is unlikely, but during development or with aggressive ad blockers it could happen.
- **How to fix:** For MVP this is acceptable since fallback IDs are somewhat readable. Consider adding a `stringsLoaded` state for future defensive rendering.

**8. `@property({ type: Object })` on graphData without equality check -- `mf-force-graph.ts:35`**

Lit's `@property({ type: Object })` uses reference equality by default. Since `transformLookupToGraph` always returns a new object, every call to `doLookup` (including the double-call from issue #1) will trigger `updated()` and re-render the graph.

- **Why it matters:** Re-calling `graphData()` on 3d-force-graph restarts the physics simulation, causing visual jitter. Combined with the double-lookup bug, every search visibly resets the graph twice.
- **How to fix:** Fix issue #1 first (which eliminates most duplicates). For further protection, compare `JSON.stringify` of old vs new data in `updated()` before calling `this.graph.graphData()`.

#### Minor (Nice to Have)

9. **Hardcoded background colour in force graph** -- `mf-force-graph.ts:42`
   - `.backgroundColor('#1a1a2e')` is hardcoded rather than reading from the CSS token `--colour-bg-primary`. The same value is in `tokens.css:3`.
   - **How to fix:** Read the computed style: `getComputedStyle(this).getPropertyValue('--colour-bg-primary').trim() || '#1a1a2e'`

10. **`three-spritetext` type workaround** -- `mf-force-graph.ts:54`
    - `sprite.backgroundColor = false as unknown as string` works but is a double cast.
    - **How to fix:** A `// @ts-expect-error` comment would be cleaner and would break if the upstream types are ever fixed.

11. **`EDGE_COLOUR` and `LABEL_FONT` could use tokens** -- `mf-force-graph.ts:10-11`
    - These are hardcoded constants that duplicate values from `tokens.css`.

12. **API client doesn't handle network errors** -- `client.ts:19`
    - `fetch()` throws a `TypeError` on network failure (DNS, offline). This propagates as a raw `TypeError`, not an `ApiError`. The `mf-app.ts:165` catch block handles it with a generic error message, which is fine, but the error type inconsistency could confuse future error-specific handling.

13. **`mf-results-panel.test.ts` doesn't mock strings** -- line 1
    - Unlike `mf-app.test.ts`, the results panel test doesn't mock `@/lib/strings`. It imports the real `getString()` which returns message IDs before `initStrings` is called. Tests still pass because they don't assert on label text, but test output may contain raw IDs like "results-synonyms" rather than "Synonyms".

14. **CSS token `--hud-width: 20rem`** -- `tokens.css:40`
    - The results panel uses `width: var(--hud-width, 320px)` (line 16). `20rem` = 320px at default 16px base, but if the user has a different base font size, these won't match. The fallback should be `20rem` not `320px`, or the token should be `320px`.

15. **`vite.config.ts` proxies `/strings` to Go API** -- line 17
    - The strings file is in `web/public/strings/v1/ui.ftl`. In dev, Vite serves from `public/` directly -- no proxy needed. But `/strings` is also proxied to `:8080`. If the Go API doesn't serve this path, the proxy will fail silently and Vite's own static file serving will handle it. Harmless but confusing.

### Recommendations

1. **Fix the double-lookup issue first** (Critical #1) -- it causes double API calls and double graph re-renders on every search.
2. **Add `mf-force-graph.test.ts`** -- the click timing logic is the most complex untested code.
3. **Consider single-click for results panel navigation** -- double-click is non-standard for link-like UI elements outside the 3D graph context.
4. **Document the `suggest` flag intent** -- either implement a lighter suggest endpoint or remove the flag to avoid confusion.
5. **Extract hardcoded colours/fonts from `mf-force-graph.ts`** into CSS custom property reads for theme consistency.

### Assessment

**Ready to merge?** With fixes.

**Reasoning:** The codebase is well-structured with clean separation of concerns, thorough testing (except for the force graph), proper accessibility attributes, and correct Shadow DOM patterns. The critical double-lookup bug should be fixed before merge as it causes visible jitter and doubled API calls. The shadow-rooted input focus-steal (Critical #2) is a latent bug that will bite when the app grows but is acceptable for MVP if documented. Everything else is polish that can follow in subsequent PRs.

---

## Data Pipeline Review (pipeline-reviewer)

### Strengths

1. **Pipeline orchestration is solid**
   - `run_pipeline.sh` uses `set -euo pipefail` (line 18), has a `--check` mode for prerequisite validation, confirms before spending API credits with `--full`, and validates all raw sources upfront before any work begins. This is well above average for a data pipeline shell script.

2. **Consistent resource cleanup across all scripts**
   - Every Python script that opens SQLite connections uses `try/finally` to ensure `conn.close()` is called: `import_oewn.py:63-73`, `import_syntagnet.py:50-66`, `import_verbnet.py:79-90`, `curate_properties.py:99-130`, `06_compute_property_idf.py:125-130`, `07_compute_property_similarity.py:116-131`, `08_compute_synset_centroids.py:98-114`.

3. **SQL injection prevention**
   - Every SQL operation uses parameterised queries (`?` placeholders). No string interpolation for user data. Clean throughout.

4. **Idempotent operations**
   - `INSERT OR IGNORE` / `INSERT OR REPLACE` used consistently across import scripts.
   - `restore_db.sh` removes and recreates the DB from scratch, making it truly idempotent.
   - `07_compute_property_similarity.py:25` and `08_compute_synset_centroids.py:25` both `DROP TABLE IF EXISTS` before re-creating, so they're safely re-runnable.

5. **Shared utilities keep things DRY**
   - `utils.py` centralises path resolution and constants (`EMBEDDING_DIM`, `LEXICON_V2`, `SQLUNET_DB`, `FASTTEXT_VEC`). All scripts import from it.

6. **A/B enrichment tooling is well-designed**
   - `enrich_ab.py` has: tenacity retry with exponential backoff (line 208-215), checkpointing for crash resume (lines 193-203, 321-334), variant C explicitly isolates the count variable (line 131 comment). This is genuinely thoughtful experimental design.

7. **Good test coverage with unit + integration separation**
   - `test_curate_properties.py` has both integration tests against the real DB (lines 14-70) AND pure unit tests with synthetic data (lines 76-134).
   - `test_07_compute_property_similarity.py` and `test_08_compute_synset_centroids.py` both test with in-memory DBs / synthetic numpy arrays in addition to real-DB checks.

8. **`normalise()` function in utils.py**
   - Simple but consistently used across the pipeline for property text canonicalisation.

### Issues

#### Critical (Must Fix)

**None found.** No security issues, no data loss risks, no secrets in code.

#### Important (Should Fix)

**1. Tests depend on live database -- no fixtures for CI**
- Files: `test_import_oewn.py`, `test_import_syntagnet.py`, `test_import_verbnet.py`, `test_synset_properties.py`, `test_validation.py`
- All integration tests open `LEXICON_V2` directly (e.g., `test_import_oewn.py:10-11`). If the DB doesn't exist (fresh clone, CI runner), all tests fail with a cryptic SQLite error.
- **Why it matters:** Can't run tests in CI without first running the full pipeline or having the DB available. The TDD workflow specified in CLAUDE.md assumes tests can be run independently.
- **Fix:** Add a pytest `conftest.py` with a `skip_if_no_db` marker or a shared fixture that `pytest.skip()`s when `LEXICON_V2` doesn't exist. This makes the test suite gracefully degrade on environments without the DB.

**2. `test_validation.py:41` uses f-string in SQL -- potential table name injection**
- `count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]`
- The `table` value comes from the hardcoded `expected` dict on line 29, so there's no actual injection risk here. However, this is a bad pattern that could be copy-pasted unsafely.
- **Fix:** Since table names can't be parameterised in SQLite, add a comment noting the dict is hardcoded, or validate `table` against a whitelist of known tables.

**3. `spike_property_vocab.py:240` -- connection not closed in `finally`**
- `conn = sqlite3.connect(SQLUNET_DB)` on line 177, but `conn.close()` is on line 240 *after* all the processing -- not in a `finally` block. If `get_pilot_synsets()` or LLM calls throw, the connection leaks.
- **Fix:** Wrap in `try/finally` like the other scripts do.

**4. `import_oewn.py` -- loads entire result sets into memory**
- Lines 15, 31, 48: `rows = [... for row in cursor]` materialises the full result set before inserting. With 107k synsets, 185k lemmas, and 234k relations, this uses significant RAM.
- **Why it matters:** On memory-constrained environments (CI runners, small VPS), this could OOM.
- **Fix:** Use chunked inserts or `executemany()` directly with the cursor iterator (the cursor itself is iterable).

**5. `06_compute_property_idf.py` -- `ALTER TABLE ADD COLUMN` isn't in the schema**
- The `idf` column is dynamically added at runtime (line 31) rather than being defined in `schema-v2.sql`. This means:
  - The SQL dump includes it (since it dumps the full DB), but a fresh restore + re-run might have ordering issues.
  - The schema file doesn't document this column.
- **Fix:** Add `idf REAL` to the `property_vocabulary` table definition in `schema-v2.sql`.

**6. `test_property_vocab_spike.py` -- depends on `property_spike.json` existing**
- `SPIKE_OUTPUT = Path(__file__).parent.parent / "output" / "property_spike.json"` (line 7). These tests will fail if the spike hasn't been run. And the spike requires a Gemini API key.
- **Fix:** Same as I1 -- add a skip marker when the file doesn't exist.

**7. `build_experiment_archive.py` -- dead import code**
- Lines 162-173: Imports `importlib.util`, `types`, creates `spec` and `mod` variables, but never actually uses them (falls through to reading the file as text on line 172). Dead code should be removed.

**8. No `conftest.py` to set up `sys.path`**
- Multiple test files use `sys.path.insert(0, str(Path(__file__).parent))` (e.g., `test_06_compute_property_idf.py:7`, `test_07_compute_property_similarity.py:7`, `test_08_compute_synset_centroids.py:7`). Meanwhile other test files use `from utils import ...` without the path manipulation, relying on CWD.
- **Fix:** Add a `conftest.py` in `data-pipeline/scripts/` that sets up the path once.

#### Minor (Nice to Have)

1. **`curate_benchmark.py:55` -- `import random` inside function body**
   - The `import random` is inside `select_benchmark()`. While it works, module-level imports are conventional and clearer.

2. **`compare_ab.py` -- `print_comparison` hardcodes "A" and "B" labels**
   - Lines 122-123: Header says "A = Original prompt (5-10 properties)", "B = Dual-dimension prompt (10-15 properties)". Doesn't account for comparing A vs C or B vs C. Low priority since this is an analysis tool, not production code.

3. **Inconsistent shebang lines**
   - `06_compute_property_idf.py`, `07_compute_property_similarity.py`, `08_compute_synset_centroids.py` have `#!/usr/bin/env python3` shebangs. Other scripts (`import_oewn.py`, `curate_properties.py`, etc.) don't.

4. **`curate_benchmark.py:93` -- `from collections import Counter` inside function body**
   - Same pattern as M1, import belongs at module level.

5. **`test_curate_properties.py:9` -- `sys.path.insert` only needed because tests run from varying CWDs**
   - Would be cleaner with a shared conftest.py (overlaps with I8).

6. **`07_compute_property_similarity.py` -- O(n^2) loop in Python for `store_similarities`**
   - Lines 87-92: Double `for` loop over all property pairs. With ~4k properties with embeddings, that's ~8M iterations. The similarity matrix computation itself is efficiently vectorised with NumPy (line 73), but the pair extraction is pure Python. This is likely fine for current data sizes (~5k properties), but could become a bottleneck at scale.

### Recommendations

1. **Add a `conftest.py`** in `data-pipeline/scripts/` that:
   - Sets up `sys.path` once
   - Provides a `@pytest.mark.requires_db` marker that skips when `LEXICON_V2` doesn't exist
   - Provides a `@pytest.mark.requires_spike` marker for spike-dependent tests

2. **Add `idf REAL` to `schema-v2.sql`** so the schema file is the single source of truth.

3. **Fix the connection leak in `spike_property_vocab.py`** -- wrap the main logic in `try/finally`.

4. **Remove dead imports in `build_experiment_archive.py`** (lines 162-170).

5. **Move module-level imports to top of file** in `curate_benchmark.py` (minor cleanup).

### Assessment

**Ready to merge?** Yes, with minor fixes.

**Reasoning:**
- No critical issues found. No security vulnerabilities, no secrets in code, no data corruption paths.
- The pipeline is well-structured with clear phase separation, consistent error handling, and idempotent operations.
- SQL is properly parameterised throughout.
- The most important fix is I1/I6 (test skip markers for missing DB/files) to prevent false failures in CI. I3 (connection leak in spike script) should also be fixed. The remaining items are code hygiene improvements.
- The A/B testing infrastructure (`enrich_ab.py`, `compare_ab.py`, `curate_benchmark.py`, `build_experiment_archive.py`) shows solid experimental methodology with checkpoint/resume, reproducible seeds, and structured archival -- good engineering for a research-adjacent pipeline.
- Test quality is good: both integration tests against real data and isolated unit tests with synthetic fixtures are present for the compute scripts.

---

## Cross-Cutting Review (cross-cutting-reviewer)

### Strengths

1. **SQL injection: excellent.** All Go SQL queries use parameterised queries (`?` placeholders) throughout `db.go`, `thesaurus.go`, `embeddings.go`, and `handler.go`. The one dynamic SQL in `thesaurus.go:152` (`queryRelations` IN clause) is built safely with `"?"` placeholders and an `args` slice -- no string interpolation of user input.

2. **No hardcoded secrets.** All Python scripts (`enrich_ab.py`, `spike_property_vocab.py`) load the Gemini API key from `os.environ.get('GEMINI_API_KEY')` and fail explicitly if missing. The Go API has no secrets at all. The `.gitignore` covers `.db` files and common sensitive patterns.

3. **XSS protection: strong.** All Lit templates use Lit's built-in `html` tagged template literals which auto-escape interpolated values. No use of `innerHTML`, `unsafeHTML`, or `dangerouslySetInnerHTML` anywhere in the frontend. User input in `mf-search-bar.ts` is read from `(e.target as HTMLInputElement).value` and passed through `trim().toLowerCase()` before dispatch. The `mf-toast.ts` renders messages via `${this.message}` inside a Lit template -- safely escaped.

4. **Database opened read-only.** `db.Open()` uses `?mode=ro` -- prevents accidental writes from the API server.

5. **Server binds to localhost only.** `main.go:44` binds to `127.0.0.1:<port>`, not `0.0.0.0`.

6. **CORS is configurable.** Default `--cors-origin` is `http://localhost:5173` (Vite dev server), not a wildcard `*`. Only `GET` and `OPTIONS` methods are allowed.

7. **Path traversal mitigation.** `HandleStrings` in `handler.go:208-209` uses `filepath.Clean()` and checks for `..` -- good defence against directory traversal.

8. **API contract: thesaurus types match.** Go `thesaurus.LookupResult` -> TS `LookupResult` contracts are consistent. JSON field names (`word`, `senses`, `synset_id`, `pos`, `definition`, `synonyms`, `relations`, `hypernyms`, `hyponyms`, `similar`) match between Go struct tags and TypeScript interfaces.

9. **Server timeouts configured.** `ReadTimeout: 10s`, `WriteTimeout: 30s` -- prevents slowloris.

10. **Frontend input validation.** `client.ts:18` validates response shape (`data.word` is string, `data.senses` is array). `handler.go` validates `word` parameter presence and bounds-checks `threshold` (0-1) and `limit` (1-200).

### Issues

#### Critical (Must Fix)

**None identified.** No secrets in code, no SQL injection vectors, no XSS vectors, no major API contract mismatches.

#### Important (Should Fix)

**1. Fluent strings: two divergent .ftl files with mismatched IDs**
- `strings/v1/ui.en-GB.ftl` (23 lines) -- the "authoritative" source served by the Go API
- `web/public/strings/v1/ui.ftl` (27 lines) -- a separate copy used by Vite dev

The frontend calls `fetch('/strings/v1/ui.ftl')` in `strings.ts:10`. In dev, Vite proxies `/strings/*` to the Go API (`vite.config.ts:16`). The Go API's `HandleStrings` maps `ui.ftl` -> `ui.en-GB.ftl` (handler.go:215-217). So in dev, the authoritative file is served. But the `web/public/strings/v1/ui.ftl` file exists and would be served directly by Vite's static file server **before** the proxy, because Vite serves `public/` files first and only proxies unmatched paths.

**This means the `web/public/strings/v1/ui.ftl` file takes precedence in dev, not the Go API.**

The two files have **different string IDs**:

String IDs used in code (`getString()` calls):
- `search-placeholder` -- both
- `search-aria-label` -- `web/public` only, **missing from** `strings/v1/ui.en-GB.ftl`
- `results-aria-label` -- `web/public` only, **missing from** `strings/v1/ui.en-GB.ftl`
- `results-synonyms` -- `web/public` only, **missing from** `strings/v1/ui.en-GB.ftl`
- `results-broader` -- `web/public` only, **missing from** `strings/v1/ui.en-GB.ftl`
- `results-narrower` -- `web/public` only, **missing from** `strings/v1/ui.en-GB.ftl`
- `results-similar` -- `web/public` only, **missing from** `strings/v1/ui.en-GB.ftl`
- `word-chip-title` -- `web/public` only, **missing from** `strings/v1/ui.en-GB.ftl`
- `status-loading` -- `web/public` only, **missing from** `strings/v1/ui.en-GB.ftl`
- `status-idle` -- `web/public` only, **missing from** `strings/v1/ui.en-GB.ftl`
- `results-word-not-found` -- both (different formatting: `strings/` uses `"{$word}"`, `web/public` uses `"{ $word }"`)
- `error-generic` -- `web/public` only, **missing from** `strings/v1/ui.en-GB.ftl`
- `toast-copied` -- `web/public` only, **missing from** `strings/v1/ui.en-GB.ftl`

**Impact:** If the app were served via the Go API alone (production mode), **13 string IDs would be missing** and fall back to showing raw IDs like `results-synonyms` instead of "Synonyms". The authoritative `strings/v1/ui.en-GB.ftl` is severely out of date -- it has old-naming-convention IDs like `section-hypernyms` that nothing in the frontend uses.

**Fix:** Sync `strings/v1/ui.en-GB.ftl` to match all IDs used in `web/public/strings/v1/ui.ftl`, then decide on a single source of truth. Either remove `web/public/strings/v1/ui.ftl` (let the Go API serve strings) or remove the Go `HandleStrings` endpoint and serve from `public/` in the built frontend.

**2. Unused/dead strings in `strings/v1/ui.en-GB.ftl`**
These IDs are defined in the authoritative .ftl but **not used anywhere** in the frontend code:
- `search-shortcut-hint`
- `results-empty`
- `results-error-network`
- `results-error-retry`
- `pos-noun`, `pos-verb`, `pos-adjective`, `pos-adverb`, `pos-adjective-satellite`
- `synonym-copy-tooltip`, `synonym-copied-feedback`
- `section-hypernyms`, `section-hyponyms`, `section-similar`

**Impact:** Tech debt. Some may be future-use, others are old names superseded by the `web/public` file's IDs (e.g. `section-hypernyms` -> `results-broader`).

**3. `f"SELECT COUNT(*) FROM {table}"` in `test_validation.py:40`**
- File: `data-pipeline/scripts/test_validation.py:40`
- Table names come from a hardcoded dict in the test (`expected = {'synsets': ...}`), not from user input, so this is **not exploitable**.
- However, it's a code-smell and sets a bad pattern. Using parameterised queries isn't possible for table names in SQLite, but the fix would be to validate against a whitelist (which is effectively what the hardcoded dict already does).
- **Verdict:** Low risk, acceptable for test code.

**4. Clipboard API: no HTTPS enforcement documented**
- `mf-results-panel.ts:116` and `mf-force-graph.ts:91` use `navigator.clipboard.writeText()`.
- This API requires a secure context (HTTPS or localhost). In production, if served over HTTP, clipboard will silently fail (caught by `.catch(() => {})`).
- The silent failure is fine, but worth documenting that HTTPS is required in production for clipboard to work.

#### Minor (Nice to Have)

5. **Forge API contract: no frontend TypeScript types**
   - The Go `forge.Match` struct (`forge.go:30-39`) and `handler.SuggestResponse` (`handler.go:67-74`) define the `/forge/suggest` response shape, but there are no corresponding TypeScript interfaces in `web/src/types/api.ts`. Currently only `LookupResult` types are defined. When the forge frontend is built, types will need to be added.
   - **Not a bug now** (forge frontend isn't started), but worth noting.

6. **Go module version: go 1.22**
   - `go.mod` specifies `go 1.22` with `toolchain go1.22.5`. This is current and fine.

7. **Vite config: no build output path configured**
   - `vite.config.ts` doesn't set `build.outDir`. Default is `dist/`, which is gitignored. Fine for now.

8. **`web/dist/strings/v1/ui.ftl` exists in the repo**
   - The `.gitignore` covers `dist/` so this shouldn't be committed. If it is, it's stale build output.

### Recommendations

1. **Unify the Fluent strings files** -- The most pressing integration issue. Decide which file is authoritative, sync the IDs, and remove the duplicate.
2. **Consider Content-Security-Policy headers** -- Not critical for MVP, but adding CSP headers in the Go server or via a reverse proxy would harden the frontend against future XSS risks.
3. **Add rate limiting** -- The Go API has no request rate limiting. For a self-hosted tool this is low risk, but if deployed publicly, consider adding `chi/middleware.Throttle` or similar.
4. **Production CORS configuration** -- The current `--cors-origin` flag is good for dev but needs to be set correctly for production. Document this in deployment notes.

### Assessment

**Ready to merge?** Yes, with one important fix.

**Reasoning:** The codebase has no critical security vulnerabilities. SQL queries are properly parameterised, no secrets are hardcoded, XSS is mitigated by Lit's auto-escaping, the server binds to localhost, and CORS is restricted. The thesaurus API contract between Go and TypeScript is consistent.

The one important issue is the **divergent Fluent strings files** -- the authoritative `strings/v1/ui.en-GB.ftl` is missing 13 string IDs that the frontend actively uses. This would cause visible UI degradation in production (raw string IDs shown instead of localised text). This should be fixed before or shortly after merge.
