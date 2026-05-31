# DOM Label Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `mf-force-graph`'s WebGL `SpriteText` labels with an HTML/CSS label layer rendered through three.js `CSS2DRenderer`, configurable per mode (`constant` | `distance-floor`), verified against an independent-code-path Playwright suite.

**Architecture:** A `CSS2DRenderer` is passed to `ForceGraph3D({ extraRenderers: [...] })`. three-render-objects renders it every tick with the same scene + camera, overlays its `pointer-events:none` `<div>` on the canvas (inside our shadow root), and forwards `setSize` on resize — so labels stay glued under rotate/pan/zoom with **no custom rAF and no hand-rolled projection**. Each label is a `CSS2DObject` (styled `<div>` + inner `<span>`) returned from `nodeThreeObject`, riding on the node group (`nodeThreeObjectExtend(true)` keeps the raycast sphere). One label system serves browse + grade. The `startLabelClampLoop` is deleted.

**Tech Stack:** Lit 3, Vite 6, TypeScript, 3d-force-graph 1.77, three 0.182 (`CSS2DRenderer`/`CSS2DObject` from `three/addons`), Vitest + happy-dom (unit, mocked), Playwright (e2e, real browser).

**Reference:** spec at `docs/superpowers/specs/2026-05-31-dom-label-layer-design.md`. Current component: `web/src/components/mf-force-graph.ts` (554 lines, read it). All commands run from `web/`. UK English. TDD: failing test first, minimal code, commit on green.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `web/src/graph/label-layer.ts` | **New.** Lit-agnostic, mode-agnostic label primitives: types, defaults, the pure `labelScale()`, `buildLabelEl()`, `makeLabelObject()`, `makeLabelRenderer()`, `syncLabelVisibility()`, `LABEL_CENTER`. |
| `web/src/graph/label-layer.test.ts` | **New.** Unit tests for the pure/DOM-buildable pieces (happy-dom; `CSS2DRenderer`/`CSS2DObject` mocked). |
| `web/src/components/mf-force-graph.ts` | Wire `extraRenderers`; replace sprite creation; add `labelSize` prop + resolution; CSS-class hover; visibility mirror; delete clamp loop + sprite path; test hooks; component CSS. |
| `web/src/components/mf-force-graph.test.ts` | Add `CSS2DRenderer` mock, capture `extraRenderers`, assert on DOM labels; drop sprite mock/assertions. |
| `web/src/types/3d-force-graph.d.ts` | Add `extraRenderers` to the construction-options type. |
| `web/package.json` | `three@0.182.0` direct dep; `@playwright/test` devDep; remove `three-spritetext`. |
| `web/playwright.config.ts` | **New.** e2e config. |
| `web/e2e/graph-labels.spec.ts` | **New.** Real-browser geometry/contrast/transform assertions. |
| `web/e2e/raycaster-offset.spec.ts` | **New.** Diagnostic harness for the hit-test offset (findings only). |
| `.gitignore` | Ignore `.playwright-mcp/`, `web/test-results/`, `web/playwright-report/`. |

---

## Task 1: Dependencies, types, gitignore

**Files:**
- Modify: `web/package.json`
- Modify: `web/src/types/3d-force-graph.d.ts:42-44`
- Modify: `.gitignore`

