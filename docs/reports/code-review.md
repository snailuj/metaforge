# Phase 1 MVP Frontend -- Code Review

**Reviewer:** Claude Opus 4.6
**Date:** 2026-02-07
**Branch:** sprint-zero
**Scope:** 13 files in `web/src/` (Batch 1 + Batch 2 of the Phase 1 plan)

---

## Summary

The implementation faithfully follows the Phase 1 plan (`docs/plans/20260207-phase1-force-graph-mvp.md`) across Batches 1 and 2. The code is clean, well-typed, and idiomatic for Lit + TypeScript. No security vulnerabilities or malware indicators were found. The review identifies 3 critical issues, 6 major issues, 8 minor issues, and 6 notes.

**Overall Verdict:** APPROVE WITH CHANGES -- the critical and major issues should be addressed before merging. None require architectural rework; most are edge-case hardening and missing integration pieces.

---

## CRITICAL Issues

### C1. `mf-app.ts` and `mf-toast.ts` do not exist -- app is not wired up

**Files:** Missing: `web/src/components/mf-app.ts`, `web/src/components/mf-toast.ts`
**Affected:** `web/src/main.ts` (line 2), `web/index.html` (line 11)

The `index.html` renders `<mf-app></mf-app>` but no `mf-app` custom element is registered anywhere. The `main.ts` is still a placeholder (`console.log('Metaforge starting...')`). Per the Phase 1 plan (Task 10), these files orchestrate the entire application -- wiring search events to API calls, transforming results, and feeding data to the graph and HUD panel.

Without these files, the application renders a blank page. The individual components work in isolation but have no orchestrator connecting them.

**Impact:** Application is non-functional as a whole. All components exist but nothing wires them together.

**Recommendation:** Implement Task 10 from the plan (mf-app.ts + mf-toast.ts + update main.ts).

---

### C2. `navigator.clipboard.writeText()` called without error handling or permission check

**Files:**
- `/home/agent/projects/metaforge/web/src/components/mf-force-graph.ts` (line 75)
- `/home/agent/projects/metaforge/web/src/components/mf-results-panel.ts` (line 110)

`navigator.clipboard.writeText()` returns a Promise that can reject if:
1. The page is not served over HTTPS (or localhost)
2. The Clipboard API is not available (some browsers, iframes)
3. The user has denied clipboard permissions

In both components, the returned Promise is ignored (fire-and-forget), and no `.catch()` is attached. An unhandled rejection will appear in the console and, in strict environments, could cause issues.

```typescript
// mf-force-graph.ts line 75
navigator.clipboard.writeText(node.word)

// mf-results-panel.ts line 110
navigator.clipboard.writeText(word)
```

**Impact:** Unhandled promise rejection when clipboard write fails. The `mf-node-copy` / `mf-word-copy` events still fire, so the toast would show "Copied" even when the copy actually failed.

**Recommendation:** Add `.catch()` with fallback or user feedback. Consider checking `navigator.clipboard` availability first.

---

### C3. `strings.ts` module-level mutable singleton is not isolated between tests

**File:** `/home/agent/projects/metaforge/web/src/lib/strings.ts` (line 7)
**Test file:** `/home/agent/projects/metaforge/web/src/lib/strings.test.ts`

The `bundle` variable is a module-level `let` with no reset mechanism. If tests run in the same module context (which vitest does by default for the same file), the `bundle` from one test leaks into subsequent tests. The test file relies on `initStrings()` being called in each test to set up the bundle, but if test order changes or a test fails during `initStrings()`, the stale bundle from a previous test would produce misleading results.

Additionally, there is no test for the case where `initStrings()` is never called -- i.e., verifying that `getString()` returns the ID fallback when `bundle` is `null`. The `beforeEach` calls `vi.restoreAllMocks()` but does not reset the `bundle` singleton.

**Impact:** Flaky tests under certain configurations. False positives if test isolation breaks.

**Recommendation:** Either export a `resetStrings()` function for testing, or restructure as a class/factory. Add a test for `getString()` before `initStrings()` is called.

---

## MAJOR Issues

### M1. `updated()` in `mf-force-graph.ts` uses wrong type for `changed` parameter

