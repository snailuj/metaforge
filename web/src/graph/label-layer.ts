// Label primitives for the force graph's CSS2D label layer.
// Lit-agnostic and mode-agnostic: callers pass a LabelStyle + LabelSizeConfig,
// so one code path serves both grade and browse palettes.

import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js'

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