- [ ] **Step 1: Pin three; do NOT remove three-spritetext yet** (it's still imported until Task 9). `@playwright/test` is added in Task 10, not here, so this task stays offline-safe.

In `web/package.json` `dependencies`, add `"three": "0.182.0"` (exact pin — matches the hoisted version and `@types/three@^0.182.0`).

- [ ] **Step 2: Install (offline-safe — three@0.182.0 is already hoisted)**

```bash
cd web && npm install
```
Expected: completes without a network fetch; `node_modules/three` stays at 0.182.0 (single hoisted copy). Records `three` in package.json + lockfile.

- [ ] **Step 3: Add `extraRenderers` to the construction-options type**

In `web/src/types/3d-force-graph.d.ts`, change the `ForceGraph3D` function signature options:
```ts
  function ForceGraph3D(
    options?: { controlType?: string; extraRenderers?: unknown[] },
  ): (container: HTMLElement) => ForceGraph3DInstance
```
(`unknown[]` avoids importing three's renderer types here; the call site passes a `CSS2DRenderer`.)

- [ ] **Step 4: gitignore scratch + Playwright artefacts**

Append to `.gitignore`:
```
.playwright-mcp/
web/test-results/
web/playwright-report/
```

- [ ] **Step 5: Verify typecheck + import resolves**

```bash
cd web && npx tsc --noEmit
```
Expected: PASS (no errors). If `three/addons/...` is referenced anywhere yet it isn't — that's Task 2.

- [ ] **Step 6: Commit**

```bash
git add web/package.json web/package-lock.json web/src/types/3d-force-graph.d.ts .gitignore
git commit -m "build(grading-ui): pin three@0.182.0, add @playwright/test, extraRenderers type"
```

---

## Task 2: `label-layer.ts` — types, defaults, pure `labelScale`, `buildLabelEl`

**Files:**
- Create: `web/src/graph/label-layer.ts`
- Create: `web/src/graph/label-layer.test.ts`

- [ ] **Step 1: Write failing tests**

`web/src/graph/label-layer.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import {
  labelScale, buildLabelEl, DEFAULT_LABEL_SIZE, LABEL_CENTER,
  type LabelSizeConfig,
} from './label-layer'

const CONST: LabelSizeConfig = { mode: 'constant', basePx: 13, minPx: 11 }
const DIST: LabelSizeConfig = { mode: 'distance-floor', basePx: 13, minPx: 10 }

describe('labelScale', () => {
  it('constant mode is always 1 regardless of distance', () => {
    expect(labelScale(CONST, 50, 200)).toBe(1)
    expect(labelScale(CONST, 5000, 200)).toBe(1)
  })
  it('distance-floor is 1 at the reference distance', () => {
    expect(labelScale(DIST, 200, 200)).toBeCloseTo(1)
  })
  it('distance-floor never exceeds 1 when closer than reference (no magnification)', () => {
    expect(labelScale(DIST, 50, 200)).toBe(1)
  })
  it('distance-floor shrinks with distance but never below the minPx/basePx floor', () => {
    expect(labelScale(DIST, 400, 200)).toBeCloseTo(0.5) // 200/400, above floor 10/13≈0.769? -> clamped
    // 10/13 ≈ 0.769 floor; 200/400=0.5 is below floor → clamps to 0.769
    expect(labelScale(DIST, 400, 200)).toBeCloseTo(10 / 13)
    expect(labelScale(DIST, 100000, 200)).toBeCloseTo(10 / 13)
  })
})

describe('buildLabelEl', () => {
  it('outer div carries class + role data-attr, inner span carries the text', () => {
    const el = buildLabelEl({ text: 'venom', colour: '#6fb8e0', role: 'vehicle' }, CONST)
    expect(el.className).toBe('mf-graph-label')
    expect(el.dataset.role).toBe('vehicle')
    const span = el.querySelector('span.mf-graph-label__text') as HTMLSpanElement
    expect(span.textContent).toBe('venom')
    expect(span.style.color).toBe('rgb(111, 184, 224)')
  })
  it('has a contrast background and a text outline', () => {
    const el = buildLabelEl({ text: 'x', colour: '#fff', role: 'step' }, CONST)
    // background alpha > 0
    expect(el.style.background).toMatch(/rgba?\(/)
    const span = el.querySelector('span') as HTMLSpanElement
    expect(span.style.textShadow).not.toBe('')
  })
  it('font size is basePx and pointer-events are disabled', () => {
    const el = buildLabelEl({ text: 'x', colour: '#fff', role: 'step' }, CONST)
    expect(el.style.pointerEvents).toBe('none')
    const span = el.querySelector('span') as HTMLSpanElement
    expect(span.style.fontSize).toBe('13px')
  })
})

describe('defaults', () => {
  it('browse is distance-floor 13/10, grade is constant 13/11', () => {
    expect(DEFAULT_LABEL_SIZE.browse).toEqual({ mode: 'distance-floor', basePx: 13, minPx: 10 })
    expect(DEFAULT_LABEL_SIZE.grade).toEqual({ mode: 'constant', basePx: 13, minPx: 11 })
  })
  it('label anchor floats just above the node', () => {
    expect(LABEL_CENTER).toEqual({ x: 0.5, y: 1.1 })
  })
})
```

- [ ] **Step 2: Run — verify it fails**

```bash
cd web && npx vitest run src/graph/label-layer.test.ts
```
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the pure + DOM-buildable pieces**

`web/src/graph/label-layer.ts` (the `CSS2DObject`/renderer pieces come in Task 3 — keep this file importable without three for now by NOT importing three yet; add the three import in Task 3):
```ts
// Label primitives for the force graph's CSS2D label layer.
// Lit-agnostic and mode-agnostic: callers pass a LabelStyle + LabelSizeConfig,
// so one code path serves both grade and browse palettes.

export type LabelSizeMode = 'constant' | 'distance-floor'

export interface LabelSizeConfig {
  mode: LabelSizeMode
  basePx: number // on-screen px when at/closer-than the reference distance
  minPx: number  // floor — rendered px never drops below this
}

export interface LabelStyle {
  text: string
  colour: string
  role: string // grade: topic|vehicle|step; browse: central|<rarity>
}

export const DEFAULT_LABEL_SIZE: Record<'browse' | 'grade', LabelSizeConfig> = {
  browse: { mode: 'distance-floor', basePx: 13, minPx: 10 },
  grade: { mode: 'constant', basePx: 13, minPx: 11 },
}

// Anchor: label centred horizontally, floated just above the node (y=1.1 lifts
// it by 110% of its own height). Exported so the e2e test asserts against the
// same value rather than a hardcoded 0.5.
export const LABEL_CENTER = { x: 0.5, y: 1.1 }

const LABEL_FONT = 'Georgia, "Times New Roman", serif'

/**
 * On-screen scale multiplier for a label. Pure — unit-tested without a browser.
 * `constant`: always 1 (CSS px is screen-constant by construction).
 * `distance-floor`: `refDist/dist`, capped at 1 (never magnifies past basePx)
 * and floored at `minPx/basePx` (never shrinks below minPx). Bounded both ends,
 * so the magnification-bug class is impossible.
 */
export function labelScale(cfg: LabelSizeConfig, dist: number, refDist: number): number {
  if (cfg.mode === 'constant') return 1
  const raw = refDist / Math.max(dist, 1e-6)
  const floor = cfg.minPx / cfg.basePx
  return Math.min(1, Math.max(floor, raw))
}

/**
 * Build the styled label element: an outer `.mf-graph-label` div (whose
 * `transform` CSS2DRenderer overwrites every frame) wrapping an inner
 * `.mf-graph-label__text` span (which we scale for distance-floor, leaving the
 * renderer's translate untouched). Plain DOM → happy-dom-assertable.
 */
export function buildLabelEl(style: LabelStyle, cfg: LabelSizeConfig): HTMLDivElement {
  const el = document.createElement('div')
  el.className = 'mf-graph-label'
  el.dataset.role = style.role
  el.style.pointerEvents = 'none' // keep sphere raycast the single hit source
  el.style.position = 'absolute'
  el.style.background = 'rgba(20, 20, 40, 0.55)' // contrast box
  el.style.borderRadius = '3px'
  el.style.padding = '1px 4px'
  el.style.willChange = 'transform'

  const span = document.createElement('span')
  span.className = 'mf-graph-label__text'
  span.textContent = style.text
  span.style.color = style.colour
  span.style.fontFamily = LABEL_FONT
  span.style.fontSize = `${cfg.basePx}px`
  span.style.whiteSpace = 'nowrap'
  span.style.display = 'inline-block'
  span.style.transformOrigin = 'center'
  span.style.textShadow = '0 0 2px #000, 0 0 3px #000' // outline for legibility
  el.appendChild(span)
  return el
}
```

- [ ] **Step 4: Run — verify pass**

```bash
cd web && npx vitest run src/graph/label-layer.test.ts
```
Expected: PASS (all). Note `rgb(111, 184, 224)` is happy-dom's normalisation of `#6fb8e0`.

- [ ] **Step 5: Commit**

```bash
git add web/src/graph/label-layer.ts web/src/graph/label-layer.test.ts
git commit -m "feat(grading-ui): label-layer primitives (labelScale, buildLabelEl, defaults)"
```

---

## Task 3: `label-layer.ts` — `makeLabelRenderer`, `makeLabelObject`, `syncLabelVisibility`

**Files:**
- Modify: `web/src/graph/label-layer.ts`
- Modify: `web/src/graph/label-layer.test.ts`

- [ ] **Step 1: Write failing tests** (append to `label-layer.test.ts`; add the mock at top of file, see note)

At the **top** of `web/src/graph/label-layer.test.ts`, add the CSS2D mock (must precede the import under test):
```ts
import { vi } from 'vitest'
vi.mock('three/addons/renderers/CSS2DRenderer.js', () => ({
  CSS2DRenderer: vi.fn().mockImplementation(() => ({
    domElement: document.createElement('div'),
    setSize: vi.fn(),
    render: vi.fn(),
  })),
  CSS2DObject: vi.fn().mockImplementation((el?: HTMLElement) => ({
    element: el ?? document.createElement('div'),
    isCSS2DObject: true,
    visible: true,
    position: { x: 0, y: 0, z: 0, set(x: number, y: number, z: number) { this.x = x; this.y = y; this.z = z } },
    center: { x: 0.5, y: 0.5, set(x: number, y: number) { this.x = x; this.y = y } },
    onBeforeRender: undefined as undefined | ((r: unknown, s: unknown, c: unknown) => void),
  })),
}))
```
Append tests:
```ts
import { makeLabelRenderer, makeLabelObject, syncLabelVisibility } from './label-layer'

describe('makeLabelRenderer', () => {
  it('creates a renderer and sizes it', () => {
    const r = makeLabelRenderer(800, 600) as unknown as { setSize: ReturnType<typeof vi.fn> }
    expect(r.setSize).toHaveBeenCalledWith(800, 600)
  })
})

describe('makeLabelObject', () => {
  it('wraps the styled element and sets the anchor centre', () => {
    const obj = makeLabelObject(
      { text: 'venom', colour: '#6fb8e0', role: 'vehicle' },
      () => DEFAULT_LABEL_SIZE.grade, () => 200,
    ) as unknown as { element: HTMLElement; center: { x: number; y: number } }
    expect(obj.element.querySelector('span')!.textContent).toBe('venom')
    expect(obj.center.x).toBe(LABEL_CENTER.x)
    expect(obj.center.y).toBe(LABEL_CENTER.y)
  })
  it('distance-floor mode scales the inner span on render; constant mode leaves it at scale(1)', () => {
    const distObj = makeLabelObject(
      { text: 'x', colour: '#fff', role: 'step' },
      () => ({ mode: 'distance-floor', basePx: 13, minPx: 10 }), () => 200,
    ) as unknown as { element: HTMLElement; position: { y: number }; onBeforeRender: (r: unknown, s: unknown, c: { position: { x: number; y: number; z: number } }) => void }
    const span = distObj.element.querySelector('span') as HTMLSpanElement
    const cam = { position: { x: 0, y: distObj.position.y, z: 400 } } // dist 400 from origin
    distObj.onBeforeRender({}, {}, cam)
    expect(span.style.transform).toBe(`scale(${10 / 13})`) // floored

    const constObj = makeLabelObject(
      { text: 'x', colour: '#fff', role: 'step' },
      () => ({ mode: 'constant', basePx: 13, minPx: 11 }), () => 200,
    ) as unknown as { element: HTMLElement; onBeforeRender: (r: unknown, s: unknown, c: { position: { x: number; y: number; z: number } }) => void }
    const cspan = constObj.element.querySelector('span') as HTMLSpanElement
    constObj.onBeforeRender({}, {}, { position: { x: 0, y: 0, z: 400 } })
    expect(cspan.style.transform).toBe('scale(1)')
  })
})

describe('syncLabelVisibility', () => {
  it('hides labels for nodes failing the predicate, shows the rest', () => {
    const mk = () => ({ isCSS2DObject: true, visible: true, element: document.createElement('div') })
    const a = mk(); const b = mk()
    const nodes = [
      { id: 'a', __threeObj: { children: [a] } },
      { id: 'b', __threeObj: { children: [b] } },
    ]
    syncLabelVisibility(nodes, n => (n as { id: string }).id === 'a')
    expect(a.visible).toBe(true); expect(a.element.style.display).toBe('')
    expect(b.visible).toBe(false); expect(b.element.style.display).toBe('none')
  })
})
```

- [ ] **Step 2: Run — verify it fails**

```bash
cd web && npx vitest run src/graph/label-layer.test.ts
```
Expected: FAIL (`makeLabelRenderer`/`makeLabelObject`/`syncLabelVisibility` not exported).

- [ ] **Step 3: Implement** (add the three import + three functions to `label-layer.ts`)

Add at the **top** of `web/src/graph/label-layer.ts`:
```ts
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js'
```
Append:
```ts
/** Construct the overlay renderer. Pass it to ForceGraph3D({ extraRenderers }) —
 *  three-render-objects positions/sizes/renders it automatically. */
export function makeLabelRenderer(width: number, height: number): CSS2DRenderer {
  const r = new CSS2DRenderer()
  r.setSize(width, height)
  return r
}

/**
 * One label per node, returned from nodeThreeObject (with extend=true so the
 * raycast sphere survives). The element rides on the node group, so the force
 * tick positions it and the extraRenderers pass projects it — no manual maths.
 * `getCfg`/`getRefDist` are read live each frame so reactive changes apply.
 */
export function makeLabelObject(
  style: LabelStyle,
  getCfg: () => LabelSizeConfig,
  getRefDist: () => number,
): CSS2DObject {
  const el = buildLabelEl(style, getCfg())
  const span = el.querySelector('span.mf-graph-label__text') as HTMLSpanElement
  const obj = new CSS2DObject(el)
  obj.center.set(LABEL_CENTER.x, LABEL_CENTER.y)
  // Same-frame per-object hook CSS2DRenderer calls during render (verified
  // CSS2DRenderer.js:236). Scales the INNER span (renderer overwrites the outer
  // transform). constant mode → scale 1 (cheap no-op).
  obj.onBeforeRender = (_r: unknown, _s: unknown, camera: unknown) => {
    const cfg = getCfg()
    const cam = camera as { position: { x: number; y: number; z: number } }
    const dx = cam.position.x - obj.position.x
    const dy = cam.position.y - obj.position.y
    const dz = cam.position.z - obj.position.z
    const dist = Math.hypot(dx, dy, dz) || 1
    span.style.transform = `scale(${labelScale(cfg, dist, getRefDist())})`
  }
  return obj
}

/**
 * Mirror a node-visibility predicate onto label DOM, defeating the
 * CSS2DRenderer orphan-element pitfall (it only toggles display while
 * traversing; a node filtered out of the scene leaves its label stuck visible).
 * Sets BOTH CSS2DObject.visible (honoured when traversed) and element.display
 * (belt-and-braces for filtered-out nodes).
 */
export function syncLabelVisibility(
  nodes: Array<{ __threeObj?: { children?: Array<{ isCSS2DObject?: boolean; visible: boolean; element: HTMLElement }> } }>,
  isVisible: (n: unknown) => boolean,
): void {
  for (const n of nodes) {
    const label = n.__threeObj?.children?.find(c => c.isCSS2DObject)
    if (!label) continue
    const vis = isVisible(n)
    label.visible = vis
    label.element.style.display = vis ? '' : 'none'
  }
}
```

- [ ] **Step 4: Run — verify pass**

```bash
cd web && npx vitest run src/graph/label-layer.test.ts
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/graph/label-layer.ts web/src/graph/label-layer.test.ts
git commit -m "feat(grading-ui): CSS2D label object/renderer + visibility mirror"
```

---

## Task 4: Wire `extraRenderers` into `mf-force-graph` (renderer construction)

**Files:**
- Modify: `web/src/components/mf-force-graph.test.ts:94-99` (extend ForceGraph3D mock) + add CSS2D mock
- Modify: `web/src/components/mf-force-graph.ts:198-202` (firstUpdated head)

- [ ] **Step 1: Extend the test mock to capture `extraRenderers` + mock CSS2D**

In `web/src/components/mf-force-graph.test.ts`, add near the other `let captured…` declarations:
```ts
let capturedExtraRenderers: unknown[] | undefined = undefined
```
Add the CSS2D module mock alongside the existing `vi.mock` calls (keep the `three-spritetext` mock for now — removed in Task 9):
```ts
vi.mock('three/addons/renderers/CSS2DRenderer.js', () => ({
  CSS2DRenderer: vi.fn().mockImplementation(() => ({
    domElement: document.createElement('div'), setSize: vi.fn(), render: vi.fn(),
  })),
  CSS2DObject: vi.fn().mockImplementation((el?: HTMLElement) => ({
    element: el ?? document.createElement('div'), isCSS2DObject: true, visible: true,
    position: { x: 0, y: 0, z: 0, set() {} },
    center: { x: 0.5, y: 0.5, set(this: { x: number; y: number }, x: number, y: number) { this.x = x; this.y = y } },
    onBeforeRender: undefined,
  })),
}))
```
Change the `3d-force-graph` mock to capture `extraRenderers`:
```ts
vi.mock('3d-force-graph', () => ({
  default: (opts?: { controlType?: string; extraRenderers?: unknown[] }) => {
    capturedControlType = opts?.controlType
    capturedExtraRenderers = opts?.extraRenderers
    return () => chainable
  },
}))
```
Reset it in `beforeEach`: `capturedExtraRenderers = undefined`.

- [ ] **Step 2: Write the failing test** (add inside the top-level `describe('MfForceGraph', …)`)

```ts
it('constructs the graph with a CSS2D extra renderer', () => {
  expect(Array.isArray(capturedExtraRenderers)).toBe(true)
  expect(capturedExtraRenderers!.length).toBe(1)
})
```

- [ ] **Step 3: Run — verify it fails**

```bash
cd web && npx vitest run src/components/mf-force-graph.test.ts -t "extra renderer"
```
Expected: FAIL (`capturedExtraRenderers` undefined).

- [ ] **Step 4: Implement — build the renderer before the graph**

In `web/src/components/mf-force-graph.ts`:
- Add import near the top: `import { makeLabelRenderer } from '@/graph/label-layer'`
- Add a field near `private graph…`: `private labelRenderer: ReturnType<typeof makeLabelRenderer> | null = null`
- In `firstUpdated`, after the `this.container` guard (line 200) and before `this.graph = ForceGraph3D(...)`:
```ts
    this.labelRenderer = makeLabelRenderer(this.container.clientWidth, this.container.clientHeight)
```
- Change the construction call (line 202) to:
```ts
    this.graph = ForceGraph3D({ controlType: 'orbit', extraRenderers: [this.labelRenderer] })(this.container)
```

- [ ] **Step 5: Run — verify pass**

```bash
cd web && npx vitest run src/components/mf-force-graph.test.ts -t "extra renderer"
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/src/components/mf-force-graph.ts web/src/components/mf-force-graph.test.ts
git commit -m "feat(grading-ui): wire CSS2DRenderer via extraRenderers in mf-force-graph"
```

---

## Task 5: Replace sprite creation with `makeLabelObject` + `labelSize` config

**Files:**
- Modify: `web/src/components/mf-force-graph.ts` (nodeThreeObject 216-241; add prop + getter + `labelStyleFor`)
- Modify: `web/src/components/mf-force-graph.test.ts` (replace the order-2 sprite-size test)

- [ ] **Step 1: Write the failing tests**

Replace the existing sprite-size test (`'uses smaller label sprite for order-2 nodes'`, ~line 645) and add config tests:
```ts
it('nodeThreeObject builds a DOM label with the node word and rarity colour (browse)', () => {
  const ember = { id: 'ember', word: 'ember', relationType: 'synonym', rarity: 'common', order: 2 }
  const obj = capturedNodeThreeObject!(ember) as { element: HTMLElement }
  const span = obj.element.querySelector('span.mf-graph-label__text') as HTMLSpanElement
  expect(span.textContent).toBe('ember')
  expect(span.style.color).toBe('rgb(127, 176, 105)') // RARITY_COLOURS.common normalised
})

it('effective label config defaults to browse distance-floor / grade constant', async () => {
  expect(el.effectiveLabelSize).toEqual({ mode: 'distance-floor', basePx: 13, minPx: 10 })
  const g = new MfForceGraph(); g.mode = 'grade'
  document.body.appendChild(g); await g.updateComplete
  expect(g.effectiveLabelSize).toEqual({ mode: 'constant', basePx: 13, minPx: 11 })
  document.body.removeChild(g)
})
```
(Confirm `RARITY_COLOURS.common` — if it isn't `#7fb069`, use the actual normalised rgb. The implementer must read `web/src/graph/colours.ts` and match.)

- [ ] **Step 2: Run — verify it fails**

```bash
cd web && npx vitest run src/components/mf-force-graph.test.ts -t "DOM label"
```
Expected: FAIL.

- [ ] **Step 3: Implement**

In `web/src/components/mf-force-graph.ts`:
- Import: `import { makeLabelRenderer, makeLabelObject, DEFAULT_LABEL_SIZE, type LabelSizeConfig, type LabelStyle } from '@/graph/label-layer'` (merge with the Task 4 import).
- Add reactive prop near the others (line 86-91):
```ts
  @property({ attribute: false }) labelSize: LabelSizeConfig | null = null
```
- Add a field for the reference distance: `private labelRefDist = 200`
- Add the getter (public for tests):
```ts
  /** Resolved label sizing: explicit prop overrides the per-mode default. */
  get effectiveLabelSize(): LabelSizeConfig {
    return this.labelSize ?? DEFAULT_LABEL_SIZE[this.mode]
  }
```
- Add `labelStyleFor` (reuses the exact colour logic from the old sprite branch):
```ts
  private labelStyleFor(n: unknown): LabelStyle {
    if (this.mode === 'grade') {
      const gn = n as GradeNode
      return { text: gn.phrase, colour: GRADE_NODE_COLOURS[gn.role], role: gn.role }
    }
    const node = n as GraphNode
    const colour = node.relationType === 'central'
      ? NODE_COLOURS.central
      : RARITY_COLOURS[node.rarity ?? 'unusual'] ?? DEFAULT_NODE_COLOUR
    return { text: node.word, colour, role: node.relationType === 'central' ? 'central' : (node.rarity ?? 'unusual') }
  }
```
- Replace the entire `.nodeThreeObject((n) => { …sprite… })` body (216-241) with:
```ts
      .nodeThreeObject((n: unknown) => makeLabelObject(
        this.labelStyleFor(n),
        () => this.effectiveLabelSize,
        () => this.labelRefDist,
      ))
```
- Remove the now-unused `LABEL_FONT`, `GRADE_LABEL_HEIGHT` consts (lines 13, 32-36) **only if** nothing else references them (the clamp loop, removed in Task 6, used `GRADE_LABEL_HEIGHT` indirectly via fontSize — grep first). Keep `GRADE_LABEL_MIN_PX` until Task 6.

- [ ] **Step 4: Run — verify pass**

```bash
cd web && npx vitest run src/components/mf-force-graph.test.ts -t "DOM label"
cd web && npx vitest run src/components/mf-force-graph.test.ts -t "label config"
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/mf-force-graph.ts web/src/components/mf-force-graph.test.ts
git commit -m "feat(grading-ui): DOM labels via makeLabelObject + per-mode labelSize config"
```

---

## Task 6: Delete the clamp loop; capture reference distance

**Files:**
- Modify: `web/src/components/mf-force-graph.ts` (remove `startLabelClampLoop`/`labelClampRAF`; grade block 353-358; disconnect 538; capture `labelRefDist` in the framing rAF 361-378)

- [ ] **Step 1: Write the failing test** (the clamp loop must be gone; ref dist captured)

```ts
it('no longer runs a sprite clamp loop (startLabelClampLoop removed)', () => {
  expect((el as unknown as Record<string, unknown>).startLabelClampLoop).toBeUndefined()
  expect((el as unknown as Record<string, unknown>).labelClampRAF).toBeUndefined()
})
```

- [ ] **Step 2: Run — verify it fails**

```bash
cd web && npx vitest run src/components/mf-force-graph.test.ts -t "clamp loop removed"
```
Expected: FAIL (method/field still present).

- [ ] **Step 3: Implement the deletions + ref-dist capture**

In `web/src/components/mf-force-graph.ts`:
- Delete the `private labelClampRAF: number | null = null` field (line 82).
- Delete the whole `startLabelClampLoop()` method (lines 402-447).
- In the grade-mode block (353-358), remove the `this.startLabelClampLoop()` call (keep `nodeRelSize(2)` + the two `d3Force` lines).
- In `disconnectedCallback`, remove `if (this.labelClampRAF) cancelAnimationFrame(this.labelClampRAF)` (line 538).
- Delete the now-unused `GRADE_LABEL_MIN_PX` const (39) and `GRADE_LABEL_HEIGHT` if still present.
- In the framing rAF (361-378), capture the reference distance just after the camera pull-in:
```ts
      if (this.graph) {
        const camera = this.graph.camera() as { position: { x: number; y: number; z: number } }
        camera.position.z *= 0.65
        // Distance at which distance-floor labels render at full basePx.
        this.labelRefDist = Math.hypot(camera.position.x, camera.position.y, camera.position.z) || 200
        // …existing controls damping…
      }
```

- [ ] **Step 4: Run — verify pass + full file typechecks**

```bash
cd web && npx vitest run src/components/mf-force-graph.test.ts -t "clamp loop removed"
cd web && npx tsc --noEmit
```
Expected: PASS; tsc clean (if tsc flags unused `GRADE_LABEL_HEIGHT`/`LABEL_FONT`, remove them).

- [ ] **Step 5: Commit**

```bash
git add web/src/components/mf-force-graph.ts web/src/components/mf-force-graph.test.ts
git commit -m "refactor(grading-ui): delete sprite clamp loop, capture label refDist"
```

---

## Task 7: Hover highlight as a CSS class on the label div

**Files:**
- Modify: `web/src/components/mf-force-graph.ts` (`setNodeHoverBorder` → `setLabelHover`; component `static styles`)
- Modify: `web/src/components/mf-force-graph.test.ts` (replace the sprite-border hover test)

- [ ] **Step 1: Write the failing test** (replace the existing hover-border test ~line 296-329)

```ts
it('toggles .label-hovered on the node label div on hover in/out (browse)', () => {
  const labelEl = document.createElement('div')
  const node = { id: 'blaze', word: 'blaze', relationType: 'synonym', rarity: 'common', order: 1,
    __threeObj: { children: [{ isCSS2DObject: true, element: labelEl }] } }
  capturedOnNodeHover!(node, null)
  expect(labelEl.classList.contains('label-hovered')).toBe(true)
  capturedOnNodeHover!(null, node)
  expect(labelEl.classList.contains('label-hovered')).toBe(false)
})
```

- [ ] **Step 2: Run — verify it fails**

```bash
cd web && npx vitest run src/components/mf-force-graph.test.ts -t "label-hovered"
```
Expected: FAIL.

- [ ] **Step 3: Implement**

In `web/src/components/mf-force-graph.ts`:
- Replace `setNodeHoverBorder` (482-508) with:
```ts
  /** Toggle the hover highlight class on a node's DOM label. */
  private setLabelHover(node: GraphNode, hover: boolean): void {
    const threeObj = (node as unknown as { __threeObj?: { children?: Array<{ isCSS2DObject?: boolean; element: HTMLElement }> } }).__threeObj
    const label = threeObj?.children?.find(c => c.isCSS2DObject)
    if (label) label.element.classList.toggle('label-hovered', hover)
  }
```
- Update the two calls in `onNodeHover` (342, 345): `this.setNodeHoverBorder(…)` → `this.setLabelHover(…)`.
- Extend `static styles` (64-74) — labels live in this shadow root, so the class rule applies here:
```ts
  static styles = css`
    :host { display: block; width: 100%; height: 100%; position: absolute; top: 0; left: 0; touch-action: none; }
    .mf-graph-label { transition: background 120ms ease; }
    .mf-graph-label.label-hovered { background: rgba(255, 255, 255, 0.18); outline: 1px solid rgba(255, 255, 255, 0.5); }
  `
```

- [ ] **Step 4: Run — verify pass**

```bash
cd web && npx vitest run src/components/mf-force-graph.test.ts -t "label-hovered"
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/mf-force-graph.ts web/src/components/mf-force-graph.test.ts
git commit -m "feat(grading-ui): hover highlight via .label-hovered class on DOM labels"
```

---

## Task 8: Visibility mirroring + static-frame test hooks

**Files:**
- Modify: `web/src/components/mf-force-graph.ts` (`updated` hiddenRarities branch; add `__test_pauseAndRenderFrame`, `__test_labelEls`)
- Modify: `web/src/components/mf-force-graph.test.ts`

- [ ] **Step 1: Write failing tests**

```ts
it('syncs label visibility when hiddenRarities changes (browse)', async () => {
  // Give two fed nodes mock label children, then hide 'rare'.
  const mkNode = (id: string, rarity: string) => ({ id, rarity, relationType: 'synonym',
    __threeObj: { children: [{ isCSS2DObject: true, visible: true, element: document.createElement('div') }] } })
  const nodes = [mkNode('blaze', 'common'), mkNode('conflagration', 'rare')]
  ;(chainable as Record<string, unknown>).graphData = () => ({ nodes, links: [] })
  el.hiddenRarities = new Set(['rare'])
  await el.updateComplete
  const rareLabel = nodes[1].__threeObj.children[0]
  expect(rareLabel.visible).toBe(false)
  expect(rareLabel.element.style.display).toBe('none')
})

it('exposes __test_pauseAndRenderFrame and __test_labelEls', () => {
  expect(typeof el.__test_pauseAndRenderFrame).toBe('function')
  expect(Array.isArray(el.__test_labelEls())).toBe(true)
})
```
Note: the existing `3d-force-graph` Proxy returns `chainable` for `graphData` (a function). To let the test stub `graph.graphData()` returning nodes, the implementer adds a `graphData` branch to the Proxy returning a settable function, OR the test sets it as shown (the Proxy `get` falls through to `() => chainable` for unknown props — so override by defining `graphData` on the chainable target). Implementer: add to the Proxy `get` a `graphData` case that, when called with no args, returns `mockGraphData` (a module-scoped `{nodes,links}` defaulting to `{nodes:[],links:[]}`), and when called with data returns chainable. Reset `mockGraphData` in beforeEach.

- [ ] **Step 2: Run — verify it fails**

```bash
cd web && npx vitest run src/components/mf-force-graph.test.ts -t "visibility"
```
Expected: FAIL.

- [ ] **Step 3: Implement**

In `web/src/components/mf-force-graph.ts`:
- Import `syncLabelVisibility` (merge with the label-layer import).
- In `updated`, extend the `hiddenRarities` branch (528-531):
```ts
    if (changed.has('hiddenRarities') && this.graph) {
      this.graph.nodeVisibility(this.isNodeVisible)
      this.graph.linkVisibility(this.isLinkVisible)
      const data = this.graph.graphData() as unknown as { nodes: Parameters<typeof syncLabelVisibility>[0] }
      syncLabelVisibility(data.nodes, this.isNodeVisible)
    }
```
- Add test hooks (place near `render()`):
```ts
  /** Test hook: freeze the sim and render exactly one label frame against the
   *  current camera, so DOM-label geometry can be measured deterministically. */
  __test_pauseAndRenderFrame(): void {
    if (!this.graph || !this.labelRenderer) return
    this.graph.pauseAnimation()
    this.labelRenderer.render(this.graph.scene() as never, this.graph.camera() as never)
  }

  /** Test hook: the live label `<div>`s in the overlay. */
  __test_labelEls(): HTMLElement[] {
    if (!this.labelRenderer) return []
    return Array.from(this.labelRenderer.domElement.querySelectorAll('.mf-graph-label'))
  }
```

- [ ] **Step 4: Run — verify pass + whole unit suite**

```bash
cd web && npx vitest run src/components/mf-force-graph.test.ts
```
Expected: PASS (any still-failing sprite assertions are removed in Task 9).

- [ ] **Step 5: Commit**

```bash
git add web/src/components/mf-force-graph.ts web/src/components/mf-force-graph.test.ts
git commit -m "feat(grading-ui): label visibility mirror + static-frame test hooks"
```

---

## Task 9: Remove `three-spritetext`; green the whole suite; build

**Files:**
- Modify: `web/src/components/mf-force-graph.test.ts` (drop `SpriteText` import, mock, and any residual sprite assertions)
- Modify: `web/package.json` (remove `three-spritetext`)

- [ ] **Step 1: Remove the sprite mock + import from the test file**

Delete `import SpriteText from 'three-spritetext'` (line 4), the `vi.mock('three-spritetext', …)` block (100-112), the `vi.mocked(SpriteText).mockClear()` in `beforeEach` (150), and any remaining assertions referencing `SpriteText` or sprite properties (`fontFace`, `material`, `padding`, `borderWidth` on sprites). Grep: `grep -n "SpriteText\|isSprite\|\.material\|fontFace" web/src/components/mf-force-graph.test.ts` and remove/convert each.

- [ ] **Step 2: Run — full unit suite**

```bash
cd web && npx vitest run
```
Expected: PASS (all files). Fix any stragglers until green.

- [ ] **Step 3: Remove the dependency + the source import**

```bash
cd web && npm uninstall three-spritetext
```
Confirm no source imports remain: `grep -rn "three-spritetext" web/src` → expected: no matches.

- [ ] **Step 4: Typecheck + production build**

```bash
cd web && npx tsc --noEmit && npm run build
```
Expected: both PASS; bundle emitted to `web/dist`.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/mf-force-graph.test.ts web/package.json web/package-lock.json
git commit -m "chore(grading-ui): remove three-spritetext (sprite path fully replaced)"
```

---

## Task 10: Playwright e2e — geometry, contrast, rotate/pan/zoom

**Files:**
- Create: `web/playwright.config.ts`
- Create: `web/e2e/graph-labels.spec.ts`

- [ ] **Step 1: Playwright config**

`web/playwright.config.ts`:
```ts
import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  use: { baseURL: 'http://localhost:5173' },
  webServer: { command: 'npm run dev', url: 'http://localhost:5173', reuseExistingServer: true, timeout: 60000 },
})
```

- [ ] **Step 2: Add the dependency + install the browser**

```bash
cd web && npm install -D @playwright/test@^1.49.0 && npx playwright install chromium
```
Expected: `@playwright/test` added to devDependencies; chromium downloaded. (If the sandbox blocks the download or registry fetch, note it in the task report — the spec accepts this suite running where a browser is available; do NOT fake a pass.)

- [ ] **Step 3: Write the e2e test** — mount the component directly via a fixture page

`web/e2e/graph-labels.spec.ts` drives a tiny harness page that imports the component, sets a fixed grade graph, and exposes the element. Use Vite's ability to serve a module: create `web/e2e/fixture.html` importing `/src/components/mf-force-graph.ts` and seeding `gradeChains` with 3 chains; then:
```ts
import { test, expect } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.goto('/e2e/fixture.html')
  await page.waitForFunction(() => (window as any).mfReady === true)
  await page.evaluate(() => (document.querySelector('mf-force-graph') as any).__test_pauseAndRenderFrame())
})

