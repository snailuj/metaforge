import { describe, it, expect } from 'vitest'
import { stubCtx } from './stub-ctx'
import { measureRun, runAll, runScaling, type ClockDeps, type RunnerEnv } from './runner'
import { createPhysics, type Physics } from './physics'
import type { Scene } from './scene'

// Rule: only frames after the warm-up count, and a full run reports its five
// drawing runs in the fixed order, then the three physics scaling sizes with
// both engines.

/** Stands in for the Rust engine: the runner only needs the shape. */
const standIn = async (scene: Scene): Promise<Physics> => createPhysics(scene)

/** Frames arrive 16 ms apart, one per microtask; `now` advances 1 ms per call. */
function fakeClock(): ClockDeps & { calls: () => number } {
  let t = 0
  let clock = 0
  return {
    now: () => ++clock,
    requestFrame(cb) {
      t += 16
      const ts = t
      queueMicrotask(() => cb(ts))
    },
    calls: () => clock,
  }
}

describe('measureRun', () => {
  it('drops warm-up frames from every series', async () => {
    const deps = fakeClock()
    let frame = 0
    const res = await measureRun(deps, () => {
      frame++
      const warm = frame <= 4 // frames at t = 16..64 are inside a 100 ms warm-up
      return { physicsMs: warm ? 999 : 1, drawMs: warm ? 999 : 2 }
    }, { warmupMs: 100, measureMs: 160 })
    expect(res.frames).toBeGreaterThan(0)
    expect(res.physics.samples().every(v => v === 1)).toBe(true)
    expect(res.draw.samples().every(v => v === 2)).toBe(true)
    expect(res.physics.samples().length).toBe(res.frames)
  })

  it('gives no more interval samples than frames, and 16 ms each here', async () => {
    const res = await measureRun(fakeClock(), () => ({ physicsMs: 0, drawMs: 0 }), { warmupMs: 0, measureMs: 160 })
    const intervals = res.interval.samples()
    expect(intervals.length).toBeLessThanOrEqual(res.frames)
    expect(intervals.length).toBe(res.frames - 1) // the very first frame has no predecessor
    expect(intervals.every(v => v === 16)).toBe(true)
  })

  it('keeps the interval across the warm-up boundary for the first measured frame', async () => {
    const res = await measureRun(fakeClock(), () => ({ physicsMs: 0, drawMs: 0 }), { warmupMs: 48, measureMs: 160 })
    expect(res.interval.samples().length).toBe(res.frames)
  })

  it('stops early and says so when the signal aborts', async () => {
    const ctl = new AbortController()
    let n = 0
    const res = await measureRun(fakeClock(), () => {
      if (++n === 3) ctl.abort()
      return { physicsMs: 0, drawMs: 0 }
    }, { warmupMs: 0, measureMs: 10_000, signal: ctl.signal })
    expect(res.interrupted).toBe(true)
    expect(res.frames).toBeLessThan(10)
  })

  it('reports remaining time to the progress callback', async () => {
    const seen: Array<[string, number]> = []
    await measureRun(fakeClock(), () => ({ physicsMs: 0, drawMs: 0 }), {
      warmupMs: 32, measureMs: 64,
      onProgress: (phase, remainingMs) => seen.push([phase, remainingMs]),
    })
    expect(seen[0][0]).toBe('warm-up')
    expect(seen.some(([p]) => p === 'measuring')).toBe(true)
    expect(seen.every(([, r]) => r >= 0)).toBe(true)
  })
})

