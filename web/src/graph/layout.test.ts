import { describe, it, expect, beforeAll } from 'vitest'
import { readFileSync } from 'node:fs'
import { forceSimulation, forceLink, forceManyBody, forceCenter, type SimulationNode } from 'd3-force-3d'
import patience from '@/fixtures/forest-patience.json'
import type { ForestResponse } from '@/types/api'
import type { GraphData, GraphLink, GraphNode } from './types'
import { composeForest, forestDepthForce, forestToGraph, FOREST_LINK_DISTANCE, FOREST_RING } from './forest'
import { SEED_SPREAD } from './growth'
import { createLayout, type Layout, type LayoutOptions } from './layout'

// These tests need the compiled engine. They are not skipped when it is
// missing: a missing file fails every test with the command that builds it.

const WASM_PATH = 'src/perf/wasm/physics.wasm'
let wasmBytes: Uint8Array

beforeAll(() => {
  try {
    wasmBytes = readFileSync(WASM_PATH)
  } catch (err) {
    throw new Error(`${WASM_PATH} is missing, so the layout tests cannot run. Build it with: npm run build:wasm`, { cause: err })
  }
})

const node = (id: string, order = 1, extra: Partial<GraphNode> = {}): GraphNode =>
  ({ id, word: id, relationType: 'synonym', val: 1, order, ...extra })
const link = (source: string, target: string, extra: Partial<GraphLink> = {}): GraphLink =>
  ({ source, target, relationType: 'synonym', order: 1, ...extra })

/** A centre with `n` words around it, as the browse graph starts out. */
function star(n: number): GraphData {
  const nodes = [node('c', 0), ...Array.from({ length: n }, (_, i) => node(`n${i}`))]
  return { nodes, links: nodes.slice(1).map(m => link('c', m.id)) }
}

/** The same data in fresh objects, as a re-composed graph arrives. */
const copyOf = (g: GraphData): GraphData => ({ nodes: g.nodes.map(n => ({ ...n })), links: g.links.map(l => ({ ...l })) })

let clock = 0
const quiet = () => undefined
function make(options: LayoutOptions = {}): Promise<Layout> {
  clock = 0
  return createLayout(wasmBytes, { now: () => clock, log: quiet, ...options })
}

/** Ticks until the layout rests; fails if it never does. */
function settle(layout: Layout, limit = 4000): number {
  let ticks = 0
  while (layout.tick()) if (++ticks > limit) throw new Error(`still running after ${limit} ticks`)
  return ticks
}

const bits = (a: ArrayLike<number>) => Array.from(new Uint32Array(Float32Array.from(a).buffer))

/** Every word's position bits, by id. */
function byId(layout: Layout): Map<string, number[]> {
  const out = new Map<string, number[]>()
  const p = layout.positions()
  for (let i = 0; i < layout.size; i++) out.set(layout.idAt(i), bits(p.subarray(3 * i, 3 * i + 3)))
  return out
}

function at(layout: Layout, id: string): [number, number, number] {
  const i = layout.indexOf(id)
  if (i < 0) throw new Error(`no word ${id}`)
  const p = layout.positions()
  return [p[3 * i], p[3 * i + 1], p[3 * i + 2]]
}

const gap = (a: ArrayLike<number>, b: ArrayLike<number>) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])

describe('createLayout', () => {
  // Rule: a module that will not run is reported, never replaced by a quiet fallback.
  it('rejects with a clear error when the wasm will not start', async () => {
    await expect(createLayout(new Uint8Array([0, 1, 2, 3]), {})).rejects.toThrow(/could not start the physics wasm/)
  })

  // Rule: a module that is not this engine is reported too.
  it('rejects when the module lacks the engine', async () => {
    const empty = new Uint8Array([0, 0x61, 0x73, 0x6d, 1, 0, 0, 0]) // a valid, empty module
    await expect(createLayout(empty, {})).rejects.toThrow(/physics wasm/)
  })
})

