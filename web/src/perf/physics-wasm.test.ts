import { describe, it, expect, beforeAll } from 'vitest'
import { readFileSync } from 'node:fs'
import { buildScene } from './scene'
import { createPhysics } from './physics'
import { createWasmPhysics, wrapWasmInstance, type PhysicsExports } from './physics-wasm'

// These tests need the compiled engine. They are not skipped when it is
// missing: a missing file fails every test with the command that builds it.

const WASM_PATH = 'src/perf/wasm/physics.wasm'
let wasmBytes: Uint8Array

beforeAll(() => {
  try {
    wasmBytes = readFileSync(WASM_PATH)
  } catch (err) {
    throw new Error(`${WASM_PATH} is missing, so the Rust physics tests cannot run. Build it with: npm run build:wasm`, { cause: err })
  }
})

const bits = (a: Float32Array) => Array.from(new Uint32Array(a.buffer, a.byteOffset, a.length))

describe('createWasmPhysics', () => {
  // Rule: the engine starts from exactly the scene's positions.
  it('starts from the scene positions', async () => {
    const scene = buildScene(3, 20, 30)
    const out = new Float32Array(60)
    ;(await createWasmPhysics(scene, wasmBytes)).writePositions(out)
    expect(Array.from(out)).toEqual(Array.from(scene.positions))
  })

  // Rule: ticking the layout moves words and never produces a non-number.
  it('moves at least one word in 10 ticks and writes no NaN', async () => {
    const scene = buildScene(1, 100, 150)
    const physics = await createWasmPhysics(scene, wasmBytes)
    const before = new Float32Array(300)
    const after = new Float32Array(300)
    physics.writePositions(before)
    for (let i = 0; i < 10; i++) physics.tick()
    physics.writePositions(after)
    expect(bits(after)).not.toEqual(bits(before))
    expect(Array.from(after).every(Number.isFinite)).toBe(true)
  })

  // Rule: ticking in a batch does exactly the work of ticking one by one.
  it('tickMany(n) leaves the layout where n single ticks leave it', async () => {
    const scene = buildScene(2, 40, 60)
    const batched = await createWasmPhysics(scene, wasmBytes)
    const single = await createWasmPhysics(scene, wasmBytes)
    batched.tickMany(12)
    for (let i = 0; i < 12; i++) single.tick()
    expect(bits(batched.positionsView())).toEqual(bits(single.positionsView()))
  })

  // Rule: the engine holds alpha, so it keeps doing full work however long it runs.
  it('keeps jostling after a long run', async () => {
    const physics = await createWasmPhysics(buildScene(1, 50, 75), wasmBytes)
    physics.tickMany(400)
    const a = Float32Array.from(physics.positionsView())
    physics.tick()
    expect(bits(physics.positionsView())).not.toEqual(bits(a))
  })

  // Rule: building the engine leaves the scene it was built from untouched.
  it('does not touch the scene it was built from', async () => {
    const scene = buildScene(1, 30, 40)
    const copy = Array.from(scene.positions)
    const edges = Array.from(scene.edges)
    ;(await createWasmPhysics(scene, wasmBytes)).tickMany(5)
    expect(Array.from(scene.positions)).toEqual(copy)
    expect(Array.from(scene.edges)).toEqual(edges)
  })

  // Rule: a failed init is reported, never swallowed into a dead engine.
  it('throws when the engine cannot be built', async () => {
    await expect(createWasmPhysics(buildScene(1, 0, 0), wasmBytes)).rejects.toThrow(/init failed/)
  })
})

describe('positionsView', () => {
  // Rule: the view is the engine's own memory, not a copy.
  it('shows the engine positions without copying', async () => {
    const physics = await createWasmPhysics(buildScene(1, 10, 12), wasmBytes)
    const view = physics.positionsView()
    const before = Float32Array.from(view)
    physics.tick()
    expect(bits(view)).not.toEqual(bits(before))
    const out = new Float32Array(30)
    physics.writePositions(out)
    expect(bits(out)).toEqual(bits(view))
  })

  // Rule: growing memory detaches old views, so the next call must make a fresh one.
  it('is made again when the memory buffer changes identity', async () => {
    const { instance } = await WebAssembly.instantiate(wasmBytes, {})
    const exports = instance.exports as unknown as PhysicsExports
    const physics = wrapWasmInstance(exports, buildScene(1, 10, 12))
    const first = physics.positionsView()
    expect(physics.positionsView() === first).toBe(true) // same buffer, same view
    const snapshot = Array.from(first)
    exports.memory.grow(1)
    expect(first.byteLength).toBe(0) // the old view is detached
    const second = physics.positionsView()
    expect(second === first).toBe(false) // compared by identity: a detached view cannot be printed
    expect(second.buffer).toBe(exports.memory.buffer)
    expect(Array.from(second)).toEqual(snapshot)
  })
})

describe('against d3-force-3d', () => {
  const rms = (a: Float32Array) => {
    let cx = 0, cy = 0, cz = 0
    const n = a.length / 3
    for (let i = 0; i < n; i++) { cx += a[3 * i]; cy += a[3 * i + 1]; cz += a[3 * i + 2] }
    cx /= n; cy /= n; cz /= n
    let sum = 0
    for (let i = 0; i < n; i++) sum += (a[3 * i] - cx) ** 2 + (a[3 * i + 1] - cy) ** 2 + (a[3 * i + 2] - cz) ** 2
    return Math.sqrt(sum / n)
  }

  // Rule: both engines lay the same scene out at a similar overall size. Exact
  // equality is not expected (d3 uses float64 and its own jiggle), but a wrong
  // decay, strength or distance changes the spread by far more than 25 per cent.
  it('lays a 100-node scene out at a similar size after 50 ticks at alpha 0.3', async () => {
    const scene = buildScene(1, 100, 150)
    const js = createPhysics(scene)
    const rust = await createWasmPhysics(scene, wasmBytes)
    for (let i = 0; i < 50; i++) { js.tick(); rust.tick() }
    const a = new Float32Array(300)
    const b = new Float32Array(300)
    js.writePositions(a)
    rust.writePositions(b)
    const [sa, sb] = [rms(a), rms(b)]
    expect(Math.abs(sa - sb) / Math.max(sa, sb), `d3 ${sa.toFixed(1)} against Rust ${sb.toFixed(1)}`).toBeLessThan(0.25)
  })
})
