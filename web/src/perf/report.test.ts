import { describe, it, expect } from 'vitest'
import { buildReport, type DeviceFacts } from './report'
import type { Results } from './results'

// Rule: the pasted report states every measured number to two decimals,
// in a fixed order, so two reports can be compared line by line.

const s = (median: number, p95: number, over = 0) => ({ count: 600, median, p95, overBudgetShare: over })

const results: Results = {
  runs: [
    { id: 'none', label: 'No glow', pixelRatio: 3, interval: s(8.333, 8.9, 0), physics: s(0.5, 0.8), draw: s(2.25, 3.1) },
    { id: 'blur', label: 'Live blur', pixelRatio: 3, interval: s(16.7, 41.6, 0.4125), physics: s(0.51, 0.82), draw: s(14.2, 30.456) },
    { id: 'sprite', label: 'Pre-drawn glow', pixelRatio: 3, interval: s(8.4, 17.7, 0.01), physics: s(0.5, 0.79), draw: s(4.5, 6.05) },
    { id: 'sprite-cap2', label: 'Pre-drawn glow, sharpness capped at 2', pixelRatio: 2, interval: s(8.3, 9, 0), physics: s(0.5, 0.8), draw: s(3, 4) },
  ],
  scaling: [
    { nodes: 100, edges: 150, ticks: 300, physics: s(0.5, 0.75) },
    { nodes: 300, edges: 450, ticks: 300, physics: s(2.1, 3.04) },
    { nodes: 1000, edges: 1500, ticks: 300, physics: s(11.005, 14) },
  ],
}

const facts: DeviceFacts = {
  isoDate: '2026-11-19T10:20:30.000Z',
  pixelRatio: 3,
  viewport: { width: 412, height: 915 },
  backingStore: { width: 1236, height: 2745 },
  userAgent: 'Mozilla/5.0 (Linux; Android 14; SM-S908B) Chrome/130.0.0.0 Mobile Safari/537.36',
}

const EXPECTED = [
  'Glow speed test 2026-11-19T10:20:30.000Z',
  'Pixel ratio: 3',
  'Viewport (CSS px): 412 x 915',
  'Backing store (px): 1236 x 2745',
  'Estimated refresh rate: 120 Hz',
  'User agent: Mozilla/5.0 (Linux; Android 14; SM-S908B) Chrome/130.0.0.0 Mobile Safari/537.36',
  'No glow: frame interval median 8.33 ms, p95 8.90 ms, over 16.7 ms 0.0%; physics median 0.50 ms, p95 0.80 ms; draw median 2.25 ms, p95 3.10 ms',
  'Live blur: frame interval median 16.70 ms, p95 41.60 ms, over 16.7 ms 41.3%; physics median 0.51 ms, p95 0.82 ms; draw median 14.20 ms, p95 30.46 ms',
  'Pre-drawn glow: frame interval median 8.40 ms, p95 17.70 ms, over 16.7 ms 1.0%; physics median 0.50 ms, p95 0.79 ms; draw median 4.50 ms, p95 6.05 ms',
  'Pre-drawn glow, sharpness capped at 2: frame interval median 8.30 ms, p95 9.00 ms, over 16.7 ms 0.0%; physics median 0.50 ms, p95 0.80 ms; draw median 3.00 ms, p95 4.00 ms',
  'Physics, 100 nodes and 150 edges: median 0.50 ms per tick, p95 0.75 ms',
  'Physics, 300 nodes and 450 edges: median 2.10 ms per tick, p95 3.04 ms',
  'Physics, 1000 nodes and 1500 edges: median 11.01 ms per tick, p95 14.00 ms',
  'Verdict: Live blur is too slow and pre-drawn glow passes, so glow is stamped from a cached image.',
  'Physics share of the frame budget: 3.0%',
].join('\n')

describe('buildReport', () => {
  it('prints the fixed input as the exact expected text', () => {
    expect(buildReport(results, facts)).toBe(EXPECTED)
  })

  it('says unknown, not Infinity, when the no-glow run has no frames', () => {
    const empty: Results = { ...results, runs: [{ ...results.runs[0], interval: s(0, 0) }, ...results.runs.slice(1)] }
    expect(buildReport(empty, facts)).toContain('Estimated refresh rate: unknown')
  })
})
