import type { FrameSummary } from '../lib/frame-timer'

// Shapes shared by the runner, the verdict, the report and the page.

export type RunId = 'none' | 'blur' | 'sprite' | 'sprite-cap2'

export interface RunResult {
  id: RunId
  label: string
  pixelRatio: number
  /** Time between animation frames: the number the pass mark is judged on. */
  interval: FrameSummary
  /** Time spent ticking the layout, per frame. */
  physics: FrameSummary
  /** Time spent projecting and drawing, per frame. */
  draw: FrameSummary
}

export interface ScalingResult {
  nodes: number
  edges: number
  ticks: number
  /** Milliseconds per tick. */
  physics: FrameSummary
}

export interface Results {
  runs: RunResult[]
  scaling: ScalingResult[]
}