test('every visible label sits on its node projected position (independent code paths)', async ({ page }) => {
  const mismatches = await page.evaluate(() => {
    const el: any = document.querySelector('mf-force-graph')
    const graph = el.graph // expose in fixture, or add a __test_graph getter
    const canvasRect = el.renderRoot.querySelector('canvas').getBoundingClientRect()
    const CENTER = { x: 0.5, y: 1.1 }
    const out: any[] = []
    for (const n of graph.graphData().nodes) {
      const lib = graph.graph2ScreenCoords(n.x, n.y, n.z) // library projector
      const label = n.__threeObj.children.find((c: any) => c.isCSS2DObject)
      if (!label || label.element.style.display === 'none') continue
      const r = label.element.getBoundingClientRect()           // browser layout
      const anchorX = r.left + r.width * CENTER.x - canvasRect.left
      const anchorY = r.top + r.height * CENTER.y - canvasRect.top
      if (Math.abs(anchorX - lib.x) > 2 || Math.abs(anchorY - lib.y) > 2) {
        out.push({ id: n.id, anchorX, anchorY, lib })
      }
    }
    return out
  })
  expect(mismatches).toEqual([])
})

test('labels stay glued under rotate, pan, and zoom', async ({ page }) => {
  for (const cam of [
    { pos: { x: 0, y: 0, z: 120 }, look: { x: 0, y: 0, z: 0 } },   // zoom in
    { pos: { x: 0, y: 0, z: 900 }, look: { x: 0, y: 0, z: 0 } },   // zoom out
    { pos: { x: 300, y: 80, z: 300 }, look: { x: 0, y: 0, z: 0 } },// orbit
    { pos: { x: 60, y: 0, z: 400 }, look: { x: 60, y: 0, z: 0 } }, // pan
  ]) {
    const ok = await page.evaluate((c) => {
      const el: any = document.querySelector('mf-force-graph')
      el.graph.cameraPosition(c.pos, c.look, 0)   // synchronous, no tween
      el.__test_pauseAndRenderFrame()
      const canvasRect = el.renderRoot.querySelector('canvas').getBoundingClientRect()
      const CENTER = { x: 0.5, y: 1.1 }
      for (const n of el.graph.graphData().nodes) {
        const label = n.__threeObj.children.find((x: any) => x.isCSS2DObject)
        if (!label || label.element.style.display === 'none') continue
        const lib = el.graph.graph2ScreenCoords(n.x, n.y, n.z)
        const r = label.element.getBoundingClientRect()
        const ax = r.left + r.width * CENTER.x - canvasRect.left
        const ay = r.top + r.height * CENTER.y - canvasRect.top
        if (Math.abs(ax - lib.x) > 2 || Math.abs(ay - lib.y) > 2) return false
      }
      return true
    }, cam)
    expect(ok).toBe(true)
  }
})

