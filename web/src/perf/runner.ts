import { createFrameTimer, summarise, type FrameTimer } from '../lib/frame-timer'
import { buildScene } from './scene'
import { project, PROJECTED_STRIDE, type View } from './project'
import { drawScene, type DrawOptions, type GlowMode } from './draw'
import { createPhysics } from './physics'
import { FRAME_BUDGET_MS, PASS_LIMIT_MS } from './verdict'
import type { Results, RunId, RunResult, ScalingResult } from './results'

// Runs the glow speed test. Nothing here touches the DOM: the page hands in
// a clock, a frame scheduler and a way to size the canvas, so every rule can
// be tested with a fake clock.

export interface ClockDeps {
  now(): number
  /** Like requestAnimationFrame: the callback gets the frame's timestamp. */
  requestFrame(cb: (timestamp: number) => void): void
}

export interface Timing {
  warmupMs: number
  measureMs: number
  scalingTicks: number
}

export const FULL_TIMING: Timing = { warmupMs: 1000, measureMs: 10_000, scalingTicks: 300 }
export const QUICK_TIMING: Timing = { warmupMs: 100, measureMs: 500, scalingTicks: 30 }

const SCENE_SEED = 1
const SCENE_NODES = 100
const SCENE_EDGES = 150
const TURN_RADIANS_PER_SECOND = 0.3
const SCALING_SIZES = [100, 300, 1000]
/** Ticks run between yields in the scaling pass, so the countdown keeps moving. */
const SCALING_BATCH = 25
const SHARPNESS_CAP = 2

interface PlanStep {
  id: RunId
  label: string
  glow: GlowMode
  capSharpness: boolean
}

export const RUN_PLAN: readonly PlanStep[] = [
  { id: 'none', label: 'No glow', glow: 'none', capSharpness: false },
  { id: 'blur', label: 'Live blur', glow: 'blur', capSharpness: false },
  { id: 'sprite', label: 'Pre-drawn glow', glow: 'sprite', capSharpness: false },
  { id: 'sprite-cap2', label: 'Pre-drawn glow, sharpness capped at 2', glow: 'sprite', capSharpness: true },
]

export interface FrameWork {
  physicsMs: number
  drawMs: number
}

export interface MeasuredRun {
  frames: number
  interval: FrameTimer
  physics: FrameTimer
  draw: FrameTimer
  interrupted: boolean
}

export interface MeasureOptions {
  warmupMs: number
  measureMs: number
  signal?: AbortSignal
  onProgress?(phase: 'warm-up' | 'measuring', remainingMs: number): void
}

/**
 * Calls `frame` on every animation frame for the warm-up and then the
 * measured period. Frames inside the warm-up do the work but are not recorded.
 */
export function measureRun(deps: ClockDeps, frame: (timestamp: number) => FrameWork, opts: MeasureOptions): Promise<MeasuredRun> {
  // One slot per millisecond is more than any display can deliver frames.
  const capacity = Math.ceil(opts.measureMs) + 16
  const run: MeasuredRun = {
    frames: 0,
    interval: createFrameTimer(capacity),
    physics: createFrameTimer(capacity),
    draw: createFrameTimer(capacity),
    interrupted: false,
  }
  return new Promise(resolve => {
    let start = NaN
    let previous = NaN
    const step = (t: number): void => {
      if (opts.signal?.aborted) {
        run.interrupted = true
        resolve(run)
        return
      }
      if (Number.isNaN(start)) start = t
      const elapsed = t - start
      if (elapsed >= opts.warmupMs + opts.measureMs) {
        resolve(run)
        return
      }
      const work = frame(t)
      const measuring = elapsed >= opts.warmupMs
      if (measuring) {
        run.frames++
        run.physics.record(work.physicsMs)
        run.draw.record(work.drawMs)
        if (!Number.isNaN(previous)) run.interval.record(t - previous)
      }
      previous = t
      opts.onProgress?.(
        measuring ? 'measuring' : 'warm-up',
        measuring ? opts.warmupMs + opts.measureMs - elapsed : opts.warmupMs - elapsed,
      )
      deps.requestFrame(step)
    }
    deps.requestFrame(step)
  })
}

const nextFrame = (deps: ClockDeps) => new Promise<void>(resolve => deps.requestFrame(() => resolve()))

