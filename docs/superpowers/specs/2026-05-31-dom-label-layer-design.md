# DOM Label Layer for the Force Graph — Design

**Date:** 2026-05-31
**Branch:** `metaphor-graph/grading-tool`
**Status:** Design (awaiting review) → implementation plan to follow

## Goal

Replace the WebGL `SpriteText` labels in `mf-force-graph` with an HTML/CSS label layer rendered through three.js `CSS2DRenderer`, so graph text is crisp at any zoom, freely styleable (background-opacity box + outline), legible by a configurable floor, and — crucially — **inspectable by tooling** (DOM `getBoundingClientRect` / `getComputedStyle`), which ends the "verify against my own projection maths" loop that produced three failed label fixes.

One label system serves **both** browse and grade modes; the sprite path is deleted.

## Why — the fix-forward diagnosis

The label sizing broke three times (blank → giant → unreadably-small-and-faint). Root cause of the *loop* (not the individual bugs): verification re-derived the renderer's own projection (`apparentPx = base.y · projFactor / dist`) and confirmed it — circular. It never checked rendered pixels or legibility. Root cause of the *current* symptom (from the code): labels are textures with `backgroundColor=false` and no stroke → low contrast; the min-px clamp floors at 11px (~8pt) and upscales a fixed-resolution texture → small and blurry.

DOM text fixes all of this structurally: resolution-independent (no blur), CSS-styleable (box + outline + size for free), and DOM-measurable (real layout pixels, an independent ground truth).

## Architecture

**The defining discovery (source-verified in `three-render-objects@^1.35`):** 3d-force-graph accepts an `extraRenderers` construction option. Its tick loop runs, after the WebGL render, `extraRenderers.forEach(r => r.render(state.scene, state.camera))` — **same scene, same camera, same frame** — sets each extra renderer's `domElement` to `position:absolute; top:0; pointer-events:none` overlaid on the canvas, and forwards `setSize()` on every resize. So a `CSS2DRenderer` passed here is driven automatically, glued to nodes under rotate/pan/zoom, with **no custom rAF and no hand-rolled projection**.

```
ForceGraph3D({ controlType: 'orbit', extraRenderers: [css2dRenderer] })(container)
```

**Label attachment:** each label is a `CSS2DObject` (wrapping a styled `<div>`) returned from `nodeThreeObject(n)`, with `nodeThreeObjectExtend(true)` kept so the default sphere — the raycast hit-target for hover/click — survives. Because the label rides as a child of the node's group (which lives in `graph.scene()`), the per-node position written by the force tick carries the label automatically, and the `extraRenderers` traversal reaches it. No `Map<nodeId, element>`, no `graph2ScreenCoords` bookkeeping.

This **deletes** `startLabelClampLoop()` / `labelClampRAF` entirely.

## Components & files

| File | Change |
|------|--------|
| `web/src/graph/label-layer.ts` | **New.** Self-contained, Lit-agnostic, mode-agnostic. Exports: `makeLabelRenderer(w,h)`, `makeLabelObject(style, cfg)`, `buildLabelEl(style, cfg)`, `syncLabelVisibility(nodes, isVisible)`, the pure `labelScale(...)` size-math fn, and types `LabelSizeMode` / `LabelSizeConfig` / `LabelStyle`. Callers pass a small style descriptor so one code path serves grade and browse palettes. |
| `web/src/components/mf-force-graph.ts` | Construct `CSS2DRenderer`, pass via `extraRenderers`; replace `nodeThreeObject` sprite creation with `makeLabelObject`; add `labelSize` reactive prop + per-mode default resolution; re-implement browse hover-border as a CSS class toggle on the label div; mirror `nodeVisibility` via `syncLabelVisibility`; delete `startLabelClampLoop`/`labelClampRAF`; add `__test_pauseAndRenderFrame()` / `__test_labelEls()` hooks; cleanup in `disconnectedCallback`. |
| `web/src/components/mf-force-graph.test.ts` | Drop the `three-spritetext` mock + sprite assertions (~10 tests); add a `three/addons/renderers/CSS2DRenderer.js` module mock mirroring the existing pattern; extend the `ForceGraph3D` Proxy mock to capture `extraRenderers`; assert on plain DOM (`textContent`, `style.color`, `dataset.role`, hover class). |
| `web/package.json` | Add `three` as a **direct** dependency pinned to `0.182.0` (lock the single hoisted instance; today it's transitive via 3d-force-graph's `>=0.118 <1`). Add `@playwright/test` devDependency. **Remove** `three-spritetext` once the sprite path is gone. |
| `web/playwright.config.ts` | **New.** `webServer` → `npm run dev` (5173); tests under `web/e2e/`. |
| `web/e2e/graph-labels.spec.ts` | **New.** Real-browser geometry/contrast assertions (happy-dom cannot run WebGL). |
| `web/src/types/3d-force-graph.d.ts` | Add `extraRenderers` to the construction-options type. |
| `.gitignore` | Add `.playwright-mcp/` and Playwright's `test-results/` / `playwright-report/`. |

