import type { Results } from './results'
import { verdict, describeVerdict, FRAME_BUDGET_MS } from './verdict'

export interface DeviceFacts {
  /** `new Date().toISOString()` at the time of the run. */
  isoDate: string
  pixelRatio: number
  viewport: { width: number; height: number }
  backingStore: { width: number; height: number }
  userAgent: string
}

const ms = (v: number) => `${v.toFixed(2)} ms`
const pct = (share: number) => `${(share * 100).toFixed(1)}%`

/** Plain text for pasting into a chat. Pure: all device facts come in as arguments. */
export function buildReport(results: Results, facts: DeviceFacts): string {
  const none = results.runs.find(r => r.id === 'none')
  const refresh = none && none.interval.median > 0 ? `${Math.round(1000 / none.interval.median)} Hz` : 'unknown'
  const v = verdict(results.runs)
  return [
    `Glow speed test ${facts.isoDate}`,
    `Pixel ratio: ${facts.pixelRatio}`,
    `Viewport (CSS px): ${facts.viewport.width} x ${facts.viewport.height}`,
    `Backing store (px): ${facts.backingStore.width} x ${facts.backingStore.height}`,
    `Estimated refresh rate: ${refresh}`,
    `User agent: ${facts.userAgent}`,
    ...results.runs.map(r =>
      `${r.label}: frame interval median ${ms(r.interval.median)}, p95 ${ms(r.interval.p95)}, ` +
      `over ${FRAME_BUDGET_MS} ms ${pct(r.interval.overBudgetShare)}; ` +
      `physics median ${ms(r.physics.median)}, p95 ${ms(r.physics.p95)}; ` +
      `draw median ${ms(r.draw.median)}, p95 ${ms(r.draw.p95)}`),
    ...results.scaling.map(s =>
      `Physics, ${s.nodes} nodes and ${s.edges} edges: median ${ms(s.physics.median)} per tick, p95 ${ms(s.physics.p95)}`),
    `Verdict: ${describeVerdict(v)}`,
    `Physics share of the frame budget: ${pct(v.physicsShare)}`,
  ].join('\n')
}