test('labels meet the min-px floor and carry contrast styles', async ({ page }) => {
  const report = await page.evaluate(() => {
    const el: any = document.querySelector('mf-force-graph')
    const labels = el.__test_labelEls()
    return labels.map((d: HTMLElement) => {
      const span = d.querySelector('span') as HTMLElement
      const cs = getComputedStyle(d); const css = getComputedStyle(span)
      return { h: d.getBoundingClientRect().height, bg: cs.backgroundColor, shadow: css.textShadow }
    })
  })
  for (const r of report) {
    expect(r.h).toBeGreaterThanOrEqual(10)             // floor
    expect(r.bg).toMatch(/rgba?\([^)]*0?\.\d+\)|rgb\(/) // background present
    expect(r.shadow).not.toBe('none')                  // outline present
  }
})
```
The fixture must expose `el.graph` (add a `get __test_graph()` returning `this.graph` to the component, or set `(el as any).graph` accessible — implementer's choice; prefer a `__test_graph` getter for cleanliness and update the test accordingly). Seed enough nodes spread out (call `zoomToFit` or feed fixed `{x,y,z}` so positions aren't all at origin — see spec pitfall).

- [ ] **Step 4: Run the e2e suite**

```bash
cd web && npx playwright test
```
Expected: 3 tests PASS. If chromium could not be installed in the sandbox, report BLOCKED with the exact error — do not mark green.

- [ ] **Step 5: Commit**

```bash
git add web/playwright.config.ts web/e2e/ web/src/components/mf-force-graph.ts
git commit -m "test(grading-ui): Playwright e2e — label geometry/contrast under rotate/pan/zoom"
```

---

## Task 11: Diagnose the raycaster hit-test offset (findings only — no fix)

**Files:**
- Create: `web/e2e/raycaster-offset.spec.ts`
- Create: `docs/inbox/2026-05-31-raycaster-offset-findings.md`

- [ ] **Step 1: Write a diagnostic harness** (not a pass/fail gate — it measures and records)

`web/e2e/raycaster-offset.spec.ts`: load the browse fixture at a known `devicePixelRatio`, place a node at a known screen position, dispatch a `pointermove` at the node's projected screen coords, and read what the library reports as hovered (instrument via `onNodeHover` capturing the hovered node id into `window`). Sweep the pointer vertically in 2px steps to find the Y at which the hover *actually* registers; the delta between that Y and the node's projected Y is the offset. Repeat at `devicePixelRatio` 1 and 2 (Playwright `deviceScaleFactor`).

```ts
import { test } from '@playwright/test'
import { writeFileSync } from 'node:fs'

