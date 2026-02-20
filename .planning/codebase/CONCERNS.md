# Codebase Concerns

**Analysis Date:** 2026-02-14

## Tech Debt

**Double-Lookup Race Condition (Critical):**
- Issue: `mf-app.ts:144-149` — `setWordHash()` fires `hashchange` event → invokes `handleHashChange` → calls `doLookup()` again on every search. No guard prevents the second lookup superseding the first.
- Files: `web/src/components/mf-app.ts`
- Impact: Every search triggers two lookups; only the second result is used. Wasted API calls, duplicate state updates, potential race between responses.
- Fix approach: Guard `handleHashChange` by comparing new word against `this.currentWord` and bail if already searching for that word. Store lookup ID to detect stale responses.

**Tier Classification Out-of-Bounds Panic (Important):**
- Issue: `forge/forge.go:18-19` — `Tier.String()` uses array indexing without bounds check. Invalid Tier values crash the server.
- Files: `api/internal/forge/forge.go`
- Impact: Any corrupted or unexpected Tier value in runtime (e.g., via bad cast or memory corruption) crashes the API process.
- Fix approach: Add bounds check before array access. Return `"unknown"` for out-of-range values (currently relies on panic as guard).

**Legacy Compatibility Layer Complexity (Important):**
- Issue: `db/db.go:180-254` — `getSynsetsWithSharedPropertiesLegacy()` uses bubble sort (O(n²)) and json.Unmarshal on every row. Kept for v1 database compatibility but adds maintenance burden and performance drag.
- Files: `api/internal/db/db.go:242-248`
- Impact: Slower queries on v1 databases; two code paths must be tested and maintained. Performance degradation if legacy path is accidentally used.
- Fix approach: Document v1 deprecation timeline. Migrate all production databases to v2. Consider removing legacy path in next major version.

**Upward Layer Dependency (Important):**
- Issue: `db/db.go:14` — `db` package imports `embeddings` for `BlobToFloats()`. Creates potential circular-dependency risk and violates layering.
- Files: `api/internal/db/db.go`, `api/internal/embeddings/embeddings.go`
- Impact: Tight coupling; changes to embeddings affect database layer. If embeddings ever needs to reference db, creates circular import.
- Fix approach: Move `BlobToFloats()` to a shared `util` or `codec` package, or have `db.go` return raw `[]byte` blobs and let callers decode.

**Hardcoded Database Path and Configuration (Important):**
- Issue: `cmd/metaforge/main.go:18` — Database path, strings directory, CORS origin all set via flags with hardcoded defaults. No env var support for container/cloud deployments.
- Files: `api/cmd/metaforge/main.go`
- Impact: Difficult to configure in containerised environments; secrets/paths in CLI arguments are visible in process list.
- Fix approach: Prefer environment variables (with flag fallback for dev). Use `flag.String` with env var defaults: `os.Getenv("DB_PATH", defaultPath)`.

**CORS Configuration for Development Only (Important):**
- Issue: `cmd/metaforge/main.go:34`, `handler/handler.go:280-295` — CORS middleware accepts hardcoded origin (`http://localhost:5173`). Will fail in production or when Vite dev server is not running.
- Files: `api/cmd/metaforge/main.go:20`, `api/internal/handler/handler.go`
- Impact: API is unusable from any origin other than Vite dev server. Production deployments must be behind a reverse proxy or require code change.
- Fix approach: Warn on startup if CORS origin doesn't match deployment environment. Document production reverse-proxy setup (Caddy/nginx).

**Strings Singleton Not Isolated in Tests (Important):**
- Issue: `web/src/lib/strings.ts:7` — `bundle` is a module-level `let` with no reset. Test isolation breaks if test order changes or if one test fails during `initStrings()`.
- Files: `web/src/lib/strings.ts`, `web/src/lib/strings.test.ts`
- Impact: Flaky tests; false positives under certain test runner configurations. Test order dependency.
- Fix approach: Export `resetStrings()` function for test cleanup, or restructure as a class/factory with explicit initialisation per instance.

---

## Known Bugs