**File:** `/home/agent/projects/metaforge/web/src/components/mf-force-graph.ts` (line 95)

```typescript
updated(changed: Map<string, unknown>): void {
```

Lit's `updated()` lifecycle receives `Map<PropertyKey, unknown>` (which is `PropertyKey = string | number | symbol`), but more importantly, for Lit's reactive property system, the correct type is `PropertyValues` (imported from `lit`). The `changed.has('graphData')` call checks for the string `'graphData'`, but since `graphData` is decorated with `@property()`, Lit tracks it by its property name. This works at runtime, but the type annotation is inaccurate and could mask issues if property names change.

**Impact:** No runtime bug currently, but incorrect typing reduces TypeScript's ability to catch refactoring errors.

**Recommendation:** Use `PropertyValues<this>` or `Map<PropertyKey, unknown>` from Lit's type definitions.

---

### M2. Force graph does not clean up WebGL resources on disconnect

**File:** `/home/agent/projects/metaforge/web/src/components/mf-force-graph.ts` (lines 101-105)

```typescript
disconnectedCallback(): void {
  super.disconnectedCallback()
  if (this.clickTimer) clearTimeout(this.clickTimer)
  this.graph = null
}
```

Setting `this.graph = null` does not dispose the Three.js renderer, scene, or animation frame. `3d-force-graph` has a `._destructor()` method (or the graph instance may have a publicly exposed cleanup). Without calling it, the WebGL context, animation loop, and event listeners leak. On repeated navigation or if the component is removed and re-added, this creates memory leaks and potentially hits the browser's WebGL context limit.

**Impact:** Memory leak and potential WebGL context exhaustion on repeated component mount/unmount cycles.

**Recommendation:** Call the graph's cleanup/destructor method before nulling the reference. Check `3d-force-graph` API for a `._destructor()` or `.pauseAnimation()` + renderer dispose.

---

### M3. No `aria-live` region on the results panel for screen reader announcements

**File:** `/home/agent/projects/metaforge/web/src/components/mf-results-panel.ts` (line 183)

The PRD (Metaforge-PRD-2.md, Accessibility section) explicitly requires `aria-live="polite"` on the results region. The panel has `role="region"` and `aria-label="Thesaurus results"` but no `aria-live` attribute.

```typescript
<div class="panel" role="region" aria-label="Thesaurus results">
```

**Impact:** Screen reader users will not be notified when results change after a new search. They would need to manually navigate to the panel to discover updated content.

**Recommendation:** Add `aria-live="polite"` to the panel div.

---

### M4. `lookupWord()` in `client.ts` does not validate the response shape

**File:** `/home/agent/projects/metaforge/web/src/api/client.ts` (line 22)

```typescript
return response.json()
```

The response is cast directly to `LookupResult` via the function's return type, but no runtime validation occurs. If the API returns an unexpected shape (e.g., a field is missing, the Go backend changes, or a proxy/CDN injects an error page), the application will get an object that does not match `LookupResult` but TypeScript believes it does. This could cause subtle runtime errors deep in the transform or rendering code.

**Impact:** Silent data corruption if the API response shape diverges. Hard-to-debug errors in downstream components.

**Recommendation:** At minimum, assert that `result.word` and `result.senses` exist. A runtime schema validator (e.g., Zod or a simple manual check) would be ideal for an API boundary.

---

### M5. `mf-search-bar` global keydown listener does not check if user is typing in another input

**File:** `/home/agent/projects/metaforge/web/src/components/mf-search-bar.ts` (lines 57-62)

```typescript
private handleGlobalKeydown = (e: KeyboardEvent) => {
  if (e.key === '/' && document.activeElement !== this.inputEl) {
    e.preventDefault()
    this.inputEl?.focus()
  }
}
```

The check `document.activeElement !== this.inputEl` only prevents re-focusing the search bar's own input. If the user is typing `/` in any other input or textarea elsewhere in the page (e.g., a future annotation feature, a settings dialog), this handler will steal focus. The `this.inputEl` is inside a shadow DOM, so `document.activeElement` will return the host element (`mf-search-bar`), not the inner input -- meaning the guard does not work as intended.

