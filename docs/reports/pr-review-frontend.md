# PR Review: TypeScript Frontend

**Reviewer:** Code Review Agent (TypeScript Frontend)
**Range:** 639f366..380d9bb
**Scope:** web/

### Strengths

1. **Clean architecture and separation of concerns.** The codebase follows a clear layered pattern: pure types (`web/src/types/api.ts`, `web/src/graph/types.ts`), pure transformation logic (`web/src/graph/transform.ts`), side-effecting API client (`web/src/api/client.ts`), i18n abstraction (`web/src/lib/strings.ts`), and Lit components. Each layer depends only on layers below it.

2. **Solid test coverage for pure logic.** `web/src/graph/transform.test.ts` (9 tests) covers central node creation, synonym/hypernym/hyponym generation, deduplication, node capping with priority tiers, empty senses, and self-reference filtering. `web/src/api/client.test.ts` (5 tests) covers success, normalisation, HTTP errors with JSON/non-JSON bodies, and invalid response shape validation. `web/src/lib/strings.test.ts` (5 tests) covers init, interpolation, missing keys, pre-init fallback, and fetch failure.

3. **API response validation.** `web/src/api/client.ts:27-29` performs shape validation on the API response before returning it, rejecting payloads missing `word` or `senses`. This is a good defensive practice that many frontend codebases skip.

4. **WebGL resource cleanup.** `web/src/components/mf-force-graph.ts:137-149` properly pauses animation, disposes the Three.js renderer, disconnects the ResizeObserver, and clears the click timer in `disconnectedCallback()`. This prevents memory leaks when the component is removed from the DOM.

5. **FlyControls key capture prevention.** `web/src/components/mf-search-bar.ts:103-104` and `:124-125` stop propagation on both `keydown` and `keyup` events, preventing the 3d-force-graph FlyControls from interpreting WASD keypresses while the user is typing. The corresponding tests (`mf-search-bar.test.ts:49-68`) verify this explicitly.

6. **Debounced auto-suggest with minimum length.** `web/src/components/mf-search-bar.ts:90-99` implements a 200ms debounce with a 3-character minimum before firing suggest events. Enter bypasses the debounce and cancels any pending timer. This is well-tested across 4 debounce-specific tests.

7. **i18n wired throughout.** All user-facing strings in `mf-app.ts`, `mf-results-panel.ts`, and `mf-search-bar.ts` use `getString()` from the Fluent bundle rather than hardcoded English, matching the PRD requirement for Fluent-based localisation. The `.ftl` file at `web/public/strings/v1/ui.ftl` covers all keys used in the code.

8. **Proper Lit lifecycle management.** All components correctly call `super.connectedCallback()` and `super.disconnectedCallback()`. The search bar removes its global keydown listener on disconnect. The app shell removes the hashchange listener. Timers are cleaned up.

9. **Dark Academic theme implementation.** `web/src/styles/tokens.css` defines all CSS custom properties matching the PRD colour palette exactly, including node colours, backgrounds, text tones, edge colours, typography, and HUD tokens.

10. **Hash-based routing.** `web/src/components/mf-app.ts:114-124` implements `#/word/<word>` routing with both reading the hash on startup and listening for `hashchange` events, enabling deep-linking and browser back/forward navigation.

### Issues

#### Critical (Must Fix)

1. **Missing `/strings` proxy in Vite dev server config.**
   - File: `web/vite.config.ts:13-16`
   - The proxy configuration includes `/thesaurus`, `/forge`, and `/health` but is missing `/strings`. The Go backend serves the Fluent strings at `/strings/v1/ui.ftl`, and without this proxy, `initStrings()` in `web/src/lib/strings.ts:10` will get a 404 in development mode (unless served from `web/public/strings/` as a static file).
   - **Impact:** In development, the strings will be served from `web/public/strings/v1/ui.ftl` by Vite's static file serving (since `public/` is the default public directory). So this actually works in dev. However, in production deployment, the Go backend serves `/strings/v1/ui.ftl` and the frontend fetches from `/strings/v1/ui.ftl`. The missing proxy means dev and prod have divergent string sources. If the Go backend's strings file differs from the static `web/public/` copy, devs will see different strings in dev vs prod.
   - **Severity adjustment:** This is a correctness concern but not a blocker since the static file in `web/public/` acts as a fallback. Downgrading to Important.

#### Important (Should Fix)

