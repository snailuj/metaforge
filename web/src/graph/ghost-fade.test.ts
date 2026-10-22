import { describe, it, expect } from 'vitest'
import { ghostFade, ghostAlphas, GHOST_FADE_STEP } from './ghost-fade'

describe('ghostFade', () => {
  const ref = 200 // the default view's camera distance

  it('is 0 at or beyond the default view distance', () => {
    expect(ghostFade(ref, ref)).toBe(0)
    expect(ghostFade(ref * 3, ref)).toBe(0)
  })

  it('is 1 once the camera is close', () => {
    expect(ghostFade(ref * 0.3, ref)).toBe(1)
    expect(ghostFade(1, ref)).toBe(1)
  })

  it('rises steadily as the camera closes in', () => {
    const levels = [1, 0.85, 0.7, 0.55, 0.4].map(f => ghostFade(ref * f, ref))
    for (let i = 1; i < levels.length; i++) expect(levels[i]).toBeGreaterThan(levels[i - 1])
  })

  it('moves in fixed steps, so the renderer only re-colours when a ghost crosses one', () => {
    for (const f of [0.31, 0.42, 0.5, 0.63, 0.77, 0.9]) {
      const level = ghostFade(ref * f, ref)
      expect(Math.abs(level / GHOST_FADE_STEP - Math.round(level / GHOST_FADE_STEP))).toBeLessThan(1e-9)
    }
  })

  it('treats an unknown reference distance as the far end', () => {
    expect(ghostFade(50, 0)).toBe(0)
  })
})

describe('ghostAlphas', () => {
  it('keeps node and label as faint as the ghost edge when far', () => {
    const far = ghostAlphas(0)
    expect(far.node).toBeLessThanOrEqual(0.06)
    expect(far.label).toBeLessThanOrEqual(0.06)
    expect(far.edge).toBeLessThanOrEqual(far.node)
  })

  it('brings all three up together, the edge no brighter than a full edge', () => {
    const near = ghostAlphas(1)
    expect(near.node).toBeGreaterThanOrEqual(0.6)
    expect(near.label).toBeGreaterThanOrEqual(0.6)
    expect(near.edge).toBeLessThanOrEqual(0.15)
    const mid = ghostAlphas(0.5)
    expect(mid.node).toBeGreaterThan(ghostAlphas(0).node)
    expect(mid.node).toBeLessThan(near.node)
  })
})