for (const dsf of [1, 2]) {
  test.describe(`dpr=${dsf}`, () => {
    test.use({ deviceScaleFactor: dsf, viewport: { width: 1000, height: 800 } })
    test(`measure vertical hover offset`, async ({ page }) => {
      await page.goto('/e2e/fixture-browse.html')
      await page.waitForFunction(() => (window as any).mfReady === true)
      const result = await page.evaluate(() => {
        const el: any = document.querySelector('mf-force-graph')
        el.__test_pauseAndRenderFrame?.()
        const node = el.graph.graphData().nodes[0]
        const p = el.graph.graph2ScreenCoords(node.x, node.y, node.z)
        const canvas = el.renderRoot.querySelector('canvas')
        const rect = canvas.getBoundingClientRect()
        ;(window as any).__hovered = null
        // requires fixture to set onNodeHover -> window.__hovered = node?.id
        const hits: number[] = []
        for (let dy = -40; dy <= 40; dy += 2) {
          canvas.dispatchEvent(new PointerEvent('pointermove', {
            clientX: rect.left + p.x, clientY: rect.top + p.y + dy, bubbles: true,
          }))
          if ((window as any).__hovered === node.id) hits.push(dy)
        }
        return { projected: p, hitsDy: hits, dpr: window.devicePixelRatio }
      })
      writeFileSync(`/tmp/raycaster-dpr${dsf}.json`, JSON.stringify(result, null, 2))
      console.log(`dpr=${dsf}`, JSON.stringify(result))
    })
  })
}
```
(Hover throttling in three-render-objects may need a small wait between moves; add `await page.waitForTimeout(20)` inside the loop via `page.evaluate` async if hits are empty.)

- [ ] **Step 2: Run + capture**

```bash
cd web && npx playwright test e2e/raycaster-offset.spec.ts
cat /tmp/raycaster-dpr1.json /tmp/raycaster-dpr2.json
```

- [ ] **Step 3: Write findings** — does the offset scale with dPR (confirming the hypothesis) or stay constant (refuting it)? Record the measured offset at each dPR, the centre of the hit band vs the projected Y, and conclude. Propose fix options ranked by blast radius: (a) `patch-package` on `three-render-objects` pointer→NDC; (b) a container-level pointer-coord correction in `mf-force-graph`; (c) upstream issue. **Apply no fix** — this is the decision Julian asked to make.

`docs/inbox/2026-05-31-raycaster-offset-findings.md`: measured data table + conclusion + ranked options.

- [ ] **Step 4: Commit**

```bash
git add web/e2e/raycaster-offset.spec.ts docs/inbox/2026-05-31-raycaster-offset-findings.md
git commit -m "test(grading-ui): raycaster hit-test offset diagnostic + findings"
```

---

## Self-Review

**Spec coverage:** extraRenderers architecture (T4) ✓; CSS2DObject children + sphere preserved (T5) ✓; one system both modes (T5 labelStyleFor) ✓; size config constant|distance-floor with per-mode defaults (T2/T5) ✓; visibility mirror / orphan-ghost fix (T3/T8) ✓; pointer-events:none default (T2) ✓; hover as CSS class (T7) ✓; three pinned + three-spritetext removed (T1/T9) ✓; static-frame instrument (T8) ✓; Playwright anti-self-confirmation via graph2ScreenCoords vs getBoundingClientRect (T10) ✓; rotate/pan/zoom via cameraPosition(…,0) (T10) ✓; min-px + contrast assertions (T10) ✓; raycaster diagnose-not-fix (T11) ✓; declutter/virtualise out of scope, seam left (visibility-gated loops) ✓.

**Placeholder scan:** colours that need confirming against `colours.ts` (RARITY_COLOURS.common rgb) are flagged for the implementer to read and match — not a placeholder, an explicit verification step. No TBDs.

**Type consistency:** `LabelSizeConfig`/`LabelStyle`/`labelScale(cfg,dist,refDist)`/`makeLabelObject(style,getCfg,getRefDist)`/`syncLabelVisibility(nodes,isVisible)`/`effectiveLabelSize`/`labelRefDist`/`LABEL_CENTER {x,y}` are consistent across Tasks 2-8. `__test_pauseAndRenderFrame`/`__test_labelEls` consistent T8/T10.