describe('Layout-Stays-The-Same', () => {
  // Rule: a word that had settled keeps its position when the same data is given again.
  it('keeps every position, and rests, when the same data arrives again', async () => {
    const layout = await make()
    const g = star(14)
    layout.setGraph(g.nodes, g.links)
    settle(layout)
    const before = byId(layout)
    expect(before.size).toBe(15) // the baseline is real: every word is there
    const again = copyOf(g)
    layout.setGraph(again.nodes, again.links)
    expect(byId(layout)).toEqual(before)
    expect(layout.tick()).toBe(false) // no reheat either
    expect(byId(layout)).toEqual(before)
  })

  // Rule: handing over the same data twice before anything ticks changes nothing, alpha included.
  it('does not reheat for identical data', async () => {
    const layout = await make()
    const g = star(5)
    layout.setGraph(g.nodes, g.links)
    for (let i = 0; i < 10; i++) layout.tick()
    const alpha = layout.alpha
    expect(alpha).toBeLessThan(1) // it had cooled, so a reheat would show
    layout.setGraph(copyOf(g).nodes, copyOf(g).links)
    expect(layout.alpha).toBe(alpha)
  })

  // Rule: a changed graph does reheat, so it never stays asleep while words arrive.
  it('wakes a rested layout when a word is added', async () => {
    const layout = await make()
    const g = star(6)
    layout.setGraph(g.nodes, g.links)
    settle(layout)
    expect(layout.tick()).toBe(false)
    layout.setGraph([...g.nodes, node('extra')], [...g.links, link('n1', 'extra')])
    expect(layout.alpha).toBeGreaterThan(0.7)
    expect(layout.tick()).toBe(true)
  })
})

describe('Growth-Stays-Steady', () => {
  /** A settled star of 12 gets eight glimpsed words under n2, as growth.test.ts does. Returns how far the most-moved settled word went. */
  async function arrive(holdOnArrival: boolean) {
    const layout = await make({ holdOnArrival })
    const g = star(12)
    layout.setGraph(g.nodes, g.links)
    settle(layout)
    const ids = g.nodes.map(n => n.id)
    const before = ids.map(id => at(layout, id))
    const fresh = Array.from({ length: 8 }, (_, i) => node(`m${i}`, 2))
    layout.setGraph([...g.nodes, ...fresh], [...g.links, ...fresh.map(f => link('n2', f.id))])
    const moved = Math.max(...ids.map((id, i) => gap(at(layout, id), before[i])))
    return { moved, layout, fresh }
  }

  // Rule: a word that had settled moves less than growth.test.ts's limit (0.5 units)
  // through an arrival's warm-up while newcomers settle.
  it('keeps settled words within 0.5 units through an arrival', async () => {
    const baseline = await arrive(false)
    // The baseline is real: without the hold an arrival does move settled words.
    expect(baseline.moved).toBeGreaterThan(5)
    const held = await arrive(true)
    expect(held.moved).toBeLessThan(0.5)
    expect(held.layout.heldCount).toBe(13)
  })

  // Rule: held words stay put for as long as arrivals are recent, then go free.
  it('holds through the quiet period and releases after it', async () => {
    const { layout, fresh } = await arrive(true)
    const centre = at(layout, 'c')
    for (let i = 0; i < 100; i++) layout.tick()
    expect(layout.heldCount).toBe(13)
    expect(gap(at(layout, 'c'), centre)).toBeLessThan(0.5)
    clock += 1000 // quiet long enough, but the newcomers are still moving fast
    layout.tick()
    expect(layout.heldCount).toBe(13)
    expect(fresh.length).toBe(8)
    clock += 6000 // the cap: released whatever the newcomers do
    layout.tick()
    expect(layout.heldCount).toBe(0)
  })

  // Rule: held words go free when the layout comes to rest, as they do on engine stop.
  it('releases when the layout rests', async () => {
    const { layout } = await arrive(true)
    expect(layout.heldCount).toBe(13) // the baseline is real: there is something to release
    clock += 500 // not yet quiet
    settle(layout)
    expect(layout.heldCount).toBe(0)
  })

  // Rule: a word the pointer holds is never freed by the release: the drag frees it.
  it('leaves a pinned word to its drag when the hold is released', async () => {
    const { layout } = await arrive(true)
    expect(layout.heldCount).toBe(13)
    layout.pin('n3', 50, 50, 50)
    clock += 7000
    layout.tick()
    expect(layout.heldCount).toBe(0)
    for (let i = 0; i < 20; i++) layout.tick()
    expect(gap(at(layout, 'n3'), [50, 50, 50])).toBeLessThan(1e-4)
    layout.unpin('n3')
    const there = at(layout, 'n3')
    for (let i = 0; i < 40; i++) layout.tick()
    expect(gap(at(layout, 'n3'), there)).toBeGreaterThan(1) // free again, so the forces move it
  })
})

