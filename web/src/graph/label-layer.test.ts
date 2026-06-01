import { describe, it, expect, vi } from 'vitest'
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
    // 10/13 ≈ 0.769 floor; 200/400=0.5 is below the floor → clamps up to 0.769.
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
    // happy-dom 17 preserves the hex literal (it does not normalise to rgb()).
    expect(span.style.color).toBe('#6fb8e0')
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

describe('buildLabelEl backlink tooltip', () => {
  it('with no backlinks renders just the head text, no arrow/tooltip', () => {
    const el = buildLabelEl({ text: 'anger', colour: '#fff', role: 'topic' }, CONST)
    expect(el.querySelector('.mf-graph-label__text')!.textContent).toBe('anger')
    expect(el.querySelector('.mf-graph-label__arrow')).toBeNull()
    expect(el.querySelector('.mf-graph-label__tooltip')).toBeNull()
  })
  it('with backlinks renders an interactive arrow and a tooltip row per deduped backlink', () => {
    const el = buildLabelEl({ text: 'heat', colour: '#fff', role: 'step', backlinks: [
      { source: 'pressure', phrase: 'subterranean heat' },
      { source: 'ember', phrase: 'the warmth below' },
      { source: 'pressure', phrase: 'subterranean heat' }, // dup — collapses
    ] }, CONST)
    const arrow = el.querySelector('.mf-graph-label__arrow') as HTMLElement
    expect(arrow).not.toBeNull()
    expect(arrow.style.pointerEvents).toBe('auto')
    const rows = el.querySelectorAll('.mf-graph-label__tooltip .mf-graph-label__backlink')
    expect(rows.length).toBe(2)
    expect(rows[0].textContent).toContain('pressure')
    expect(rows[0].textContent).toContain('subterranean heat')
  })
  it('does not set inline display on the tooltip (the stylesheet :hover rule controls it)', () => {
    const el = buildLabelEl({ text: 'heat', colour: '#fff', role: 'step', backlinks: [
      { source: 'pressure', phrase: 'subterranean heat' },
    ] }, CONST)
    const tooltip = el.querySelector('.mf-graph-label__tooltip') as HTMLElement
    // An inline display:none would out-specify the :hover rule and never reveal.
    expect(tooltip.style.display).toBe('')
  })
  it('keeps space-colliding (source, phrase) pairs as distinct rows', () => {
    // A space-joined dedup key would collapse these two genuinely-distinct
    // connections ("cold fire"+"below" vs "cold"+"fire below" both → "cold fire
    // below"), silently dropping one row. A structured key keeps them apart.
    const el = buildLabelEl({ text: 'X', colour: '#fff', role: 'step', backlinks: [
      { source: 'cold fire', phrase: 'below' },
      { source: 'cold', phrase: 'fire below' },
    ] }, CONST)
    const rows = el.querySelectorAll('.mf-graph-label__tooltip .mf-graph-label__backlink')
    expect(rows.length).toBe(2)
  })
  it('an empty backlinks array renders no arrow/tooltip', () => {
    const el = buildLabelEl({ text: 'anger', colour: '#fff', role: 'topic', backlinks: [] }, CONST)
    expect(el.querySelector('.mf-graph-label__arrow')).toBeNull()
    expect(el.querySelector('.mf-graph-label__tooltip')).toBeNull()
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
