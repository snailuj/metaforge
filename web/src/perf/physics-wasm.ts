import { HELD_ALPHA, type Physics } from './physics'
import type { Scene } from './scene'

// The Rust engine in web/physics-wasm, wrapped to look like createPhysics so
// the runner treats both engines alike.

/** What the module exports; see web/physics-wasm/src/lib.rs. */
export interface PhysicsExports {
  memory: WebAssembly.Memory
  init(nodeCount: number, linkCount: number): number
  positions_ptr(): number
  links_ptr(): number
  prepare(): void
  tick(alpha: number): void
  tick_many(alpha: number, count: number): void
}

export interface WasmPhysics extends Physics {
  /**
   * A view straight onto the engine's positions in wasm memory: no copy.
   * Growing the memory detaches old views, so this makes a new one whenever
   * `memory.buffer` is a different object. Do not hold the result across calls
   * into the engine that could grow memory.
   */
  positionsView(): Float32Array
}

export function wrapWasmInstance(ex: PhysicsExports, scene: Scene): WasmPhysics {
  const nodeCount = scene.nodeCount
  const linkCount = scene.edges.length / 2
  if (ex.init(nodeCount, linkCount) !== 1) {
    throw new Error(`physics wasm init failed for ${nodeCount} nodes and ${linkCount} links`)
  }
  // Pointers are read after init: init is the only call that allocates, and the
  // buffers never move afterwards.
  const positionsPtr = ex.positions_ptr()
  new Float32Array(ex.memory.buffer, positionsPtr, nodeCount * 3).set(scene.positions)
  new Uint32Array(ex.memory.buffer, ex.links_ptr(), linkCount * 2).set(scene.edges)
  ex.prepare()

  let view: Float32Array | null = null
  const positionsView = (): Float32Array => {
    if (view === null || view.buffer !== ex.memory.buffer) {
      view = new Float32Array(ex.memory.buffer, positionsPtr, nodeCount * 3)
    }
    return view
  }

  return {
    tick() {
      ex.tick(HELD_ALPHA)
    },
    tickMany(count) {
      ex.tick_many(HELD_ALPHA, count)
    },
    writePositions(out) {
      out.set(positionsView())
    },
    positionsView,
  }
}

/** Instantiates its own copy of the module, so each scene has its own engine state. */
export async function createWasmPhysics(scene: Scene, wasmBytes: BufferSource): Promise<WasmPhysics> {
  const { instance } = await WebAssembly.instantiate(wasmBytes, {})
  return wrapWasmInstance(instance.exports as unknown as PhysicsExports, scene)
}