describe('New words start at their parent', () => {
  // Rule: each newcomer's first position is within the seed offset of its parent,
  // and a chain of newcomers seeds outward from its placed end.
  it('seeds newcomers beside their parents, chains included', async () => {
    const layout = await make({ warmupTicks: 0 })
    const g = star(6)
    layout.setGraph(g.nodes, g.links)
    for (let i = 0; i < 30; i++) layout.tick()
    const kid = node('kid', 2)
    const other = node('other', 2)
    const grandkid = node('grandkid', 3)
    layout.setGraph(
      [...g.nodes, grandkid, kid, other],
      [...g.links, link('n1', 'kid'), link('kid', 'grandkid'), link('n4', 'other')],
    )
    const half = SEED_SPREAD / 2
    for (const [child, parent] of [['kid', 'n1'], ['other', 'n4'], ['grandkid', 'kid']] as const) {
      const [c, p] = [at(layout, child), at(layout, parent)]
      for (let k = 0; k < 3; k++) expect(Math.abs(c[k] - p[k]), `${child} on axis ${k}`).toBeLessThanOrEqual(half + 1e-4)
    }
    // The baseline is real: the offset is not zero, so a word is not simply copied from its parent.
    expect(gap(at(layout, 'kid'), at(layout, 'n1'))).toBeGreaterThan(0)
  })

  // Rule: a newcomer that arrives with a position keeps it, as a seeded forest word does today.
  it('keeps the position a newcomer brings', async () => {
    const layout = await make({ warmupTicks: 0 })
    const g = star(3)
    layout.setGraph(g.nodes, g.links)
    layout.setGraph([...g.nodes, node('placed', 2, { x: 300, y: -200, z: 100 })], [...g.links, link('n0', 'placed')])
    expect(at(layout, 'placed')).toEqual([300, -200, 100])
  })

  // Rule: a first graph with no positions gets d3's starting spiral, and every word is finite.
  it('places a first graph at finite, distinct positions', async () => {
    const layout = await make({ warmupTicks: 0 })
    const g = star(9)
    layout.setGraph(g.nodes, g.links)
    expect(Array.from(layout.positions()).every(Number.isFinite)).toBe(true)
    expect(new Set(Array.from(byId(layout).values()).map(b => b.join())).size).toBe(10)
  })
})

describe('Removing a word keeps every other word where it was', () => {
  // Rule: after removals, each remaining word's id still maps to its own position.
  it('keeps the id-to-position mapping correct', async () => {
    const layout = await make({ warmupTicks: 0 })
    const g = star(10)
    layout.setGraph(g.nodes, g.links)
    for (let i = 0; i < 40; i++) layout.tick()
    const before = byId(layout)
    const gone = new Set(['c', 'n3', 'n9']) // the first, a middle and the last word
    const nodes = g.nodes.filter(n => !gone.has(n.id))
    layout.setGraph(nodes, g.links.filter(l => !gone.has(l.source as string) && !gone.has(l.target as string)))
    expect(layout.size).toBe(8)
    const after = byId(layout)
    for (const id of gone) {
      expect(layout.indexOf(id)).toBe(-1)
      expect(after.has(id)).toBe(false)
    }
    for (const n of nodes) {
      expect(after.get(n.id), n.id).toEqual(before.get(n.id))
      expect(layout.idAt(layout.indexOf(n.id))).toBe(n.id)
    }
  })

  // Rule: a removed word that was held or pinned leaves no stale hold behind.
  it('drops a removed word from the hold', async () => {
    const layout = await make({ holdOnArrival: true })
    const g = star(5)
    layout.setGraph(g.nodes, g.links)
    layout.setGraph([...g.nodes, node('m', 2)], [...g.links, link('n0', 'm')])
    expect(layout.heldCount).toBe(6)
    layout.setGraph(g.nodes.filter(n => n.id !== 'n2'), g.links.filter(l => l.target !== 'n2'))
    expect(layout.heldCount).toBeLessThanOrEqual(5)
    clock += 7000
    expect(() => layout.tick()).not.toThrow()
    expect(layout.heldCount).toBe(0)
  })
})

