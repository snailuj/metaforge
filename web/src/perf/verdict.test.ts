import { describe, it, expect } from 'vitest'
import { verdict, describeVerdict, FRAME_BUDGET_MS, JITTER_ALLOWANCE_MS, PASS_LIMIT_MS, type Verdict } from './verdict'
import type { RunId, RunResult } from './results'

// Rule: the glow method is the first run, in the order blur, sprite,
// sprite-cap2, whose frame-interval p95 is within the budget plus the
// timer-jitter allowance; if none is, glow waits for the graph to rest.

const summary = (p95: number, median = p95) => ({ count: 600, median, p95, overBudgetShare: 0 })

function run(id: RunId, p95: number, physicsMedian = 1): RunResult {
  return { id, label: id, pixelRatio: 3, interval: summary(p95), physics: summary(physicsMedian), draw: summary(5) }
}

const all = (p: { none?: number; blur: number; sprite: number; cap: number }, physicsMedian = 1): RunResult[] => [
  run('none', p.none ?? 16.7, physicsMedian), run('blur', p.blur), run('sprite', p.sprite), run('sprite-cap2', p.cap),
]

describe('verdict', () => {
  it('exports the budget, allowance and their sum', () => {
    expect(FRAME_BUDGET_MS).toBe(16.7)
    expect(JITTER_ALLOWANCE_MS).toBe(1.0)
    expect(PASS_LIMIT_MS).toBeCloseTo(17.7, 10)
  })

  it('chooses live blur when it passes, even if the others pass too', () => {
    expect(verdict(all({ blur: 16.7, sprite: 16.7, cap: 16.7 })).choice).toBe('blur')
  })

  it('falls to the pre-drawn glow when blur fails', () => {
    expect(verdict(all({ blur: 40, sprite: 17, cap: 17 })).choice).toBe('sprite')
  })

  it('falls to the capped pre-drawn glow when only that passes', () => {
    expect(verdict(all({ blur: 40, sprite: 25, cap: 16.8 })).choice).toBe('sprite-cap2')
  })

  it('says rest-only when none passes', () => {
    expect(verdict(all({ blur: 40, sprite: 25, cap: 18 })).choice).toBe('rest-only')
  })

  it('passes at the limit and fails just above it', () => {
    expect(verdict(all({ blur: PASS_LIMIT_MS, sprite: 99, cap: 99 })).choice).toBe('blur')
    expect(verdict(all({ blur: PASS_LIMIT_MS + 0.01, sprite: 99, cap: 99 })).choice).toBe('rest-only')
  })

  it('does not let the no-glow run pick the method', () => {
    expect(verdict(all({ none: 10, blur: 40, sprite: 40, cap: 40 })).choice).toBe('rest-only')
  })

  it('treats a run that never happened as a fail', () => {
    expect(verdict([run('none', 10), run('blur', 40)]).choice).toBe('rest-only')
    expect(verdict([]).choice).toBe('rest-only')
  })

  it('reports the physics share as the no-glow physics median over the budget', () => {
    const v = verdict(all({ blur: 16, sprite: 16, cap: 16 }, 3.34))
    expect(v.physicsShare).toBeCloseTo(0.2, 3)
  })

  it('reports a zero physics share, not NaN, without a no-glow run', () => {
    expect(verdict([]).physicsShare).toBe(0)
  })

  it('records which runs passed', () => {
    expect(verdict(all({ blur: 40, sprite: 17, cap: 99 })).passes).toEqual({ blur: false, sprite: true, 'sprite-cap2': false })
  })
})

describe('verdict and the Rust physics run', () => {
  // Rule: the Rust run is a comparison, not a glow candidate, so it never
  // changes the verdict or the physics share, whatever its numbers are.
  it('ignores a none-wasm run, however slow or fast', () => {
    const base = all({ blur: 40, sprite: 20, cap: 16 }, 2)
    const without = verdict(base)
    for (const p95 of [1, 500]) {
      const withRust = verdict([...base, run('none-wasm', p95, 0.1)])
      expect(withRust).toEqual(without)
    }
    expect(without.choice).toBe('sprite-cap2')
  })
})

describe('describeVerdict', () => {
  const sentences = {
    blur: 'Live blur passes, so glow can use the canvas blur setting.',
    sprite: 'Live blur is too slow and pre-drawn glow passes, so glow is stamped from a cached image.',
    'sprite-cap2': 'Pre-drawn glow is too slow at full sharpness and passes with sharpness capped at 2.',
    'rest-only': 'No glow method passes, so glow is drawn only when the graph rests and a WebGL glow layer moves to now.',
  } as const

  it.each(Object.entries(sentences))('gives one plain sentence for %s', (choice, text) => {
    const v = { choice, passes: { blur: false, sprite: false, 'sprite-cap2': false }, physicsShare: 0 } as Verdict
    expect(describeVerdict(v)).toBe(text)
  })
})