**Impact:** The `/` shortcut may steal focus from other inputs. The shadow DOM boundary means the check against `this.inputEl` will never match `document.activeElement` (which sees the host, not the shadow-internal element).

**Recommendation:** Check whether `document.activeElement` is any input, textarea, or contenteditable element before intercepting the keypress. Also account for shadow DOM: `document.activeElement` will be the `mf-search-bar` host element when the inner input is focused, so check for that.

---

### M6. No test coverage for the API client (`client.ts`)

**File:** `/home/agent/projects/metaforge/web/src/api/client.ts`

The Phase 1 plan explicitly notes `client.ts` has no test file (the plan says "Verify it compiles" only). However, the function has meaningful logic: URL encoding, error parsing, `ApiError` construction. The `lookupWord` function is a critical data-path function and should have tests covering:
- Successful lookup
- HTTP error with JSON body
- HTTP error with non-JSON body (the `.catch` path on line 22)
- Empty/whitespace word input
- Network failure

**Impact:** Regressions in the API client would not be caught by automated tests.

**Recommendation:** Add a `client.test.ts` with mocked `fetch` (similar to how `strings.test.ts` mocks it).

---

## MINOR Issues

### m1. Hardcoded placeholder string in `mf-search-bar.ts` instead of using Fluent

**File:** `/home/agent/projects/metaforge/web/src/components/mf-search-bar.ts` (line 102)

```typescript
placeholder="Search for a word..."
```

The Phase 1 plan acknowledges this as a known gap ("Components use hardcoded strings; wire to getString()"). The Fluent strings client (`strings.ts`) is built and tested, but none of the components use it. The `strings.test.ts` even tests a `search-placeholder` message ID that matches this exact string.

**Impact:** Internationalisation is blocked. Low urgency for MVP but worth flagging.

---

### m2. `3d-force-graph.d.ts` declares everything as `any`

**File:** `/home/agent/projects/metaforge/web/src/types/3d-force-graph.d.ts` (lines 1-4)

```typescript
declare module '3d-force-graph' {
  const ForceGraph3D: any
  export default ForceGraph3D
}
```

This disables all type checking for the `ForceGraph3D` API. Every method chain in `mf-force-graph.ts` is unchecked -- misspelled methods, wrong argument types, and incorrect callback signatures would all pass silently.

**Impact:** No compile-time safety for any `3d-force-graph` API usage. Typos in method names or incorrect callback signatures would only be caught at runtime.

**Recommendation:** Either use `@types/3d-force-graph` if available, or write a minimal declaration covering the methods actually used (`.backgroundColor()`, `.nodeLabel()`, `.nodeColor()`, `.nodeVal()`, `.nodeOpacity()`, `.linkColor()`, `.linkWidth()`, `.linkOpacity()`, `.onNodeClick()`, `.onNodeRightClick()`, `.onNodeHover()`, `.graphData()`).

---

### m3. `mf-force-graph.ts` double-click detection has timing fragility

**File:** `/home/agent/projects/metaforge/web/src/components/mf-force-graph.ts` (lines 51-72)

The double-click detection uses a 300ms timeout with `onNodeClick`. This means:
1. Every single click is delayed by 300ms before the `mf-node-select` event fires.
2. If the user clicks two different nodes within 300ms, the second click on node B triggers `mf-node-navigate` for node B but the event detail will be node B, not the first-clicked node -- which is correct but the semantic is "the user was trying to navigate to node B via double-click", which may not be their intent.

The PRD specifies "Single-click: Shows tooltip/detail in HUD" and "Double-click node: New word becomes centre, graph reshuffles". The 300ms delay on single-click selection is a usability concern.

**Impact:** 300ms perceived lag on every single click. Potential for misinterpreted clicks across different nodes.

**Recommendation:** Consider using `dblclick` event from the browser (which `3d-force-graph` may expose via `onNodeDblClick` or could be handled at the DOM level) instead of manual timer-based detection. Alternatively, reduce the timeout to ~200ms.

---

### m4. `transform.ts` uses word as node ID, causing collisions for homonyms