describe('Rest', () => {
  // Rule: after enough ticks with no new data, tick() returns false and stays false until setGraph adds something.
  it('stops, stays stopped and moves nothing until new data arrives', async () => {
    const layout = await make()
    const g = star(20)
    layout.setGraph(g.nodes, g.links)
    const ticks = settle(layout)
    // d3's alpha min 0.001 at decay 0.005, 50 of the steps already taken by the warm-up.
    expect(ticks).toBeGreaterThan(1200)
    expect(ticks).toBeLessThan(1400)
    const rested = byId(layout)
    for (let i = 0; i < 20; i++) expect(layout.tick()).toBe(false)
    expect(byId(layout)).toEqual(rested)
    layout.setGraph([...g.nodes, node('late')], [...g.links, link('n0', 'late')])
    expect(layout.tick()).toBe(true)
  })

  // Rule: the layout also rests after the cooldown time, however warm it still is.
  it('rests after 30 seconds of running', async () => {
    const layout = await make()
    const g = star(5)
    layout.setGraph(g.nodes, g.links)
    expect(layout.tick()).toBe(true)
    clock += 30_001
    expect(layout.tick()).toBe(false)
    expect(layout.alpha).toBeGreaterThan(0.5)
  })
})

describe('Pin and unpin', () => {
  // Rule: a pinned word follows the pointer exactly while its neighbours move, and wakes a rested layout.
  it('holds a pinned word at the pointer and wakes the layout', async () => {
    const layout = await make()
    const g = star(8)
    layout.setGraph(g.nodes, g.links)
    settle(layout)
    const neighbour = at(layout, 'n1')
    expect(layout.pin('n0', 80, 0, 0)).toBe(true)
    expect(layout.tick()).toBe(true)
    for (let i = 0; i < 60; i++) layout.tick()
    expect(gap(at(layout, 'n0'), [80, 0, 0])).toBeLessThan(1e-4)
    expect(gap(at(layout, 'n1'), neighbour)).toBeGreaterThan(1) // the drag pulled the rest after it
    layout.unpin('n0')
    settle(layout)
    expect(layout.tick()).toBe(false)
  })

  // Rule: a word that is not there cannot be pinned, and says so instead of throwing mid-drag.
  it('reports a pin on an unknown word', async () => {
    const logs: string[] = []
    const layout = await make({ log: msg => logs.push(msg) })
    layout.setGraph(star(2).nodes, star(2).links)
    expect(layout.pin('nobody', 0, 0, 0)).toBe(false)
    expect(logs.some(m => /pin/.test(m))).toBe(true)
  })
})