describe('runScaling', () => {
  it('reports the three sizes in order, with both engines timed', async () => {
    const out = await runScaling(fakeClock(), standIn, 30)
    expect(out.map(r => r.nodes)).toEqual([100, 300, 1000])
    expect(out.map(r => r.edges)).toEqual([150, 450, 1500])
    expect(out.every(r => r.ticks === 30 && r.physics.count === 3 && r.rustPhysics.count === 3)).toBe(true)
    expect(out.every(r => r.physics.median > 0 && r.rustPhysics.median > 0)).toBe(true)
  })

  // Rule: a sample is the time of a batch divided by its tick count, for both
  // engines alike, because performance.now() can be coarsened to 0.1 ms and a
  // single fast tick would round to zero. The fake clock charges 1 ms per batch.
  it('divides each batch time by the ticks in it, the short last batch by its own count', async () => {
    const out = await runScaling(fakeClock(), standIn, 25)
    for (const r of out) {
      for (const summary of [r.physics, r.rustPhysics]) {
        expect(summary.count).toBe(3) // batches of 10, 10 and 5
        expect(summary.median).toBeCloseTo(0.1, 10)
        expect(summary.p95).toBeCloseTo(0.2, 10)
      }
    }
  })

  it('runs the Rust engine through tickMany, one scene per size', async () => {
    const sizes: number[] = []
    const batches: number[] = []
    const spy = async (scene: Scene): Promise<Physics> => {
      sizes.push(scene.nodeCount)
      const inner = createPhysics(scene)
      return { ...inner, tickMany: n => { batches.push(n); inner.tickMany(n) } }
    }
    await runScaling(fakeClock(), spy, 20)
    expect(sizes).toEqual([100, 300, 1000])
    expect(batches.length).toBeGreaterThan(0)
    expect(batches.every(n => n <= 10)).toBe(true)
  })

  it('stops between sizes when the signal aborts', async () => {
    const ctl = new AbortController()
    const out = await runScaling(fakeClock(), standIn, 10, ctl.signal, nodes => { if (nodes === 300) ctl.abort() })
    expect(out.map(r => r.nodes)).toEqual([100])
  })
})

describe('runAll', () => {
  const makeEnv = (ratios: number[]): RunnerEnv => ({
    deps: fakeClock(),
    devicePixelRatio: 3,
    prepareSurface: pixelRatio => {
      ratios.push(pixelRatio)
      return { ctx: stubCtx().ctx, width: 400, height: 600, pixelRatio }
    },
    makeCanvas: () => ({ canvas: {} as unknown as CanvasImageSource, ctx: stubCtx().ctx }),
    makeRustPhysics: standIn,
  })
  const timing = { warmupMs: 20, measureMs: 64, scalingTicks: 5 }

  it('returns the five runs in the fixed order, then scaling', async () => {
    const ratios: number[] = []
    const out = await runAll(makeEnv(ratios), timing)
    expect(out.interrupted).toBe(false)
    expect(out.results.runs.map(r => [r.id, r.label])).toEqual([
      ['none', 'No glow'],
      ['blur', 'Live blur'],
      ['sprite', 'Pre-drawn glow'],
      ['sprite-cap2', 'Pre-drawn glow, sharpness capped at 2'],
      ['none-wasm', 'No glow, Rust physics'],
    ])
    expect(out.results.scaling.map(s => s.nodes)).toEqual([100, 300, 1000])
  })

  it('caps the last run at a pixel ratio of 2 and leaves the others at the device ratio', async () => {
    const ratios: number[] = []
    const out = await runAll(makeEnv(ratios), timing)
    expect(ratios).toEqual([3, 3, 3, 2, 3])
    expect(out.results.runs.map(r => r.pixelRatio)).toEqual([3, 3, 3, 2, 3])
  })

  it('does not raise the ratio of a device already below the cap', async () => {
    const ratios: number[] = []
    const env = { ...makeEnv(ratios), devicePixelRatio: 1.5 }
    await runAll(env, timing)
    expect(ratios).toEqual([1.5, 1.5, 1.5, 1.5, 1.5])
  })

  it('reports status for every run and the scaling pass', async () => {
    const seen = new Set<string>()
    const env = { ...makeEnv([]), onStatus: (s: { runId: string }) => seen.add(s.runId) }
    await runAll(env, timing)
    expect([...seen]).toEqual(['none', 'blur', 'sprite', 'sprite-cap2', 'none-wasm', 'scaling'])
  })

  // Rule: the fifth run differs from the first only in its physics engine, so
  // only it builds a Rust engine for the 100-node drawing scene.
  it('builds the Rust engine for the fifth run and for the three scaling sizes only', async () => {
    const sizes: number[] = []
    const env = { ...makeEnv([]), makeRustPhysics: async (scene: Scene) => { sizes.push(scene.nodeCount); return createPhysics(scene) } }
    await runAll(env, timing)
    expect(sizes).toEqual([100, 100, 300, 1000])
  })

  it('returns only the finished runs and skips scaling when interrupted', async () => {
    const ctl = new AbortController()
    const env = makeEnv([])
    let started = 0
    const base = env.prepareSurface
    env.prepareSurface = r => {
      if (++started === 2) ctl.abort()
      return base(r)
    }
    env.signal = ctl.signal
    const out = await runAll(env, timing)
    expect(out.interrupted).toBe(true)
    expect(out.results.runs.map(r => r.id)).toEqual(['none'])
    expect(out.results.scaling).toEqual([])
  })
})
