import { describe, it, expect } from 'vitest'
import { forceSimulation, forceLink, forceManyBody, forceCenter } from 'd3-force-3d'
import type { GraphLink, GraphNode } from './types'
import { arrivals, seedArrivals, holdSettled, releaseHeld, shouldRelease, SETTLED_SPEED, type SimNode } from './growth'

const node = (id: string, order = 1, pos?: { x: number; y: number; z: number }): SimNode =>
  ({ id, word: id, relationType: 'synonym', val: 1, order, ...pos })
const link = (source: string, target: string): GraphLink => ({ source, target, relationType: 'synonym', order: 1 })

describe('arrivals', () => {
  // Rule: a node is a newcomer when its id was not fed before or it has no position yet.
  it('names nodes with a new id or no position, and nothing else', () => {
    const nodes = [node('old', 1, { x: 1, y: 2, z: 3 }), node('fresh'), node('replaced')]
    expect(arrivals(nodes, new Set(['old', 'replaced'])).map(n => n.id)).toEqual(['fresh', 'replaced'])
    expect(arrivals(nodes.slice(0, 1), new Set(['old']))).toEqual([])
  })
})

describe('seedArrivals', () => {
  // Rule: every unplaced newcomer starts within the jitter of a placed neighbour, the
  // shallowest one, and a chain of newcomers seeds outward from its placed end in one pass.
  it('starts each newcomer beside its parent, chains included', () => {
    const parent = node('parent', 1, { x: 100, y: -50, z: 20 })
    const centre = node('centre', 0, { x: 0, y: 0, z: 0 })
    const child = node('child', 2)
    const grandchild = node('grandchild', 3)
    // The grandchild is listed first: order, not array position, decides who seeds first.
    const newcomers = [grandchild, child]
    seedArrivals(newcomers, [link('centre', 'parent'), link('child', 'grandchild'), link('parent', 'child')], [centre, parent, child, grandchild], () => 1)
    expect(child).toMatchObject({ x: 101, y: -49, z: 21 })
    expect(grandchild).toMatchObject({ x: 102, y: -48, z: 22 })
  })

  // Rule: a newcomer the simulation already placed (a seeded forest node) keeps its position.
  it('leaves a placed newcomer and a newcomer with no placed neighbour alone', () => {
    const placed = node('placed', 1, { x: 5, y: 5, z: 5 })
    const lonely = node('lonely')
    seedArrivals([placed, lonely], [link('placed', 'x')], [placed, lonely], () => 1)
    expect(placed).toMatchObject({ x: 5, y: 5, z: 5 })
    expect(lonely.x).toBeUndefined()
  })

  // Rule: link ends may already be node objects (d3 swaps them in once fed).
  it('reads link ends that d3 has turned into node objects', () => {
    const parent = node('parent', 1, { x: 10, y: 10, z: 10 })
    const child = node('child', 2)
    seedArrivals([child], [{ ...link('parent', 'child'), source: parent as never, target: child as never }], [parent, child], () => 0)
    expect(child).toMatchObject({ x: 10, y: 10, z: 10 })
  })
})

describe('holdSettled and releaseHeld', () => {
  // Rule: only placed, free, non-newcomer nodes are held, and release frees exactly those.
  it('holds placed free nodes at their position and releases only what it held', () => {
    const free = node('free', 1, { x: 1, y: 2, z: 3 })
    const fixed: SimNode = { ...node('fixed', 1, { x: 4, y: 4, z: 4 }), fx: 9, fy: 9, fz: 9 }
    const fresh = node('fresh', 2, { x: 0, y: 0, z: 0 })
    const unplaced = node('unplaced')
    const held = holdSettled([free, fixed, fresh, unplaced], new Set(['fresh']))
    expect([...held]).toEqual(['free'])
    expect(free).toMatchObject({ fx: 1, fy: 2, fz: 3 })
    expect(fresh.fx).toBeUndefined()
    releaseHeld([free, fixed, fresh], held)
    expect('fx' in free || 'fy' in free || 'fz' in free).toBe(false)
    expect(fixed).toMatchObject({ fx: 9, fy: 9, fz: 9 })
  })

  // Rule: a held node dropped by a drag during the hold ends free, as a drag does today.
  it('frees a held node that a drag moved, and hands a node mid-drag back to the drag', () => {
    const dropped = node('dropped', 1, { x: 1, y: 1, z: 1 })
    const dragging = node('dragging', 1, { x: 2, y: 2, z: 2 })
    const held = holdSettled([dropped, dragging], new Set())
    // The library keeps a held node's fx at the drop point (it saw fx set at dragstart).
    Object.assign(dropped, { fx: 40, fy: 40, fz: 40 })
    // Mid-drag, the library has stored the fixed position it will restore at dragend.
    const initial = { fx: 2, fy: 2, fz: 2 }
    Object.assign(dragging, { fx: 50, fy: 50, fz: 50, __initialFixedPos: initial })
    releaseHeld([dropped, dragging], held)
    expect(dropped.fx).toBeUndefined()
    expect(dragging.fx).toBe(50) // the pointer still has it
    expect(initial).toEqual({ fx: undefined, fy: undefined, fz: undefined }) // so dragend frees it
  })
})