describe('Links and depth', () => {
  // Rule: a metaphor link rests longer than a thesaurus link (52 against 30).
  it('uses each link\'s own distance', async () => {
    const layout = await make()
    const nodes = [node('a'), node('b'), node('x'), node('y')]
    layout.setGraph(nodes, [link('a', 'b'), link('x', 'y', { relationType: 'metaphor', metaphor: { grounds: [], pathKeys: [], forestSource: 'x', forestTarget: 'y' } })])
    settle(layout)
    const [ab, xy] = [gap(at(layout, 'a'), at(layout, 'b')), gap(at(layout, 'x'), at(layout, 'y'))]
    expect(xy - ab).toBeGreaterThan(15)
    expect(ab).toBeGreaterThan(25)
    expect(xy).toBeLessThan(75)
  })

  // Rule: a link that names a word that is not there is refused before anything changes.
  it('refuses a link to a missing word and leaves the layout alone', async () => {
    const layout = await make()
    const g = star(4)
    layout.setGraph(g.nodes, g.links)
    const before = byId(layout)
    expect(() => layout.setGraph(g.nodes, [...g.links, link('c', 'ghost')])).toThrow(/ghost/)
    expect(byId(layout)).toEqual(before)
    expect(() => layout.setGraph([...g.nodes, node('n1')], g.links)).toThrow(/n1/)
    expect(byId(layout)).toEqual(before)
  })

  // Rule: link ends may already be node objects (d3 swaps them in once fed).
  it('reads link ends that are node objects', async () => {
    const layout = await make()
    const a = node('a')
    const b = node('b')
    layout.setGraph([a, b], [{ ...link('a', 'b'), source: a as never, target: b as never }])
    settle(layout)
    expect(gap(at(layout, 'a'), at(layout, 'b'))).toBeLessThan(60)
  })

  // Rule: the depth rings ride the same maths as forest.ts: one tick of the Rust
  // force and one of forestDepthForce on the same small input agree within 1e-4.
  it('applies the forest depth force exactly as forest.ts does', async () => {
    const { instance } = await WebAssembly.instantiate(wasmBytes, {})
    const ex = instance.exports as unknown as {
      memory: WebAssembly.Memory
      init(n: number, m: number): number
      positions_ptr(): number
      velocities_ptr(): number
      depth_ptr(): number
      set_ring(on: number, spacing: number, offset: number, strength: number, flatten: number): void
      apply_depth(alpha: number): void
    }
    const pts = [[10, 20, 30], [12, 20, 30], [10, 20, 230], [40, 50, 60], [10, 120, 30], [-60, 5, 77], [3, 3, 3]].map(p => p.map(Math.fround))
    const depths = [0, 1, 1, undefined, 2, 3, 0.5]
    const alpha = 0.7
    // The JS force, on node objects.
    const nodes = pts.map(([x, y, z], i) => ({ x, y, z, vx: 0, vy: 0, vz: 0, depth: depths[i] }))
    const force = forestDepthForce((n: (typeof nodes)[number]) => n.depth, FOREST_RING)
    force.initialize(nodes)
    force(alpha)
    // The Rust force, on the same input.
    expect(ex.init(pts.length, 0)).toBe(1)
    new Float32Array(ex.memory.buffer, ex.positions_ptr(), pts.length * 3).set(pts.flat())
    new Float32Array(ex.memory.buffer, ex.depth_ptr(), pts.length).set(depths.map(d => d ?? NaN))
    ex.set_ring(1, FOREST_RING.spacing, FOREST_RING.offset, FOREST_RING.strength, FOREST_RING.flatten)
    ex.apply_depth(alpha)
    const v = new Float32Array(ex.memory.buffer, ex.velocities_ptr(), pts.length * 3)
    nodes.forEach((n, i) => {
      expect(Math.abs(v[3 * i] - n.vx), `vx of ${i}`).toBeLessThan(1e-4)
      expect(Math.abs(v[3 * i + 1] - n.vy), `vy of ${i}`).toBeLessThan(1e-4)
      expect(Math.abs(v[3 * i + 2] - n.vz), `vz of ${i}`).toBeLessThan(1e-4)
    })
    // The baseline is real: the force moved something, and spared the nodes it should.
    expect(Math.max(...nodes.map(n => Math.abs(n.vx) + Math.abs(n.vy) + Math.abs(n.vz)))).toBeGreaterThan(1)
    expect(nodes[3].vx + nodes[3].vy + nodes[3].vz).toBe(0)
  })
})

