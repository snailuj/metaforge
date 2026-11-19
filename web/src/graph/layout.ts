// The graph's layout physics: the Rust engine in web/physics-wasm behind the same
// settings the app gives d3-force-3d today. Plain TypeScript; nothing here knows
// about Lit, the renderer or the camera. The renderer reads `positions()` and
// calls `tick()` each frame until it returns false.
//
// Not wired into mf-force-graph.ts yet.

import type { GraphLink, GraphNode } from './types'
import { resolveEndpoint } from './transform'
import { SEED_SPREAD, seedParents, settledToHold, shouldRelease } from './growth'
import { mulberry32 } from '@/lib/random'

/** The forest rings, as mf-force-graph.ts sets them. A test fails if the two drift apart. */
export const FOREST_RING = { spacing: 52, offset: 22, strength: 0.08, flatten: 0.6 }
export const FOREST_LINK_DISTANCE = FOREST_RING.spacing
const THESAURUS_LINK_DISTANCE = 30
/** What 3d-force-graph holds alpha at while a word is dragged. */
const DRAG_ALPHA = 0.3
const INITIAL_CAPACITY = { nodes: 64, links: 128 }

export interface RingOptions {
  spacing: number
  offset: number
  strength: number
  flatten: number
}

export interface LayoutOptions {
  /** Forest depth of a word, or undefined for a thesaurus word. Read on every setGraph. */
  depthOf?: (node: GraphNode) => number | undefined
  /** Constants of the depth force. Without them the force is off. */
  ring?: RingOptions
  linkDistance?: number
  metaphorDistance?: number
  velocityDecay?: number
  alphaDecay?: number
  /** d3's default 0.001: the layout rests once alpha falls below it. */
  alphaMin?: number
  /** The layout rests this long after it last woke, whatever alpha says. */
  cooldownMs?: number
  /** Ticks run inside setGraph, before the first frame of new data. */
  warmupTicks?: number
  /** Hold settled words still while newcomers settle. */
  holdOnArrival?: boolean
  holdQuietMs?: number
  holdMaxQuietMs?: number
  initialCapacity?: { nodes: number; links: number }
  now?: () => number
  /** Seeds the offset of a newcomer from its parent. */
  random?: () => number
  log?: (message: string, data?: Record<string, unknown>) => void
}

export interface Layout {
  /**
   * Give the layout the graph as it is now. Words it already has keep their
   * position and velocity; new words start at their parent; words that are gone
   * are dropped. The same graph again changes nothing and does not reheat; any
   * other change reheats alpha to 1 and runs the warm-up. Throws, changing
   * nothing, on a duplicate id or a link to a word that is not in the graph.
   */
  setGraph(nodes: readonly GraphNode[], links: readonly GraphLink[]): void
  /**
   * One step. True while the layout is running. The call that returns false has
   * taken the last step (draw once more after it); later calls return false and
   * move nothing, until setGraph changes the graph or a word is pinned.
   */
  tick(): boolean
  /** x, y, z per word, straight onto wasm memory. Do not keep it across setGraph or pin. */
  positions(): Float32Array
  /** Index of the word in `positions()`, or -1. */
  indexOf(id: string): number
  idAt(index: number): string
  /** Fix a word at a position (a drag) and wake the layout. False when there is no such word. */
  pin(id: string, x: number, y: number, z: number): boolean
  unpin(id: string): void
  /** Free the words held for an arrival, now. */
  releaseHeld(why?: string): void
  holdOnArrival: boolean
  readonly size: number
  readonly alpha: number
  readonly heldCount: number
  readonly capacity: { nodes: number; links: number }
}

/** What the module exports; see web/physics-wasm/src/lib.rs. */
interface Exports {
  memory: WebAssembly.Memory
  init(nodes: number, links: number): number
  set_counts(nodes: number, links: number): number
  positions_ptr(): number
  velocities_ptr(): number
  fixed_ptr(): number
  fixed_pos_ptr(): number
  depth_ptr(): number
  links_ptr(): number
  link_dist_ptr(): number
  refresh_links(): void
  place_unplaced(): void
  set_params(velocityDecay: number, alphaDecay: number, alphaTarget: number, alphaMin: number): void
  set_alpha(alpha: number): void
  get_alpha(): number
  set_ring(on: number, spacing: number, offset: number, strength: number, flatten: number): void
  step(): number
  step_many(count: number): number
}

const REQUIRED: ReadonlyArray<keyof Exports> = [
  'memory', 'init', 'set_counts', 'positions_ptr', 'velocities_ptr', 'fixed_ptr', 'fixed_pos_ptr', 'depth_ptr',
  'links_ptr', 'link_dist_ptr', 'refresh_links', 'place_unplaced', 'set_params', 'set_alpha', 'get_alpha',
  'set_ring', 'step', 'step_many',
]