## Key design decisions

**Size behaviour is a config setting** (per your call) — a reactive `@property({attribute:false}) labelSize: LabelSizeConfig`:

```ts
type LabelSizeMode = 'constant' | 'distance-floor'
interface LabelSizeConfig { mode: LabelSizeMode; basePx: number; minPx: number }
const DEFAULT_LABEL_SIZE: Record<'browse'|'grade', LabelSizeConfig> = {
  browse: { mode: 'distance-floor', basePx: 13, minPx: 10 }, // explore depth, but stay legible
  grade:  { mode: 'constant',       basePx: 13, minPx: 11 }, // flat constellation, uniform text
}
```

Effective config resolves in a getter (`this.labelSize ?? DEFAULT_LABEL_SIZE[this.mode]`) so a parent *can* override per instance but isn't forced to — grade vs browse falls out of the default map with no extra plumbing. The `minPx` floors (10/11) are lifted verbatim from the sprite era so behaviour is preserved as that path is deleted.

- **`constant`**: do nothing per-frame — a CSS div is laid out at its CSS px regardless of depth; on-screen size is constant by construction. Cheapest; best for thousands of nodes.
- **`distance-floor`**: emulate the old grow/shrink-with-distance feel but clamp to `minPx`. Applied via `CSS2DObject.onBeforeRender` (the per-object hook three already calls each render) scaling an **inner `<span>`** (the renderer overwrites the outer div's `transform` every frame, so we must not touch it). The scale maths is extracted as a **pure exported `labelScale()`** so it's unit-testable without a browser and reused in the hook.

**Visibility mirroring (the orphan-ghost-label pitfall).** `CSS2DRenderer` only toggles `display` while *traversing* the scene and never removes elements it appended. `nodeVisibility` removes a hidden node's whole group from the scene, so its label is never traversed → it lingers in the DOM at its last position with `display:''`. Fix: `syncLabelVisibility()` sets both `CSS2DObject.visible` and `element.style.display` from the same `isNodeVisible` predicate, called whenever `hiddenRarities` (today) or the future 2-hop fog-of-war changes the visible set. Grade mode has no rarity filter today, but this is the seam fog-of-war needs, so it's built now.

**Pointer-events.** The overlay root is forced `pointer-events:none` by three-render-objects (so orbit/pan/zoom drag through to the canvas). Label divs default to `pointer-events:none` too, so the existing sphere-raycast `onNode*` contract stays the single source of truth (no double-fire, no "label eats the drag"). Individual divs opt into `pointer-events:auto` only if a label-specific affordance is later added.

**Hover feedback.** Browse-mode `setNodeHoverBorder` (sprite border mutation) becomes a `.label-hovered` CSS class toggled on the node's label div via the existing `onNodeHover` callback (reached through `node.__threeObj.children.find(c => c.isCSS2DObject).element`).

**three pinned direct.** Prevents a future 3d-force-graph bump (range allows `<1`) from splitting `CSS2DObject`'s `Object3D` base across two three copies (which would silently break scene traversal / `instanceof`) or desyncing runtime from `@types/three`.

## Verification strategy — the actual fix for fix-forwarding

**Static-frame instrument.** `pauseAnimation()` stops the render loop, so the component exposes `__test_pauseAndRenderFrame()` which pauses then calls `labelRenderer.render(scene, camera)` exactly once against the frozen camera — deterministic, no rAF races. DOM labels are *always* in a screenshot (a frozen WebGL canvas can capture blank — `preserveDrawingBuffer` is false), so **machine assertions read the DOM, screenshots are for human eyeballing only.**

**Playwright e2e (real browser; greenfield — none installed yet).** After `__test_pauseAndRenderFrame()`, for each visible label:
- **Position (anti-self-confirmation):** compare two *independent* code paths — `graph.graph2ScreenCoords(x,y,z)` (the library's projector) on one side, the label div's `getBoundingClientRect` (the browser's layout of the real CSS transform) on the other, offset by the canvas's page rect and the configured `CSS2DObject.center`. They share only the camera object, never the pixel-mapping code, so a wiring bug (wrong `matrixWorld`, wrong centre, stale camera, mis-parented label) shows up as a mismatch. **Never hand-roll the `fov`/`tan` projection in the assertion** — that was the original bug.
- **Rotate / pan / zoom** each get their own frozen frame, driven by `graph.cameraPosition(pos, lookAt, 0)` (synchronous, no tween), re-running the position assertion — this is the explicit proof labels stay glued. One extra smoke test does a real damped mouse drag + wheel and polls until the camera is stable before asserting.
- **Min-px floor:** `rect.height >= minPx` in both modes; in `distance-floor`, zoom far out → height clamps to exactly the floor, zoom in → grows above it.
- **Contrast:** `getComputedStyle` — background alpha > 0, outline present (`textShadow !== 'none'` or `-webkit-text-stroke-width > 0`), role colour matches `GRADE_NODE_COLOURS` / `RARITY_COLOURS`.

**Unit tests (happy-dom, mocked).** Pure `labelScale()` formula; mode→default-config mapping; `buildLabelEl` produces a div with the right text/colour/role/styles; `syncLabelVisibility` toggles display; `extraRenderers` wired at construction. No WebGL.

## The raycaster hit-test offset — diagnose, then fix (scoped separately)

Long-standing (`≈ −1 × item-height`, pre-dates grade mode, affects browse). Research hypothesis is a devicePixelRatio mismatch in three-render-objects' pointer→NDC mapping (`Vector2(x/width·2−1, −(y/height)·2+1)`), **medium confidence, needs live diagnosis** — and the suspected fix sits in `node_modules` (would need `patch-package` or a container-level pointer correction). Because the static-frame instrument is exactly the tool to diagnose it empirically (click known screen coords, observe what raycasts), this spec **includes the diagnosis** as the final step but treats the *fix mechanism* as a follow-up decision once the root cause is confirmed — it is not on the label work's critical path, and a `node_modules` patch is a call for you to approve.

## Out of scope / future seams

- **Declutter / virtualise** for hundreds-to-thousands of labels: not built (YAGNI). The seam is in place — `syncLabelVisibility` + the `distance-floor` loop iterate only `CSS2DObject.visible` labels, and a future 2-hop fog-of-war just drives the visible predicate. Set `CSS2DRenderer.sortObjects = false` when that scale arrives (per-frame z-index sorting is O(n log n) DOM writes).
- **Label-specific affordances** (e.g. click-to-copy on text): trivial later via `pointer-events:auto` on the div.

## Risks (carried from research)

- `extraRenderers` is a **construction-time** option (no `graph.extraRenderers()` setter) — the `CSS2DRenderer` must exist before `ForceGraph3D({...})` in `firstUpdated`.
- Keep import + `vi.mock` specifiers **identical** (`three/addons/renderers/CSS2DRenderer.js`) or the real module loads in tests.
- `CSS2DRenderer` overwrites the outer div `transform` every render → distance-floor scale goes on an **inner span**.
- `setSize` is CSS-px native — **do not** multiply by devicePixelRatio (would offset labels on retina).
- Deleting the sprite path also removes `setNodeHoverBorder` and ~10 sprite-asserting unit tests — budget for *replacing* them, not just adding.

## Migration / deletion checklist

1. Add `three` direct dep + `@playwright/test`.
2. New `label-layer.ts` (TDD).
3. Rewire `mf-force-graph` to `extraRenderers` + `makeLabelObject`; delete clamp loop + sprite hover; add config + visibility mirror + test hooks.
4. Update unit tests (drop sprite mocks/assertions, add DOM assertions).
5. Playwright config + e2e geometry/contrast suite.
6. Remove `three-spritetext` dep + mock.
7. Diagnose the raycaster offset with the instrument; surface fix options.