describe('Capacity', () => {
  // Rule: growing past capacity re-creates the engine without losing anything: a layout
  // that had to grow ends bit for bit where one with room to spare ends, positions,
  // velocities, fixed words and alpha included.
  it('keeps every position bit for bit through a re-init', async () => {
    const small = await make({ initialCapacity: { nodes: 4, links: 4 }, holdOnArrival: true })
    const roomy = await make({ initialCapacity: { nodes: 4096, links: 4096 }, holdOnArrival: true })
    const first = star(3)
    const second = star(30)
    for (const l of [small, roomy]) {
      l.setGraph(first.nodes, first.links)
      for (let i = 0; i < 20; i++) l.tick()
      l.pin('n1', 20, 20, 20)
    }
    const before = byId(small)
    small.setGraph(second.nodes, second.links) // 31 words in room for 4: it must grow, twice
    roomy.setGraph(second.nodes, second.links)
    expect(small.capacity.nodes).toBeGreaterThanOrEqual(31)
    expect(roomy.capacity.nodes).toBe(4096)
    expect(small.capacity.nodes).toBeLessThan(4096)
    expect(byId(small)).toEqual(byId(roomy))
    for (let i = 0; i < 25; i++) {
      small.tick()
      roomy.tick()
    }
    expect(byId(small)).toEqual(byId(roomy))
    expect(small.alpha).toBe(roomy.alpha)
    expect(before.size).toBe(4) // the starting point was real
  })

  // Rule: a re-init preserves the words that were there before any tick, bit for bit.
  it('leaves the old words exactly where they were when it grows', async () => {
    const layout = await make({ initialCapacity: { nodes: 4, links: 4 }, warmupTicks: 0 })
    const g = star(3)
    layout.setGraph(g.nodes, g.links)
    for (let i = 0; i < 17; i++) layout.tick()
    const before = byId(layout)
    const more = star(40)
    layout.setGraph(more.nodes.slice(0, 4).concat(more.nodes.slice(4)), more.links)
    for (const [id, p] of before) expect(byId(layout).get(id), id).toEqual(p)
  })

  // Rule: the view onto positions is the engine's own memory, shared while nothing
  // changes and made again when the memory buffer is a different object.
  it('re-makes the positions view when the memory grows', async () => {
    const layout = await make({ initialCapacity: { nodes: 4, links: 4 }, warmupTicks: 0 })
    const g = star(3)
    layout.setGraph(g.nodes, g.links)
    const view = layout.positions()
    expect(layout.positions() === view).toBe(true)
    const snapshot = Array.from(view)
    expect(view.length).toBe(12)
    const big = star(2000)
    layout.setGraph(big.nodes, big.links)
    expect(view.byteLength).toBe(0) // the old view was detached by the growth
    const fresh = layout.positions()
    expect(fresh === view).toBe(false)
    expect(fresh.length).toBe(2001 * 3)
    expect(Array.from(fresh.subarray(0, 12))).toEqual(snapshot) // seeded positions of the first words are unchanged
    layout.tick()
    expect(layout.positions() === fresh).toBe(true)
  })
})

