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

describe('defaults', () => {
  it('browse is distance-floor 13/10, grade is constant 13/11', () => {
    expect(DEFAULT_LABEL_SIZE.browse).toEqual({ mode: 'distance-floor', basePx: 13, minPx: 10 })
    expect(DEFAULT_LABEL_SIZE.grade).toEqual({ mode: 'constant', basePx: 13, minPx: 11 })
  })
  it('label anchor floats just above the node', () => {
    expect(LABEL_CENTER).toEqual({ x: 0.5, y: 1.1 })
  })
})