**File:** `/home/agent/projects/metaforge/web/src/graph/transform.ts` (line 55)

```typescript
const nodeId = rw.word
```

The `GraphNode.id` comment in `types.ts` (line 11) says: "Unique: word or word__synsetId for disambiguation". However, the transform always uses just the word as the ID. If the same word appears as both a hypernym and a hyponym (e.g., "run" could be both), the deduplication logic silently drops the second occurrence with "first relation type wins". While this is documented behaviour, using word-only IDs means that legitimately different senses of the same word cannot coexist in the graph.

**Impact:** Loss of information when the same word appears in multiple relation types. The graph comment promises synset-based disambiguation but the implementation does not deliver it.

**Recommendation:** For MVP this is acceptable (documented dedup behaviour), but consider using `word__synsetId` as the ID when a word appears in multiple senses to preserve both nodes.

---

### m5. `mf-results-panel.ts` renders `result.word` directly in HTML without escaping concern

**File:** `/home/agent/projects/metaforge/web/src/components/mf-results-panel.ts` (line 184)

```typescript
<h2>${this.result.word}</h2>
```

Lit's `html` tagged template literal automatically escapes interpolated values, so this is not an XSS vulnerability. However, the `result` property is typed as `LookupResult | null` and comes from the API response via `@property({ type: Object })`. If a malicious or corrupted API response includes HTML/script in the `word` field, Lit would render it as text (safe). This is noted for completeness -- Lit's templating provides adequate protection here.

**Impact:** None -- Lit's escaping handles this correctly.

---

### m6. `mf-results-panel.ts` word chips have no keyboard accessibility

**File:** `/home/agent/projects/metaforge/web/src/components/mf-results-panel.ts` (lines 121-129)

The word chips are `<span>` elements with `@dblclick` handlers but no `tabindex`, `role="button"`, or `@keydown` handler. The PRD requires keyboard navigation: "Tab through HUD results, Enter to select". Currently, word chips cannot receive keyboard focus.

```typescript
<span
  class="word-chip ${type}"
  data-word=${rw.word}
  @dblclick=${() => this.handleWordDblClick(rw.word)}
  @contextmenu=${(e: MouseEvent) => this.handleWordRightClick(e, rw.word)}
  title="Double-click to navigate, right-click to copy"
>${rw.word}</span>
```

**Impact:** Keyboard-only users and screen reader users cannot navigate to or activate word chips. Fails WCAG 2.1 AA requirement from the PRD.

**Recommendation:** Add `tabindex="0"`, `role="button"`, and a `@keydown` handler that triggers navigation on Enter.

---

### m7. `transform.test.ts` does not test self-reference skipping explicitly

**File:** `/home/agent/projects/metaforge/web/src/graph/transform.test.ts`

The transform function skips self-references (line 53 of `transform.ts`: `if (rw.word === result.word) continue`), but no test explicitly verifies this behaviour with a fixture where the searched word appears in its own synonyms list.

**Impact:** The self-reference guard could be accidentally removed without a test catching it.

**Recommendation:** Add a test where a sense's synonyms include the searched word itself, and verify it is not duplicated as a node.

---

### m8. `initStrings()` silently continues on fetch failure

**File:** `/home/agent/projects/metaforge/web/src/lib/strings.ts` (lines 11-13)

```typescript
if (!response.ok) {
  console.error('Failed to load strings:', response.status)
  return
}
```

If the strings file fails to load (network error, 404, etc.), `bundle` remains `null` and all `getString()` calls return the message ID as fallback. This is reasonable graceful degradation, but there is no test for this failure path.

**Impact:** Low -- the fallback behaviour is sensible. But the failure path is untested.

**Recommendation:** Add a test verifying that `getString()` returns the ID when `initStrings()` encounters a fetch failure.

---

## NOTES

### N1. Plan conformance is high

The implementation matches the Phase 1 plan almost verbatim. Files, types, function signatures, test fixtures, and CSS tokens all align. The only substantive deviation is that Batch 3 (Task 10: mf-app.ts, mf-toast.ts, main.ts update) has not been implemented yet, which is flagged as C1 above.

---

### N2. UK English spelling is correctly used