describe('against d3-force-3d, with the depth rings on', () => {
  // A thesaurus for "patience" with second-order words, the forest fixture laid over it.
  function scene(): { data: GraphData; depthOf: (n: GraphNode) => number | undefined } {
    const nodes: GraphNode[] = [node('patience', 0, { relationType: 'central', val: 8 })]
    const links: GraphLink[] = []
    for (let i = 0; i < 22; i++) {
      nodes.push(node(`syn${i}`, 1))
      links.push(link('patience', `syn${i}`))
    }
    for (let i = 0; i < 9; i++) {
      nodes.push(node(`sub${i}`, 2))
      links.push(link(`syn${i % 4}`, `sub${i}`, { order: 2 }))
    }
    const forest = forestToGraph(patience as ForestResponse)
    const { data, overlay } = composeForest({ nodes, links }, forest)
    return { data, depthOf: n => overlay!.byNodeId.get(n.id)?.depth }
  }

  const rms = (a: ArrayLike<number>) => {
    const n = a.length / 3
    const c = [0, 0, 0]
    for (let i = 0; i < n; i++) for (let k = 0; k < 3; k++) c[k] += a[3 * i + k] / n
    let sum = 0
    for (let i = 0; i < n; i++) for (let k = 0; k < 3; k++) sum += (a[3 * i + k] - c[k]) ** 2
    return Math.sqrt(sum / n)
  }

  /** How far the forest words sit from the root's plane on average: what the rings' flattening sets. */
  function forestDepthSpread(flat: ArrayLike<number>, ids: string[], depthOf: (n: GraphNode) => number | undefined, data: GraphData): number {
    const root = ids.indexOf('patience')
    const forest = data.nodes.filter(nd => (depthOf(nd) ?? 0) > 0).map(nd => ids.indexOf(nd.id))
    return forest.reduce((sum, i) => sum + Math.abs(flat[3 * i + 2] - flat[3 * root + 2]), 0) / forest.length
  }

  /** The app's d3 set-up: link, charge, centre, then the depth force. */
  function d3Sizes(withRings: boolean) {
    const { data, depthOf } = scene()
    const nodes = data.nodes.map(n => ({ ...n })) as (GraphNode & SimulationNode)[]
    const links = data.links.map(l => ({ ...l }))
    const sim = forceSimulation(nodes, 3)
      .force('link', (forceLink(links).id((d: GraphNode) => d.id) as unknown as { distance(f: (l: GraphLink) => number): never }).distance(l => (l.metaphor ? FOREST_LINK_DISTANCE : 30)))
      .force('charge', forceManyBody())
      .force('center', forceCenter())
      .velocityDecay(0.85)
      .alphaDecay(0.005)
      .stop()
    if (withRings) sim.force('forestDepth', forestDepthForce((n: GraphNode) => depthOf(n), FOREST_RING) as never)
    const flat = () => Float32Array.from(nodes.flatMap(n => [n.x!, n.y!, n.z!]))
    sim.tick(50)
    const warm = rms(flat())
    sim.tick(300)
    const ids = nodes.map(nd => nd.id)
    return { warm, later: rms(flat()), nodeCount: nodes.length, spread: forestDepthSpread(flat(), ids, depthOf, data) }
  }

  async function rustSizes(withRings: boolean) {
    const { data, depthOf } = scene()
    const layout = await make(withRings ? { depthOf, ring: FOREST_RING } : {})
    layout.setGraph(data.nodes, data.links) // includes the 50 warm-up ticks
    const warm = rms(layout.positions())
    for (let i = 0; i < 300; i++) layout.tick()
    const ids = Array.from({ length: layout.size }, (_, i) => layout.idAt(i))
    return { warm, later: rms(layout.positions()), nodeCount: layout.size, spread: forestDepthSpread(layout.positions(), ids, depthOf, data) }
  }

  // Rule: both engines lay one realistic scene out at a similar overall size
  // (within 25 per cent) after the warm-up and again 300 ticks later. Exact
  // equality is not expected: d3 works in float64 with its own jiggle.
  it('lays a forest over a thesaurus out at a similar size', async () => {
    const js = d3Sizes(true)
    const rust = await rustSizes(true)
    expect(js.nodeCount).toBe(rust.nodeCount)
    expect(js.nodeCount).toBeGreaterThan(45)
    for (const phase of ['warm', 'later'] as const) {
      const [a, b] = [js[phase], rust[phase]]
      expect(Math.abs(a - b) / Math.max(a, b), `${phase}: d3 ${a.toFixed(1)} against Rust ${b.toFixed(1)}`).toBeLessThan(0.25)
    }
  })

  // Rule: the comparison means something only if the rings change the layout: they
  // flatten the forest towards the root's plane, so its words sit nearer that plane.
  it('has rings that change how flat the forest lies', async () => {
    const [on, off] = [d3Sizes(true), d3Sizes(false)]
    const [rustOn, rustOff] = [await rustSizes(true), await rustSizes(false)]
    expect(Math.abs(on.spread - off.spread) / off.spread).toBeGreaterThan(0.1)
    expect(Math.abs(rustOn.spread - rustOff.spread) / rustOff.spread).toBeGreaterThan(0.1)
  })
})