**Navigator Clipboard API Not Error-Handled (Critical):**
- Symptoms: Unhandled promise rejection in console when clipboard write fails. Toast shows "Copied" even when copy failed.
- Files: `web/src/components/mf-force-graph.ts:112`, `web/src/components/mf-results-panel.ts:214`
- Trigger: Right-click copy on any word when: (1) page not served over HTTPS, (2) user denies clipboard permission, or (3) Clipboard API unavailable in browser/iframe.
- Workaround: Use keyboard shortcut (Ctrl+C) after clicking word, or open browser dev tools to suppress console errors. Copy still fails silently.
- Fix approach: Add `.catch(() => { /* clipboard unavailable */ })` to promise. Optionally show error toast: `.catch(() => toast.show('Clipboard unavailable'))`.

**Results Panel Overlaps Search Bar on Mobile (Important):**
- Symptoms: Results panel starts at `top: 2rem` (32px), search bar ends at ~48px (height) + padding. On narrow viewports, panel overlays search input.
- Files: `web/src/components/mf-results-panel.ts:12-13`, `web/src/components/mf-app.ts:33-34`
- Trigger: Viewport width < 768px (mobile breakpoint) with multiple senses displayed.
- Workaround: Manually collapse panel or rotate device to landscape.
- Fix approach: Add media query: offset panel below search bar on mobile, or use `top: calc(var(--space-md, 1rem) + 48px)` consistently.

**Double-Click Detection on Graph Has 300ms Delay (Important):**
- Symptoms: Every single node click waits 300ms before firing event. Perceived lag in interaction. False clicks on different nodes within 300ms trigger confusing navigation.
- Files: `web/src/components/mf-force-graph.ts:88-107`
- Trigger: Any node click in the 3D force graph.
- Workaround: Wait for animations to settle before clicking next node. Use keyboard navigation if available (not currently implemented).
- Fix approach: Use browser's native `dblclick` event if `3d-force-graph` exposes it. Reduce timeout to 200ms. Or: single-click for navigation, require Ctrl+click for selection.

**Response Shape Validation Missing (Important):**
- Symptoms: If API returns unexpected JSON structure (missing fields, type mismatch), application silently fails deep in rendering with cryptic errors.
- Files: `web/src/api/client.ts:24-37`
- Trigger: API schema change, proxy injecting error page, or corrupted response.
- Workaround: Check browser console for errors; they usually point to the transform or render code, not the API response.
- Fix approach: Add runtime validation: `if (!data.word || !Array.isArray(data.senses)) throw new ApiError('Invalid response shape')`.

**Shadow DOM Active Element Check Broken (Important):**
- Symptoms: `/` shortcut steals focus from other inputs on the page. Guard `document.activeElement !== this.inputEl` does not work because shadow DOM boundary returns host element, not inner input.
- Files: `web/src/components/mf-search-bar.ts:161-174`
- Trigger: User types `/` in any input elsewhere on page (future feature, iframe, etc.).
- Workaround: Use `/` shortcut only when search bar is visible/expected.
- Fix approach: Check if `document.activeElement` is any input/textarea/contenteditable. Account for shadow root: if active element is `mf-search-bar` host, check if inner input is focused.

---

## Security Considerations

**HTTPS Requirement for Clipboard API (Medium):**
- Risk: Clipboard API requires HTTPS (or localhost dev). Production deployments served over HTTP will silently fail copy operations with unhandled rejections. Users may believe copy worked but it didn't.
- Files: `web/src/components/mf-force-graph.ts:112`, `web/src/components/mf-results-panel.ts:214`
- Current mitigation: None; silently fails.
- Recommendations: (1) Add error handling to clipboard calls. (2) Document HTTPS requirement in deployment guide. (3) Consider fallback: show fallback UI if clipboard unavailable (e.g., "Copy: HTTPS required").

**No Content-Security-Policy Headers (Low):**
- Risk: If API serves static HTML (future feature), lack of CSP allows inline scripts and external resource injection.
- Files: `api/cmd/metaforge/main.go`, `api/internal/handler/handler.go`
- Current mitigation: None.
- Recommendations: Add CSP headers via reverse proxy (Caddy/nginx) or middleware. For MVP with frontend-only app, this is low priority.