2. **Missing `/strings` proxy causes dev/prod string divergence (promoted from Critical).**
   - File: `web/vite.config.ts:13-16`
   - Add `'/strings': 'http://localhost:8080'` to the proxy config so the dev server fetches strings from the Go backend, matching production behaviour.
   - The Phase 1 plan explicitly included this proxy route.

3. **No `aria-live` region for toast notifications.**
   - File: `web/src/components/mf-toast.ts:47-49`
   - The toast renders visible text but has no `role="status"` or `aria-live="polite"` attribute. Screen reader users will not be notified when a word is copied.
   - **Fix:** Add `role="status"` and `aria-live="polite"` to the toast container div.

4. **`mf-toast` has no `disconnectedCallback` to clear its timer.**
   - File: `web/src/components/mf-toast.ts:34`
   - The `hideTimer` is set in `show()` but never cleared if the element is removed from the DOM during the timeout.
   - **Impact:** Minor in practice since the toast lives for the app's lifetime, but it is a correctness issue. If the component were reused or removed, the timer callback would fire on a detached element.
   - **Fix:** Add `disconnectedCallback() { super.disconnectedCallback(); if (this.hideTimer) clearTimeout(this.hideTimer); }`.

5. **`@state()` used on `graph` field was correctly replaced with a private field, but `graphData` property on `mf-force-graph` triggers unnecessary re-renders.**
   - File: `web/src/components/mf-force-graph.ts:41`
   - `graphData` is declared with `@property({ type: Object })`. Since `GraphData` is an object reference, every time `mf-app` re-renders (e.g., on state change), the same object reference is passed through, and Lit's default dirty-checking (reference equality) means this is fine. However, if a new `GraphData` object is created for every render (which it is not here since `transformLookupToGraph` is only called in `doLookup`), this could cause redundant `graphData()` calls to 3d-force-graph.
   - **Current code is correct** in practice, but the `updated()` hook at line 131-134 should also handle the case where `graphData` is set to an empty graph (e.g., clearing the display). Currently it skips the update when `nodes.length === 0`, which means there is no way to clear the graph.
   - **Fix:** Change the condition in `updated()` from `this.graphData.nodes.length` to `true` (or at least allow empty graphs through).

6. **No test coverage for `mf-app.ts` or `mf-toast.ts`.**
   - These are the orchestrator and notification components. While `mf-app` is harder to unit test (it involves API calls and multiple child components), key logic like `doLookup`, `getWordFromHash`, `setWordHash`, and error state transitions could be tested with mocked fetch. The toast `show()` method is trivially testable.
   - **Impact:** The app shell contains the most complex state machine (`idle` -> `loading` -> `ready`/`error`) and it has zero test coverage.

7. **Double-click detection uses a manual timer instead of the native `dblclick` event.**
   - File: `web/src/components/mf-force-graph.ts:70-91`
   - The click handler sets a 200ms timer and relies on a second click arriving before the timer fires to detect double-click. This introduces a 200ms delay on every single-click select. The 3d-force-graph library provides `onNodeClick` but not a native `onNodeDblClick`, so the manual approach is understandable. However, 200ms is quite fast and may cause false double-click detection on slower clickers.
   - **Suggestion:** Consider using 250-300ms to match the typical OS double-click threshold, or document the intentional 200ms threshold.

8. **`mf-results-panel.test.ts` does not clean up elements in a `beforeEach`/`afterEach` pattern.**
   - File: `web/src/components/mf-results-panel.test.ts`
   - Each test creates and removes elements inline. If a test fails, the element is not removed from the DOM, potentially affecting subsequent tests.
   - **Fix:** Use `beforeEach`/`afterEach` hooks as done in `mf-search-bar.test.ts`.

9. **`handleNodeNavigate` in `mf-app.ts` uses `CustomEvent` without typed detail.**
   - File: `web/src/components/mf-app.ts:130`
   - The parameter type is `CustomEvent` (no generic), so `e.detail` is `any`. The handler then accesses `node?.word` without type checking.
   - **Fix:** Define a typed detail interface or at minimum type the parameter as `CustomEvent<{ word: string }>` and adjust the graph component's event dispatch to match.

10. **`prefers-reduced-motion` is not implemented.**
    - The PRD Section "Accessibility > Visual Accessibility" requires `prefers-reduced-motion` support. The Phase 1 plan explicitly defers this as a "Known Gap," so this is expected. Noting for tracking.

#### Minor (Nice to Have)

