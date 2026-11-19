import type { RunId, RunResult } from './results'

// Pass mark for the glow speed test: 60 frames a second, with a small
// allowance because the frame timer itself jitters by about a millisecond.

export const FRAME_BUDGET_MS = 16.7
export const JITTER_ALLOWANCE_MS = 1.0
export const PASS_LIMIT_MS = FRAME_BUDGET_MS + JITTER_ALLOWANCE_MS

/** Candidates in the order they are tried. */
const ORDER = ['blur', 'sprite', 'sprite-cap2'] as const satisfies readonly RunId[]
type Candidate = (typeof ORDER)[number]

export interface Verdict {
  choice: Candidate | 'rest-only'
  passes: Record<Candidate, boolean>
  /** Median physics time of the no-glow run as a fraction of the frame budget. */
  physicsShare: number
}

export function verdict(runs: readonly RunResult[]): Verdict {
  const byId = new Map(runs.map(r => [r.id, r]))
  const passes = { blur: false, sprite: false, 'sprite-cap2': false } as Record<Candidate, boolean>
  for (const id of ORDER) {
    const r = byId.get(id)
    passes[id] = r !== undefined && r.interval.count > 0 && r.interval.p95 <= PASS_LIMIT_MS
  }
  const choice = ORDER.find(id => passes[id]) ?? 'rest-only'
  const none = byId.get('none')
  return { choice, passes, physicsShare: none ? none.physics.median / FRAME_BUDGET_MS : 0 }
}

export function describeVerdict(v: Verdict): string {
  switch (v.choice) {
    case 'blur':
      return 'Live blur passes, so glow can use the canvas blur setting.'
    case 'sprite':
      return 'Live blur is too slow and pre-drawn glow passes, so glow is stamped from a cached image.'
    case 'sprite-cap2':
      return 'Pre-drawn glow is too slow at full sharpness and passes with sharpness capped at 2.'
    case 'rest-only':
      return 'No glow method passes, so glow is drawn only when the graph rests and a WebGL glow layer moves to now.'
  }
}