**No Rate Limiting (Low):**
- Risk: If deployed publicly, API is vulnerable to brute-force or resource-exhaustion attacks (e.g., many large queries). No request throttling.
- Files: `api/cmd/metaforge/main.go` (no middleware)
- Current mitigation: None; relies on reverse proxy or firewall.
- Recommendations: (1) Document deployment behind rate-limit proxy. (2) For self-hosted, add `chi/middleware.Throttle` or similar. (3) Monitor query patterns in production.

**Database Read-Only Flag Insufficient (Low):**
- Risk: Database opened with `immutable=1` prevents writes, but no file-system permission check. If DB file becomes writable, schema could be corrupted.
- Files: `api/internal/db/db.go:34`
- Current mitigation: `immutable=1` SQLite flag + hardened file permissions expected.
- Recommendations: (1) Document file permissions (e.g., `chmod 444 lexicon_v2.db`). (2) Optionally: verify file permissions at startup, warn if writable.

**Secrets in CLI Flags (Low):**
- Risk: If CORS origin or database path contains secrets (unlikely but possible), they appear in `ps` output.
- Files: `api/cmd/metaforge/main.go:18-21`
- Current mitigation: None; defaults are safe, but flag-based config is insecure.
- Recommendations: Use environment variables for sensitive config. Mask flag values in help/logs.

---

## Performance Bottlenecks

**Bubble Sort in Legacy Path (Medium):**
- Problem: O(n²) bubble sort in `getSynsetsWithSharedPropertiesLegacy()` for result ranking. Only hits v1 databases but degrades gracefully.
- Files: `api/internal/db/db.go:242-248`
- Cause: Implemented for backwards compatibility; v2 uses pre-computed similarity matrix.
- Improvement path: (1) Migrate all databases to v2 schema. (2) Use `sort.Slice()` instead of bubble sort as interim fix. (3) Add benchmark tests to catch performance regressions.

**Table Existence Check on Every Query (Low):**
- Problem: `GetSynsetsWithSharedProperties()` checks if `property_similarity` table exists on every call. Adds overhead even though schema is static after initialization.
- Files: `api/internal/db/db.go:119-128`
- Cause: Backwards compatibility with v1 databases; check is O(n) metadata query.
- Improvement path: Cache result at handler init time or check once at startup. Per-query check is premature pessimism.

**WebGL Resource Leak on Component Unmount (Medium):**
- Problem: `mf-force-graph.ts:160-173` sets `this.graph = null` but does not call cleanup/destructor. Three.js renderer, animation loop, and event listeners leak on repeated mount/unmount.
- Files: `web/src/components/mf-force-graph.ts`
- Cause: Missing call to `._destructor()` or `pauseAnimation()` + renderer cleanup before nulling reference.
- Improvement path: (1) Call graph's cleanup method in `disconnectedCallback`. (2) Add lifecycle test that mounts/unmounts component repeatedly and checks for memory leaks.

**N+1 Query Pattern Partially Mitigated (Low):**
- Problem: `GetForgeMatches()` retrieves candidates, details, overlap, and centroids in single mega-query (good), but `GetSynset()` still queries separately for properties in a loop. Not called on hot path but inefficient for ad-hoc lookups.
- Files: `api/internal/db/db.go:40-98`
- Cause: Property lookup uses separate query; could be included in main query with JOIN.
- Improvement path: Move property retrieval into `GetSynset()` query itself, or batch fetch properties for multiple synsets.

---

## Fragile Areas

**Graph Transform Deduplication by Word Only (Medium):**
- Files: `web/src/graph/transform.ts:55`
- Why fragile: Uses word as node ID. If same word appears as both hypernym and hyponym (homonym across relations), deduplication silently keeps first occurrence. Documented but brittle.
- Safe modification: (1) Test with fixture that has homonym spanning multiple relation types. (2) Consider using `word__synsetId` as ID. (3) Document dedup behaviour clearly in comments.
- Test coverage: `transform.test.ts` lacks explicit test for homonym across relations.

**API Response Type Validation Absent (Medium):**
- Files: `web/src/api/client.ts:24-37`
- Why fragile: Direct cast to `LookupResult` with no runtime validation. Any schema mismatch (missing field, type change, proxy error injection) silently propagates to rendering code.
- Safe modification: (1) Add assertion on `data.word` and `data.senses` before returning. (2) Use Zod or similar for strict schema validation. (3) Test with malformed responses.
- Test coverage: No test for API error responses or schema mismatches.