describe('shouldRelease', () => {
  const slow = { ...node('a', 1, { x: 0, y: 0, z: 0 }), vx: SETTLED_SPEED / 2, vy: 0, vz: 0 }
  const fast = { ...node('b', 1, { x: 0, y: 0, z: 0 }), vx: SETTLED_SPEED * 4, vy: 0, vz: 0 }
  const opts = { quietMs: 1000, maxQuietMs: 6000 }

  // Rule: held nodes go free only once arrivals have stopped AND the newcomers have settled,
  // or after a long quiet whatever the newcomers do.
  it('waits for quiet and settled newcomers, with a cap on the wait', () => {
    expect(shouldRelease({ ...opts, now: 500, lastArrivalAt: 0, newcomers: [slow] })).toBe(false)
    expect(shouldRelease({ ...opts, now: 1500, lastArrivalAt: 0, newcomers: [slow] })).toBe(true)
    expect(shouldRelease({ ...opts, now: 1500, lastArrivalAt: 0, newcomers: [slow, fast] })).toBe(false)
    expect(shouldRelease({ ...opts, now: 6000, lastArrivalAt: 0, newcomers: [fast] })).toBe(true)
  })
})

describe('steady growth in a real force simulation', () => {
  type D3Node = SimNode & { vx: number; vy: number; vz: number }
  /** A star of `n` words settled the way the browse graph is configured. */
  function settledStar(n: number) {
    const nodes: D3Node[] = [node('c', 0), ...Array.from({ length: n }, (_, i) => node(`n${i}`))] as D3Node[]
    const links: GraphLink[] = nodes.slice(1).map(m => link('c', m.id))
    const sim = forceSimulation(nodes, 3)
      .force('link', forceLink(links.map(l => ({ ...l }))).id((d: { id: string }) => d.id).distance(30))
      .force('charge', forceManyBody())
      .force('center', forceCenter())
      .velocityDecay(0.85).alphaDecay(0.005).stop()
    for (let i = 0; i < 1200; i++) sim.tick()
    return { nodes, links, sim }
  }
  /** Feed eight glimpsed words under n2 as graphData() does: reheat, then 50 warm-up ticks.
   *  Returns how far the most-moved settled node went. */
  function arrive(hold: boolean): { moved: number; settledSpeed: number } {
    const { nodes, links, sim } = settledStar(12)
    const settledSpeed = Math.max(...nodes.map(n => Math.hypot(n.vx, n.vy, n.vz)))
    const before = nodes.map(n => [n.x!, n.y!, n.z!])
    const fresh = Array.from({ length: 8 }, (_, i) => node(`m${i}`, 2))
    const all = [...nodes, ...fresh]
    const allLinks = [...links, ...fresh.map(f => link('n2', f.id))]
    const newcomers = arrivals(all, new Set(nodes.map(n => n.id)))
    let k = 0
    seedArrivals(newcomers, allLinks, all, () => ((k++ % 5) - 2) / 2)
    if (hold) holdSettled(all, new Set(newcomers.map(n => n.id)))
    sim.nodes(all)
    ;(sim.force('link') as unknown as { links(l: unknown[]): void }).links(allLinks.map(l => ({ ...l })))
    sim.alpha(1)
    for (let i = 0; i < 50; i++) sim.tick()
    const moved = Math.max(...nodes.map((n, i) => Math.hypot(n.x! - before[i][0], n.y! - before[i][1], n.z! - before[i][2])))
    return { moved, settledSpeed }
  }

  // Rule: a node that had settled before an arrival moves less than a small distance
  // during that arrival's warm-up.
  it('keeps settled nodes within 0.5 units through an arrival', () => {
    const baseline = arrive(false)
    // The baseline is real: the star had settled, and an unheld arrival does move it.
    expect(baseline.settledSpeed).toBeLessThan(SETTLED_SPEED)
    expect(baseline.moved).toBeGreaterThan(5)
    expect(arrive(true).moved).toBeLessThan(0.5)
  })

  // Rule: newcomers grow out of their parent, not out of the origin.
  it('starts glimpsed words at their parent', () => {
    const { nodes, links } = settledStar(6)
    const parent = nodes.find(n => n.id === 'n2')!
    const fresh = [node('m0', 2), node('m1', 2)]
    seedArrivals(fresh, [...links, link('n2', 'm0'), link('m1', 'n2')], [...nodes, ...fresh])
    for (const f of fresh) {
      expect(Math.hypot(f.x! - parent.x!, f.y! - parent.y!, f.z! - parent.z!)).toBeLessThan(4)
    }
  })
})