Per the coding style guidelines, UK English spelling is used consistently: "colour" in CSS tokens and variable names, "optimise" would be used if relevant. This is correct.

---

### N3. Test fixture reuse between files

The `melancholy` test fixture is defined separately in both `transform.test.ts` and `mf-results-panel.test.ts` with slightly different structures (different senses). This is acceptable for now but could be extracted to a shared test fixtures module if the pattern continues.

---

### N4. `ApiError` does not set prototype correctly for `instanceof` checks

**File:** `/home/agent/projects/metaforge/web/src/api/client.ts` (lines 3-10)

The `ApiError` class extends `Error` but does not call `Object.setPrototypeOf(this, ApiError.prototype)` in the constructor. In environments that downlevel-compile to ES5, `instanceof ApiError` checks may fail. Since the project targets ES2022 and uses native classes, this is not a problem -- but worth noting for portability.

---

### N5. CSS custom properties use sensible fallback values

Throughout all components, CSS custom properties include fallback values (e.g., `var(--colour-bg-hud, rgba(22, 33, 62, 0.6))`). This is good practice and ensures the components render correctly even without the global `tokens.css` loaded.

---

### N6. The `@state()` decorator on `graph` in `mf-force-graph.ts` is questionable

**File:** `/home/agent/projects/metaforge/web/src/components/mf-force-graph.ts` (line 30)

```typescript
@state() private graph: ReturnType<typeof ForceGraph3D> | null = null
```

The `graph` property holds the `3d-force-graph` instance. Decorating it with `@state()` means any assignment to `this.graph` triggers a Lit re-render, but the `render()` method does not reference `this.graph` at all -- it only renders a container div. The graph instance is managed imperatively. This `@state()` is unnecessary and causes a superfluous re-render when the graph is initialised in `firstUpdated()`.

**Impact:** One unnecessary re-render on initial setup. Negligible performance impact.

**Recommendation:** Remove the `@state()` decorator from `graph` and use a plain private property instead.

---

## Test Coverage Summary

| File | Tests | Verdict |
|------|-------|---------|
| `graph/transform.ts` | 8 tests in `transform.test.ts` | Good -- covers central node, relations, dedup, cap, priority, empty input. Missing: self-reference test. |
| `lib/strings.ts` | 3 tests in `strings.test.ts` | Adequate -- covers happy path, interpolation, fallback. Missing: fetch failure, pre-init fallback. |
| `components/mf-search-bar.ts` | 3 tests in `mf-search-bar.test.ts` | Adequate -- covers registration, submit, empty guard. Missing: Escape key, `/` shortcut. |
| `components/mf-results-panel.ts` | 4 tests in `mf-results-panel.test.ts` | Adequate -- covers registration, heading, definitions, dblclick navigation. Missing: right-click copy, null result. |
| `components/mf-force-graph.ts` | 0 tests | Acknowledged in plan as hard to test (WebGL). Acceptable. |
| `api/client.ts` | 0 tests | Should have basic tests with mocked fetch. See M6. |
| `types/api.ts` | N/A (types only) | N/A |
| `graph/types.ts` | N/A (types only) | N/A |
| `types/3d-force-graph.d.ts` | N/A (declaration) | N/A |

**Total test count:** 18 tests across 4 test files.

---

## Issue Tally

| Severity | Count |
|----------|-------|
| CRITICAL | 3 |
| MAJOR | 6 |
| MINOR | 8 |
| NOTE | 6 |

---

## Recommended Priority Order

1. **C1** -- Implement `mf-app.ts` and `mf-toast.ts` (the app does not work without them)
2. **C2** -- Add error handling to `navigator.clipboard.writeText()` calls
3. **C3** -- Fix strings singleton test isolation
4. **M2** -- Clean up WebGL resources in `disconnectedCallback`
5. **M3** -- Add `aria-live="polite"` to results panel
6. **M5** -- Fix shadow DOM active element check in search bar's `/` handler
7. **M6** -- Add API client tests
8. **m6** -- Add keyboard accessibility to word chips
9. **M1** -- Fix `updated()` parameter type
10. **M4** -- Add response shape validation

Everything else can be addressed in polish passes.