const bitsOf = (a: Float32Array | Uint32Array) => new Uint32Array(a.buffer, a.byteOffset, a.length)
/** Same numbers, NaN included (a word with no depth). */
const sameBits = (a: Float32Array | Uint32Array, b: Float32Array | Uint32Array) => {
  if (a.length !== b.length) return false
  const [x, y] = [bitsOf(a), bitsOf(b)]
  for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return false
  return true
}

const hasPosition = (n: GraphNode) => Number.isFinite(n.x) && Number.isFinite(n.y) && Number.isFinite(n.z)

export async function createLayout(wasmBytes: BufferSource, options: LayoutOptions = {}): Promise<Layout> {
  const cfg = {
    linkDistance: options.linkDistance ?? THESAURUS_LINK_DISTANCE,
    metaphorDistance: options.metaphorDistance ?? FOREST_LINK_DISTANCE,
    velocityDecay: options.velocityDecay ?? 0.85,
    alphaDecay: options.alphaDecay ?? 0.005,
    alphaMin: options.alphaMin ?? 0.001,
    cooldownMs: options.cooldownMs ?? 30_000,
    warmupTicks: options.warmupTicks ?? 50,
    holdQuietMs: options.holdQuietMs ?? 1000,
    holdMaxQuietMs: options.holdMaxQuietMs ?? 6000,
  }
  const now = options.now ?? (() => performance.now())
  const random = options.random ?? mulberry32(0x5eed)
  const log = options.log ?? ((message, data) => console.debug('[layout]', message, data ?? ''))
  const depthOf = options.depthOf

  let ex: Exports
  try {
    const { instance } = await WebAssembly.instantiate(wasmBytes, {})
    ex = instance.exports as unknown as Exports
  } catch (err) {
    throw new Error('layout: could not start the physics wasm; rebuild it with npm run build:wasm', { cause: err })
  }
  const missing = REQUIRED.filter(name => typeof ex[name] !== (name === 'memory' ? 'object' : 'function'))
  if (missing.length > 0) {
    throw new Error(`layout: the physics wasm lacks ${missing.join(', ')}; rebuild it with npm run build:wasm`)
  }

  let capN = 0
  let capM = 0
  let p = { pos: 0, vel: 0, fixed: 0, fixedPos: 0, depth: 0, links: 0, dist: 0 }
  let alphaTarget = 0
  let broken = false

  const f32 = (ptr: number, len: number) => new Float32Array(ex.memory.buffer, ptr, len)
  const u8 = (ptr: number, len: number) => new Uint8Array(ex.memory.buffer, ptr, len)
  const u32 = (ptr: number, len: number) => new Uint32Array(ex.memory.buffer, ptr, len)

  const applyParams = () => ex.set_params(cfg.velocityDecay, cfg.alphaDecay, alphaTarget, cfg.alphaMin)

  /** Makes a fresh engine with room for these counts. Everything in it is lost. */
  function allocate(nodes: number, links: number): void {
    if (ex.init(nodes, links) !== 1) {
      broken = true
      throw new Error(`layout: the physics wasm could not allocate room for ${nodes} words and ${links} links`)
    }
    capN = nodes
    capM = links
    p = {
      pos: ex.positions_ptr(), vel: ex.velocities_ptr(), fixed: ex.fixed_ptr(), fixedPos: ex.fixed_pos_ptr(),
      depth: ex.depth_ptr(), links: ex.links_ptr(), dist: ex.link_dist_ptr(),
    }
    applyParams()
    const ring = options.ring
    ex.set_ring(ring ? 1 : 0, ring?.spacing ?? 0, ring?.offset ?? 0, ring?.strength ?? 0, ring?.flatten ?? 0)
    ex.set_counts(0, 0)
  }
  allocate(Math.max(1, options.initialCapacity?.nodes ?? INITIAL_CAPACITY.nodes), Math.max(1, options.initialCapacity?.links ?? INITIAL_CAPACITY.links))

  // What the engine holds, in the engine's order.
  let ids: string[] = []
  let index = new Map<string, number>()
  let n = 0
  let sentLinks = new Uint32Array(0)
  let sentDist = new Float32Array(0)
  let sentDepth = new Float32Array(0)

  let running = false
  let startedAt = 0
  let lastArrivalAt = 0
  const held = new Set<string>()
  const pinned = new Set<string>()
  /** Where the latest newcomers sit, with a reused record of each one's velocity. */
  let newcomerIdx = new Int32Array(0)
  let probes: Array<{ vx: number; vy: number; vz: number }> = []

  function wake(): void {
    running = true
    startedAt = now()
  }

  function setAlphaTarget(target: number): void {
    alphaTarget = target
    applyParams()
  }

  function releaseHeld(why = 'asked'): void {
    if (held.size === 0) return
    log('releasing held words', { why, held: held.size })
    const fixed = u8(p.fixed, n)
    for (const id of held) {
      // A word under the pointer is left to its drag, which frees it at unpin.
      if (pinned.has(id)) continue
      const i = index.get(id)
      if (i !== undefined) fixed[i] = 0
    }
    held.clear()
    newcomerIdx = new Int32Array(0)
  }

  function stop(why: string): void {
    running = false
    releaseHeld(`stopped: ${why}`)
  }

  function releaseWhenQuiet(): void {
    const v = f32(p.vel, 3 * n)
    for (let k = 0; k < newcomerIdx.length; k++) {
      const i = newcomerIdx[k]
      const probe = probes[k]
      probe.vx = v[3 * i]
      probe.vy = v[3 * i + 1]
      probe.vz = v[3 * i + 2]
    }
    if (shouldRelease({ now: now(), lastArrivalAt, newcomers: probes, quietMs: cfg.holdQuietMs, maxQuietMs: cfg.holdMaxQuietMs })) {
      releaseHeld('arrivals settled')
    }
  }

  let view: Float32Array | null = null

  const api: Layout = {
    holdOnArrival: options.holdOnArrival ?? false,

    setGraph(nodes, links) {
      if (broken) throw new Error('layout: unusable after a failed allocation')

      // Check everything before changing anything.
      const nextById = new Map<string, GraphNode>()
      for (const node of nodes) {
        if (nextById.has(node.id)) throw new Error(`layout: two words share the id "${node.id}"`)
        nextById.set(node.id, node)
      }
      const ends = links.map(l => {
        const source = resolveEndpoint(l.source)
        const target = resolveEndpoint(l.target)
        for (const id of [source, target]) {
          if (!nextById.has(id)) throw new Error(`layout: the link ${source} to ${target} names "${id}", which is not in the graph`)
        }
        return [source, target] as const
      })

      // Survivors keep their order and newcomers follow, so a removal compacts.
      const order = ids.filter(id => nextById.has(id))
      const survivors = order.length
      const newIds: string[] = []
      for (const node of nodes) {
        if (!index.has(node.id)) {
          order.push(node.id)
          newIds.push(node.id)
        }
      }
      const newIndex = new Map(order.map((id, i) => [id, i]))
      const nextN = order.length
      const nextM = links.length
      const nodeList = order.map(id => nextById.get(id)!)

      const lk = new Uint32Array(2 * nextM)
      const ld = new Float32Array(nextM)
      links.forEach((l, k) => {
        lk[2 * k] = newIndex.get(ends[k][0])!
        lk[2 * k + 1] = newIndex.get(ends[k][1])!
        ld[k] = l.metaphor ? cfg.metaphorDistance : cfg.linkDistance
      })
      const dp = new Float32Array(nextN)
      nodeList.forEach((node, i) => { dp[i] = depthOf?.(node) ?? NaN })

      if (newIds.length === 0 && survivors === n && sameBits(lk, sentLinks) && sameBits(ld, sentDist) && sameBits(dp, sentDepth)) return

      // Carry survivors across, compacted, with newcomers still to place.
      const pos = new Float32Array(3 * nextN).fill(NaN)
      const vel = new Float32Array(3 * nextN)
      const fixed = new Uint8Array(nextN)
      const fixedPos = new Float32Array(3 * nextN)
      {
        const [oPos, oVel, oFixed, oFixedPos] = [f32(p.pos, 3 * n), f32(p.vel, 3 * n), u8(p.fixed, n), f32(p.fixedPos, 3 * n)]
        for (let i = 0; i < survivors; i++) {
          const o = index.get(order[i])!
          pos.set(oPos.subarray(3 * o, 3 * o + 3), 3 * i)
          vel.set(oVel.subarray(3 * o, 3 * o + 3), 3 * i)
          fixed[i] = oFixed[o]
          fixedPos.set(oFixedPos.subarray(3 * o, 3 * o + 3), 3 * i)
        }
      }
      const newSet = new Set(newIds)
      for (const id of newIds) {
        const node = nextById.get(id)!
        if (hasPosition(node)) pos.set([node.x!, node.y!, node.z!], 3 * newIndex.get(id)!)
      }

      // Each newcomer starts beside its parent, as growth.ts does.
      const newcomers = newIds.map(id => nextById.get(id)!)
      for (const { child, parent } of seedParents(newcomers, links, nodeList, node => !newSet.has(node.id) || hasPosition(node))) {
        const [c, q] = [newIndex.get(child.id)!, newIndex.get(parent.id)!]
        for (let k = 0; k < 3; k++) pos[3 * c + k] = pos[3 * q + k] + (random() - 0.5) * SEED_SPREAD
      }

      for (const set of [held, pinned]) for (const id of set) if (!nextById.has(id)) set.delete(id)
      if (api.holdOnArrival) {
        for (const node of settledToHold(nodeList.slice(0, survivors), newSet, node => fixed[newIndex.get(node.id)!] === 0)) {
          const i = newIndex.get(node.id)!
          fixed[i] = 1
          fixedPos.set(pos.subarray(3 * i, 3 * i + 3), 3 * i)
          held.add(node.id)
        }
      }

      if (nextN > capN || nextM > capM) {
        let nodesCap = capN
        let linksCap = capM
        while (nodesCap < nextN) nodesCap *= 2
        while (linksCap < nextM) linksCap *= 2
        const alpha = ex.get_alpha()
        allocate(nodesCap, linksCap)
        ex.set_alpha(alpha)
        log('grew capacity', { nodes: nodesCap, links: linksCap })
      }
      if (ex.set_counts(nextN, nextM) !== 1) throw new Error('layout: the physics wasm refused counts it has room for')
      f32(p.pos, 3 * nextN).set(pos)
      f32(p.vel, 3 * nextN).set(vel)
      u8(p.fixed, nextN).set(fixed)
      f32(p.fixedPos, 3 * nextN).set(fixedPos)
      f32(p.depth, nextN).set(dp)
      u32(p.links, 2 * nextM).set(lk)
      f32(p.dist, nextM).set(ld)
      ex.refresh_links()
      ex.place_unplaced()

      const removed = n - survivors
      ids = order
      index = newIndex
      n = nextN
      sentLinks = lk
      sentDist = ld
      sentDepth = dp
      newcomerIdx = Int32Array.from(newIds, id => newIndex.get(id)!)
      probes = newIds.map(() => ({ vx: 0, vy: 0, vz: 0 }))

      // A change reheats, as every graphData() does today.
      ex.set_alpha(1)
      wake()
      lastArrivalAt = now()
      log('arrival', { newcomers: newIds.length, removed, held: held.size, words: n, links: nextM })
      if (cfg.warmupTicks > 0) ex.step_many(cfg.warmupTicks)
    },

    tick() {
      if (!running) return false
      if (now() - startedAt > cfg.cooldownMs) {
        stop('cooldown')
        return false
      }
      const more = ex.step() === 1
      if (held.size > 0) releaseWhenQuiet()
      if (!more) {
        stop('alpha below its minimum')
        return false
      }
      return true
    },

    positions() {
      if (view === null || view.buffer !== ex.memory.buffer || view.byteOffset !== p.pos || view.length !== 3 * n) {
        view = new Float32Array(ex.memory.buffer, p.pos, 3 * n)
      }
      return view
    },

    indexOf: id => index.get(id) ?? -1,

    idAt(i) {
      const id = ids[i]
      if (id === undefined) throw new Error(`layout: no word at index ${i}`)
      return id
    },

    pin(id, x, y, z) {
      const i = index.get(id)
      if (i === undefined) {
        log('pin: no such word', { id })
        return false
      }
      pinned.add(id)
      u8(p.fixed, n)[i] = 1
      f32(p.fixedPos, 3 * n).set([x, y, z], 3 * i)
      f32(p.pos, 3 * n).set([x, y, z], 3 * i) // the word follows the pointer before the next tick
      setAlphaTarget(DRAG_ALPHA)
      wake()
      return true
    },

    unpin(id) {
      if (!pinned.delete(id)) return
      const i = index.get(id)
      if (i !== undefined) {
        const fixed = u8(p.fixed, n)
        if (held.has(id)) {
          // Still held for an arrival: it stays where it was dropped until the release.
          f32(p.fixedPos, 3 * n).set(f32(p.pos, 3 * n).subarray(3 * i, 3 * i + 3), 3 * i)
        } else {
          fixed[i] = 0
        }
      }
      if (pinned.size === 0) setAlphaTarget(0)
      wake()
    },

    releaseHeld,

    get size() { return n },
    get alpha() { return ex.get_alpha() },
    get heldCount() { return held.size },
    get capacity() { return { nodes: capN, links: capM } },
  }
  return api
}