/** Physics alone, no drawing, at three graph sizes. */
export async function runScaling(
  deps: ClockDeps, ticks: number, signal?: AbortSignal, onProgress?: (nodes: number) => void,
): Promise<ScalingResult[]> {
  const out: ScalingResult[] = []
  for (const nodes of SCALING_SIZES) {
    if (signal?.aborted) break
    onProgress?.(nodes)
    const edges = Math.round(nodes * 1.5)
    const physics = createPhysics(buildScene(SCENE_SEED, nodes, edges))
    const timer = createFrameTimer(ticks)
    for (let i = 0; i < ticks; i++) {
      const before = deps.now()
      physics.tick()
      timer.record(deps.now() - before)
      if ((i + 1) % SCALING_BATCH === 0) await nextFrame(deps)
    }
    out.push({ nodes, edges, ticks, physics: summarise(timer.samples(), FRAME_BUDGET_MS) })
  }
  return out
}

export interface Surface {
  ctx: CanvasRenderingContext2D
  /** CSS pixels. */
  width: number
  height: number
  pixelRatio: number
}

export interface RunStatus {
  runId: RunId | 'scaling'
  label: string
  phase: 'warm-up' | 'measuring' | 'scaling'
  remainingMs: number
  /** 1-based position among the four drawing runs; the scaling pass counts as a fifth step. */
  step: number
  steps: number
}

export interface RunnerEnv {
  deps: ClockDeps
  devicePixelRatio: number
  /** Sizes the canvas backing store to CSS size times `pixelRatio` and returns its context. */
  prepareSurface(pixelRatio: number): Surface
  makeCanvas?: DrawOptions['makeCanvas']
  signal?: AbortSignal
  onStatus?(status: RunStatus): void
}

export interface RunOutcome {
  results: Results
  interrupted: boolean
}

async function runDrawing(env: RunnerEnv, step: PlanStep, timing: Timing, index: number): Promise<RunResult | null> {
  const pixelRatio = step.capSharpness ? Math.min(env.devicePixelRatio, SHARPNESS_CAP) : env.devicePixelRatio
  const surface = env.prepareSurface(pixelRatio)
  const scene = buildScene(SCENE_SEED, SCENE_NODES, SCENE_EDGES)
  const physics = createPhysics(scene)
  const positions = new Float32Array(scene.nodeCount * 3)
  const projected = new Float32Array(scene.nodeCount * PROJECTED_STRIDE)
  const view: View = {
    cx: surface.width / 2,
    cy: surface.height / 2,
    distance: 320,
    focal: Math.min(surface.width, surface.height) * 0.9,
  }
  const opts: DrawOptions = {
    glow: step.glow, pixelRatio, width: surface.width, height: surface.height, makeCanvas: env.makeCanvas,
    referenceScale: view.focal / view.distance,
  }
  const { now } = env.deps

  const measured = await measureRun(env.deps, t => {
    const p0 = now()
    physics.tick()
    physics.writePositions(positions)
    const p1 = now()
    project(positions, scene.nodeCount, (t / 1000) * TURN_RADIANS_PER_SECOND, view, projected)
    drawScene(surface.ctx, scene, projected, opts)
    const p2 = now()
    return { physicsMs: p1 - p0, drawMs: p2 - p1 }
  }, {
    warmupMs: timing.warmupMs,
    measureMs: timing.measureMs,
    signal: env.signal,
    onProgress: (phase, remainingMs) => env.onStatus?.({
      runId: step.id, label: step.label, phase, remainingMs, step: index + 1, steps: RUN_PLAN.length + 1,
    }),
  })
  if (measured.interrupted) return null
  return {
    id: step.id,
    label: step.label,
    pixelRatio,
    interval: summarise(measured.interval.samples(), PASS_LIMIT_MS),
    physics: summarise(measured.physics.samples(), FRAME_BUDGET_MS),
    draw: summarise(measured.draw.samples(), FRAME_BUDGET_MS),
  }
}

/** The four drawing runs in plan order, then the physics scaling pass. */
export async function runAll(env: RunnerEnv, timing: Timing): Promise<RunOutcome> {
  const runs: RunResult[] = []
  for (const [i, step] of RUN_PLAN.entries()) {
    const result = await runDrawing(env, step, timing, i)
    if (!result) return { results: { runs, scaling: [] }, interrupted: true }
    runs.push(result)
  }
  const scaling = await runScaling(env.deps, timing.scalingTicks, env.signal, nodes =>
    env.onStatus?.({
      runId: 'scaling', label: `Physics alone, ${nodes} nodes`, phase: 'scaling', remainingMs: 0,
      step: RUN_PLAN.length + 1, steps: RUN_PLAN.length + 1,
    }))
  return { results: { runs, scaling }, interrupted: env.signal?.aborted ?? false }
}
