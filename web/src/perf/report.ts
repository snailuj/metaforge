import type { Results, ScalingResult } from './results'
import { verdict, describeVerdict, PASS_LIMIT_MS } from './verdict'

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

/** How many times faster Rust is than JavaScript, from the medians; null if Rust's median is zero. */
export function speedUp(s: ScalingResult): number | null {
  return s.rustPhysics.median > 0 ? s.physics.median / s.rustPhysics.median : null
}

export const formatSpeedUp = (s: ScalingResult): string => {
  const x = speedUp(s)
  return x === null ? 'n/a' : `${x.toFixed(1)}x`
}

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
      `over ${PASS_LIMIT_MS} ms ${pct(r.interval.overBudgetShare)}; ` +
      `physics median ${ms(r.physics.median)}, p95 ${ms(r.physics.p95)}; ` +
      `draw median ${ms(r.draw.median)}, p95 ${ms(r.draw.p95)}`),
    ...results.scaling.map(s =>
      `Physics, ${s.nodes} nodes and ${s.edges} edges: ` +
      `JS median ${ms(s.physics.median)} per tick, p95 ${ms(s.physics.p95)}; ` +
      `Rust median ${ms(s.rustPhysics.median)} per tick, p95 ${ms(s.rustPhysics.p95)}`),
    `Verdict: ${describeVerdict(v)}`,
    `Physics share of the frame budget: ${pct(v.physicsShare)}`,
    ...(results.scaling.length > 0
      ? [`Rust physics speed-up at ${results.scaling.map(s => s.nodes).join(' / ')} nodes: ${results.scaling.map(formatSpeedUp).join(' / ')}`]
      : []),
  ].join('\n')
}