**Strings Module Mutable Singleton (Medium):**
- Files: `web/src/lib/strings.ts:7`
- Why fragile: `bundle` is module-level `let` with no reset mechanism. Tests share state; order dependency. Pre-init calls to `getString()` return ID fallback without clear indication that strings failed to load.
- Safe modification: (1) Export `resetStrings()` for test teardown. (2) Add `initStrings()` failure case tests. (3) Consider factory pattern if strings are used in multiple contexts.
- Test coverage: Missing test for `getString()` before `initStrings()` called.

**Tile Classification Hardcoded Thresholds (Low):**
- Files: `api/internal/forge/forge.go:27-30`
- Why fragile: `HighDistanceThreshold`, `MinOverlap`, `StrongOverlap` are compile-time constants. Changes require code recompilation and testing. No configuration/tuning path.
- Safe modification: (1) Make configurable via environment or config file. (2) Add tests that verify tier boundaries. (3) Document tuning process.
- Test coverage: `forge_test.go` has good tier coverage but doesn't test boundary cases near thresholds.

---

## Scaling Limits

**Database Query Result Scaling (Medium):**
- Current capacity: `GetForgeMatches()` limits results to 200 (hard cap in handler). Single mega-query with JOINs scales to ~100k+ synsets.
- Limit: Query execution time increases with similarity matrix size. At 500k synsets + properties, query may timeout (30s write timeout in server).
- Scaling path: (1) Add query result pagination. (2) Use database indexes on property_id and synset_id. (3) Cache centroids in memory or Redis. (4) Consider materialized view for common queries.

**WebGL Context Limit (Low):**
- Current capacity: Browser WebGL context limit is typically 8-16 active contexts depending on GPU. Repeated graph mount/unmount without cleanup exhausts contexts.
- Limit: After 8-16 page reloads or component resets, browser throws "WebGL context lost" error and graph stops rendering.
- Scaling path: (1) Fix resource cleanup in `disconnectedCallback`. (2) Reuse single graph instance instead of recreating. (3) Add WebGL context lost handler to gracefully restore.

**Concurrent Lookups on Mobile (Low):**
- Current capacity: 4 SQLite connections max (`SetMaxOpenConns(4)`). Mobile with poor network may queue requests.
- Limit: If user searches multiple times in rapid succession, 5th concurrent request waits. No request timeout outside server Write/Read timeouts.
- Scaling path: (1) Document concurrent connection limit in performance docs. (2) Cancel stale lookups client-side (already done via `lookupId`). (3) Increase pool size for production or use connection pooling proxy.

---

## Dependencies at Risk

**3d-force-graph Type Safety Missing (Medium):**
- Risk: Custom `.d.ts` declares `ForceGraph3D: any`, disabling all type checking on library API.
- Files: `web/src/types/3d-force-graph.d.ts:6-7`
- Impact: Typos in method names, incorrect callback signatures, and wrong argument types go undetected at compile time.
- Migration plan: (1) Check if `@types/3d-force-graph` exists on npm. (2) If not, write minimal type definitions for methods actually used (`.backgroundColor()`, `.nodeColor()`, `.onNodeClick()`, etc.). (3) Enable strict null checks to catch undefined methods.

**Legacy Enrichment Data Structure (Low):**
- Risk: `db/db.go:180-254` legacy path expects `enrichment` table with `properties` JSON column. If schema evolves, legacy path breaks.
- Files: `api/internal/db/db.go:192-254`
- Impact: v1 database support becomes unmaintainable as schema diverges.
- Migration plan: (1) Set deprecation timeline for v1 databases. (2) Provide migration script v1 → v2. (3) Remove legacy path in next major version (2027?).

**SQLite Immutable Flag Lock-In (Low):**
- Risk: `db.go:34` uses `immutable=1` for read-only access. If future feature requires write access (e.g., user annotations), must rearchitect.
- Files: `api/internal/db/db.go:34`
- Impact: Cannot add write operations to current database without switching to separate write DB.
- Migration plan: (1) Use separate read-only lexicon database + separate write database for user data (IndexedDB for MVP). (2) Document why immutable flag is used. (3) Plan for multi-database pattern if needed.

---

## Missing Critical Features

