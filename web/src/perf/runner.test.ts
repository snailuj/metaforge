import { describe, it, expect } from 'vitest'
import { stubCtx } from './stub-ctx'
import { measureRun, runAll, runScaling, type ClockDeps, type RunnerEnv } from './runner'

// Rule: only frames after the warm-up count, and a full run reports its four
// drawing runs in the fixed order, then the three physics scaling sizes.

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
  it('times each tick and reports the three sizes in order', async () => {
    const out = await runScaling(fakeClock(), 6)
    expect(out.map(r => r.nodes)).toEqual([100, 300, 1000])
    expect(out.map(r => r.edges)).toEqual([150, 450, 1500])
    expect(out.every(r => r.ticks === 6 && r.physics.count === 6)).toBe(true)
    expect(out.every(r => r.physics.median > 0)).toBe(true)
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
  })
  const timing = { warmupMs: 20, measureMs: 64, scalingTicks: 5 }

  it('returns the four runs in the fixed order, then scaling', async () => {
    const ratios: number[] = []
    const out = await runAll(makeEnv(ratios), timing)
    expect(out.interrupted).toBe(false)
    expect(out.results.runs.map(r => [r.id, r.label])).toEqual([
      ['none', 'No glow'],
      ['blur', 'Live blur'],
      ['sprite', 'Pre-drawn glow'],
      ['sprite-cap2', 'Pre-drawn glow, sharpness capped at 2'],
    ])
    expect(out.results.scaling.map(s => s.nodes)).toEqual([100, 300, 1000])
  })

  it('caps the last run at a pixel ratio of 2 and leaves the others at the device ratio', async () => {
    const ratios: number[] = []
    const out = await runAll(makeEnv(ratios), timing)
    expect(ratios).toEqual([3, 3, 3, 2])
    expect(out.results.runs.map(r => r.pixelRatio)).toEqual([3, 3, 3, 2])
  })

  it('does not raise the ratio of a device already below the cap', async () => {
    const ratios: number[] = []
    const env = { ...makeEnv(ratios), devicePixelRatio: 1.5 }
    await runAll(env, timing)
    expect(ratios).toEqual([1.5, 1.5, 1.5, 1.5])
  })

  it('reports status for every run and the scaling pass', async () => {
    const seen = new Set<string>()
    const env = { ...makeEnv([]), onStatus: (s: { runId: string }) => seen.add(s.runId) }
    await runAll(env, timing)
    expect([...seen]).toEqual(['none', 'blur', 'sprite', 'sprite-cap2', 'scaling'])
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