11. **Node colour map is duplicated between `mf-force-graph.ts` and CSS tokens.**
    - File: `web/src/components/mf-force-graph.ts:10-16` and `web/src/styles/tokens.css:17-21`
    - The hex colours for node types are defined both in the TypeScript `NODE_COLOURS` constant and in the CSS tokens. If the theme changes, both must be updated.
    - **Suggestion:** Consider reading the CSS custom properties from the host element at runtime, or extract the colour map to a shared constants module imported by both the graph component and the results panel CSS.

12. **`sprite.backgroundColor = false as unknown as string` is a questionable cast.**
    - File: `web/src/components/mf-force-graph.ts:59`
    - This casts `false` to `string` via `unknown` to disable the SpriteText background. While this works because three-spritetext accepts `false`, the double cast obscures intent.
    - **Suggestion:** Add a comment explaining why, or check if three-spritetext types accept `false | string`.

13. **Search bar `role="searchbox"` should be `role="search"` on the wrapping element.**
    - File: `web/src/components/mf-search-bar.ts:155`
    - The PRD specifies `role="search"` on the search bar. Currently, `role="searchbox"` is on the `<input>` element. The WAI-ARIA pattern recommends `role="search"` on the containing `<form>` or `<div>`, not on the input itself (which already has an implicit `textbox` role).
    - **Fix:** Add `role="search"` to the `.search-wrapper` div and remove `role="searchbox"` from the input.

14. **CSS tokens use `px` for `--hud-width` instead of `rem`.**
    - File: `web/src/styles/tokens.css:40`
    - The PRD states "HUD uses `rem` units" for font scaling. The HUD width is `320px`. This is a minor inconsistency; the panel width being fixed in `px` is reasonable, but noting it for completeness.

15. **`getString()` import in `mf-app.ts` is unused indirectly after switch to Fluent strings.**
    - File: `web/src/components/mf-app.ts:5`
    - `getString` is imported and used correctly. However, `initStrings` is imported as well. Both are used, so this is actually fine. No issue.

16. **No `<meta name="description">` or favicon in `index.html`.**
    - File: `web/index.html`
    - Minor SEO/UX polish. Not critical for an MVP.

17. **The `/` keyboard shortcut handler does not check for `e.target` inside shadow roots of other components.**
    - File: `web/src/components/mf-search-bar.ts:66-79`
    - The guard checks `document.activeElement` but in a shadow DOM context, if another component's shadow root has an input focused, `document.activeElement` would be the host element (not the input). The code handles this for its own shadow root (line 76) but not for other potential shadow-rooted inputs. In practice this is fine since `mf-search-bar` is the only input component, but worth noting for future-proofing.

### Recommendations

1. **Add the missing `/strings` proxy route to `vite.config.ts`.** This is a one-line fix that aligns dev behaviour with production.

2. **Add basic tests for `mf-app.ts` state transitions.** At minimum, test that `doLookup` transitions from `idle` -> `loading` -> `ready` on success and `idle` -> `loading` -> `error` on failure. Mock `lookupWord` and verify `graphData` and `result` are set. This is the component with the most complex logic and zero test coverage.

3. **Add `disconnectedCallback` to `mf-toast.ts`** and add `aria-live="polite"` to the toast div. Both are small changes with meaningful impact on correctness and accessibility.

4. **Allow clearing the graph.** Change the guard in `mf-force-graph.ts:132` from `this.graphData.nodes.length` to allow empty data through. This enables future features like clearing the display on error.

5. **Standardise test cleanup.** The `mf-results-panel.test.ts` should adopt the `beforeEach`/`afterEach` pattern used in `mf-search-bar.test.ts` for consistency and to avoid leaking DOM elements on test failure.

6. **Consider extracting the colour map** to a shared constant to avoid duplication between the TypeScript graph component and CSS tokens.

### Assessment

**Ready to merge?** Yes, with fixes

**Reasoning:** The implementation is well-structured, the 33 tests all pass, TypeScript compilation is clean, and the architecture closely follows both the PRD and Phase 1 plan. The issues identified are primarily polish items: a missing proxy route (which works around itself via static files), a missing timer cleanup in the toast, an accessibility gap on the toast, and missing tests for the app shell. None of these are blocking bugs. The most impactful fix is the `/strings` proxy route (1 line), followed by adding `mf-app` test coverage. The codebase demonstrates solid engineering practices overall -- proper lifecycle cleanup, typed events, FlyControls interaction awareness, Fluent i18n integration, and defensive API response validation.