**No Error Recovery for Failed Suggestions (Medium):**
- Problem: If autocomplete API fails, suggestions silently clear. No error toast or user feedback. User sees search bar stop autocompleting and may think it's broken.
- Blocks: Users cannot tell if autocomplete is working; trust in search degrades on poor networks.
- Fix approach: (1) Show error toast on fetch failure if `SUGGEST_MODE === 'dropdown'`. (2) Add retry logic. (3) Log error to console for debugging.

**No API Request Timeout or Cancellation (Medium):**
- Problem: If server hangs, lookup request waits indefinitely (server has 30s write timeout but client has no explicit timeout). User is stuck loading forever.
- Blocks: Users cannot cancel stale requests; perceived app hang.
- Fix approach: (1) Add `AbortController` with 10s timeout on fetch. (2) Cancel previous lookup when new search starts (already done via `lookupId`). (3) Show timeout error to user after 5-10s.

**No Offline Support (Low):**
- Problem: App requires network access for every search. Offline mode not mentioned but IndexedDB is mentioned in architecture.
- Blocks: Users cannot use app on airplane, tunnel, or poor-signal areas. Cannot cache frequent searches.
- Fix approach: (1) Cache recent searches in IndexedDB. (2) Show cached results when offline. (3) Add service worker for offline fallback (future work).

---

## Test Coverage Gaps

**Untested: Double-Lookup Race Condition (High Priority):**
- What's not tested: Rapid successive searches before first response returns. Current tests assume sequential lookups.
- Files: `web/src/components/mf-app.test.ts`
- Risk: Race between two in-flight requests. Second request's response could clobber first if first responds later.
- Priority: High — this is C1 bug already identified in code review.

**Untested: API Client Error Paths (High Priority):**
- What's not tested: Network errors, malformed JSON responses, 404s, 500s, timeout scenarios.
- Files: `web/src/api/client.ts`
- Risk: Network errors crash silently or show generic "Unknown error" to user. Real-world issues go undiagnosed.
- Priority: High — M6 from code review.

**Untested: Clipboard Failure (High Priority):**
- What's not tested: Clipboard unavailable, permission denied, HTTPS requirement. Currently silently fails.
- Files: `web/src/components/mf-force-graph.ts`, `web/src/components/mf-results-panel.ts`
- Risk: Copy functionality appears to work but fails silently. Users lose trust.
- Priority: High — C2 from code review.

**Untested: Results Panel on Mobile Collision (Medium Priority):**
- What's not tested: Results panel positioning on narrow viewports. No responsive layout test.
- Files: `web/src/components/mf-results-panel.ts`
- Risk: Panel overlays search bar, breaking usability on mobile.
- Priority: Medium — I6 from code review.

**Untested: Strings Fetch Failure (Medium Priority):**
- What's not tested: `initStrings()` failure path when fetch returns 404 or network error. `getString()` fallback to ID.
- Files: `web/src/lib/strings.ts`, `web/src/lib/strings.test.ts`
- Risk: Silent failure; users see message IDs instead of translated strings. No indication that localization failed.
- Priority: Medium.

**Untested: Legacy Database Path (Medium Priority):**
- What's not tested: Entire legacy `getSynsetsWithSharedPropertiesLegacy()` code path. Bubble sort, JSON parsing, all branches.
- Files: `api/internal/db/db.go:180-254`, `api/internal/db/db_test.go`
- Risk: v1 database support untested; bugs lurk in rarely-used code.
- Priority: Medium — reduces risk as v1 databases phase out.

**Untested: Graph WebGL Resource Cleanup (Medium Priority):**
- What's not tested: Repeated mount/unmount of force graph. WebGL context leaks, memory leaks.
- Files: `web/src/components/mf-force-graph.ts`, no test file
- Risk: Hard to test (browser-only, WebGL), but memory leak risk is real.
- Priority: Medium — hard to test but important for stability.

**Untested: Tier Classification Edge Cases (Low Priority):**
- What's not tested: Tier classification with 0 distance, exactly at threshold boundaries, negative values (should not happen but guards missing).
- Files: `api/internal/forge/forge.go`, `api/internal/forge/forge_test.go`
- Risk: Edge case panics or unexpected tier assignments.
- Priority: Low — thresholds are stable and well-defined.

---

*Concerns audit: 2026-02-14*
