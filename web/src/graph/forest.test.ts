import { describe, it, expect } from 'vitest'
import type { ForestResponse } from '@/types/api'
import type { GraphData, GraphLink } from './types'
import patience from '@/fixtures/forest-patience.json'
import { forestToGraph, composeForest, litEndpoints, normaliseWord, forestDepthForce, streamMarks, fadeMarks, nextFadeEnd, FOREST_FADE_MS, LIVE_SCORE } from './forest'
import type { StreamPath } from '@/forest/state'

const forestResponse = patience as ForestResponse

// A browse graph for "patience" that already holds two forest words, one of
// them spelt with different case and spacing, plus a second-order node.
function thesaurusGraph(): GraphData {
  return {
    nodes: [
      { id: 'patience', word: 'patience', relationType: 'central', val: 8, order: 0, rarity: 'common' },
      { id: 'forbearance', word: 'forbearance', relationType: 'synonym', val: 4, order: 1, rarity: 'rare' },
      { id: 'escapement', word: 'escapement', relationType: 'similar', val: 2, order: 1, rarity: 'rare' },
      { id: 'Peat  Bog', word: 'Peat  Bog', relationType: 'similar', val: 1, order: 2 },
    ],
    links: [
      { source: 'patience', target: 'forbearance', relationType: 'synonym', order: 1 },
      { source: 'patience', target: 'escapement', relationType: 'similar', order: 1 },
      { source: 'forbearance', target: 'Peat  Bog', relationType: 'similar', order: 2 },
    ],
  }
}

const endOf = (v: unknown): string => (typeof v === 'string' ? v : (v as { id: string }).id)
const metaphorLinks = (data: GraphData): GraphLink[] => data.links.filter(l => l.metaphor)

describe('normaliseWord', () => {
  it('lower-cases, trims and collapses inner whitespace, as the server does', () => {
    expect(normaliseWord('  Peat \t Bog ')).toBe('peat bog')
  })
})

describe('forestToGraph', () => {
  const forest = forestToGraph(forestResponse)

  it('records each node role, and its depth as the fewest hops from the source', () => {
    expect(forest.info.get('patience')).toMatchObject({ role: 'source', depth: 0 })
    expect(forest.info.get('dormant seed')).toMatchObject({ role: 'hop', depth: 1 })
    expect(forest.info.get('keloid')).toMatchObject({ role: 'endpoint', depth: 3 })
  })

  it(`marks an endpoint live when its score is ${LIVE_SCORE} or more`, () => {
    expect(forest.info.get('seed vault')?.live).toBe(true)   // 7
    expect(forest.info.get('solera')?.live).toBe(false)      // 6
    expect(forest.info.get('dormant seed')?.live).toBe(false)
  })

  it('lists, for every node, exactly the kept paths that pass through or end at it', () => {
    for (const [id, info] of forest.info) {
      const expected = forestResponse.endpoints.filter(e => e.path.includes(id)).map(e => e.id).sort()
      expect([...info.endpointIds].sort(), id).toEqual(expected)
    }
  })

  it('keeps the endpoint list in API order', () => {
    expect(forest.endpoints.map(e => e.id)).toEqual(forestResponse.endpoints.map(e => e.id))
  })
})

describe('composeForest', () => {
  it('passes the thesaurus graph through unchanged when there is no forest', () => {
    const base = thesaurusGraph()
    const { data, overlay } = composeForest(base, null)
    expect(data).toBe(base)
    expect(overlay).toBeNull()
  })

  // Rule: every endpoint in the response is reachable from the source by
  // metaphor links in the graph data.
  it('makes every endpoint reachable from the source along metaphor links', () => {
    const forest = forestToGraph(forestResponse)
    const { data, overlay } = composeForest(thesaurusGraph(), forest)
    const sourceId = overlay!.nodeIdByForestId.get('patience')!
    const out = new Map<string, string[]>()
    for (const l of metaphorLinks(data)) {
      out.set(endOf(l.source), [...(out.get(endOf(l.source)) ?? []), endOf(l.target)])
    }
    const reached = new Set([sourceId])
    const queue = [sourceId]
    while (queue.length) for (const next of out.get(queue.shift()!) ?? []) if (!reached.has(next)) { reached.add(next); queue.push(next) }

    expect(forestResponse.endpoints.length).toBeGreaterThan(0)
    for (const e of forestResponse.endpoints) {
      expect(reached.has(overlay!.nodeIdByForestId.get(e.id)!), e.id).toBe(true)
    }
  })

  // Rule: a forest word that is already a thesaurus node becomes that node.
  it('merges a forest word into the existing thesaurus node by normalised word, keeping the node object', () => {
    const base = thesaurusGraph()
    const { data, overlay } = composeForest(base, forestToGraph(forestResponse))
    const ids = data.nodes.map(n => n.id)
    expect(new Set(ids).size).toBe(ids.length)

    expect(overlay!.nodeIdByForestId.get('patience')).toBe('patience')
    expect(overlay!.nodeIdByForestId.get('peat bog')).toBe('Peat  Bog')
    expect(data.nodes.find(n => n.id === 'Peat  Bog')).toBe(base.nodes[3])
    expect(data.nodes.find(n => n.id === 'escapement')).toBe(base.nodes[2])
    expect(overlay!.byNodeId.get('escapement')?.role).toBe('endpoint')
    expect(overlay!.byNodeId.get('forbearance')).toBeUndefined()
  })

  it('leaves no link pointing at a node that is not in the graph', () => {
    const { data } = composeForest(thesaurusGraph(), forestToGraph(forestResponse))
    const ids = new Set(data.nodes.map(n => n.id))
    for (const l of data.links) {
      expect(ids.has(endOf(l.source)), `${endOf(l.source)} -> ${endOf(l.target)}`).toBe(true)
      expect(ids.has(endOf(l.target)), `${endOf(l.source)} -> ${endOf(l.target)}`).toBe(true)
    }
  })

  it('adds metaphor links as their own objects, never merged into a thesaurus link on the same pair', () => {
    const base = thesaurusGraph()
    const { data } = composeForest(base, forestToGraph(forestResponse))
    const pair = data.links.filter(l => endOf(l.source) === 'patience' && endOf(l.target) === 'escapement')
    expect(pair).toHaveLength(2)
    expect(pair.filter(l => l.metaphor)).toHaveLength(1)
    expect(pair.find(l => !l.metaphor)).toBe(base.links[1])
    expect(metaphorLinks(data)).toHaveLength(forestResponse.edges.length)
  })

  it('carries each edge’s grounds and the paths through it on its metaphor link', () => {
    const { data } = composeForest(thesaurusGraph(), forestToGraph(forestResponse))
    const link = metaphorLinks(data).find(l => endOf(l.source) === 'patience' && endOf(l.target) === 'dormant seed')!
    expect(link.metaphor!.grounds).toEqual(['waits intact until conditions allow'])
    expect([...link.metaphor!.endpointIds].sort()).toEqual(['controlled burn', 'seed vault'])
  })

  it('reuses forest-only node objects across recompositions, so a re-layout keeps their positions', () => {
    const forest = forestToGraph(forestResponse)
    const first = composeForest(thesaurusGraph(), forest).data
    const second = composeForest(thesaurusGraph(), forest).data
    const varve1 = first.nodes.find(n => n.id === 'varve')
    expect(varve1).toBeDefined()
    expect(second.nodes.find(n => n.id === 'varve')).toBe(varve1)
  })

  it('gives metaphor links string endpoints every time, so a re-fed simulation never holds a stale node object', () => {
    const forest = forestToGraph(forestResponse)
    const first = composeForest(thesaurusGraph(), forest).data
    // d3 replaces string ends with node objects once fed
    for (const l of metaphorLinks(first)) l.source = { id: endOf(l.source) } as never
    const second = composeForest(thesaurusGraph(), forest).data
    for (const l of metaphorLinks(second)) expect(typeof l.source).toBe('string')
  })
})

describe('streamed forest marks', () => {
  const hop = (from: string, to: string) => ({ from, to, ground: `${from} to ${to}` })
  const path = (id: string, status: StreamPath['status'], hops: [string, string][], endpoint?: string): StreamPath =>
    ({ id, facet: Number(id[1]), hops: hops.map(([f, t]) => hop(f, t)), status, endpoint, score: endpoint ? 8 : undefined })
  const key = (s: string, t: string) => JSON.stringify([s, t])
  // facet 0: head hop patience -> lake sediment, branches b0 and b1 off it
  const paths = (head: StreamPath['status'], b0: StreamPath['status'], b1: StreamPath['status']): Record<string, StreamPath> => ({
    f0: path('f0', head, [['patience', 'lake sediment']]),
    f0b0: path('f0b0', b0, [['lake sediment', 'varve']], b0 === 'kept' ? 'varve' : undefined),
    f0b1: path('f0b1', b1, [['lake sediment', 'silt'], ['silt', 'delta']]),
  })

  // Rule: a link or node stays while any pending or kept path uses it, and a
  // branch uses its facet's head hop even though that hop came under the facet's id.
  it('keeps the head hop while any branch still uses it, and drops it once none does', () => {
    const live = streamMarks(paths('rejected', 'pending', 'rejected'), null)
    expect(live.links.get(key('patience', 'lake sediment'))?.status).toBe('pending')
    expect(live.links.has(key('silt', 'delta'))).toBe(false)
    expect(live.nodes.has('silt')).toBe(false)
    const none = streamMarks(paths('rejected', 'rejected', 'rejected'), null)
    expect(none.links.size).toBe(0)
    expect(none.nodes.size).toBe(0)
  })

  it('a link or node on a kept path is kept, the rest of a pending path stays pending', () => {
    const m = streamMarks(paths('rejected', 'kept', 'pending'), null)
    expect(m.links.get(key('patience', 'lake sediment'))?.status).toBe('kept')
    expect(m.links.get(key('lake sediment', 'varve'))?.status).toBe('kept')
    expect(m.links.get(key('silt', 'delta'))?.status).toBe('pending')
    expect(m.nodes.get('varve')).toMatchObject({ role: 'endpoint', live: true, depth: 2, status: 'kept' })
    expect(m.nodes.get('delta')).toMatchObject({ role: 'hop', depth: 3, status: 'pending' })
    expect(m.nodes.get('patience')).toMatchObject({ role: 'source', depth: 0 })
  })

  // Rule: a mark never doubles a node or link the latest snapshot already draws.
  it('leaves out every node and link the snapshot already holds', () => {
    const forest = forestToGraph(forestResponse)
    const m = streamMarks(paths('rejected', 'kept', 'pending'), forest)
    // the snapshot holds patience -> lake sediment -> varve
    expect(m.links.has(key('patience', 'lake sediment'))).toBe(false)
    expect(m.links.has(key('lake sediment', 'varve'))).toBe(false)
    expect(m.nodes.has('lake sediment')).toBe(false)
    expect(m.links.has(key('lake sediment', 'silt'))).toBe(true)
    expect(m.nodes.has('silt')).toBe(true)
  })

  // Rule: a mark that no path uses any more fades for FOREST_FADE_MS, then goes;
  // with no fade time (reduced motion) it goes at once.
  it('fades a dropped mark for the fade time, then removes it', () => {
    const before = streamMarks(paths('pending', 'pending', 'pending'), null)
    const after = streamMarks(paths('pending', 'pending', 'rejected'), null)
    expect(before.links.has(key('silt', 'delta'))).toBe(true)
    const fading = fadeMarks(before, after, null, 1000, FOREST_FADE_MS)
    expect(fading.links.get(key('silt', 'delta'))).toMatchObject({ status: 'fading', fadeUntil: 1000 + FOREST_FADE_MS })
    expect(fading.nodes.get('delta')).toMatchObject({ status: 'fading', fadeUntil: 1000 + FOREST_FADE_MS })
    expect(fading.links.get(key('patience', 'lake sediment'))?.status).toBe('pending')
    expect(nextFadeEnd(fading)).toBe(1000 + FOREST_FADE_MS)
    // a later update during the fade keeps its deadline
    const still = fadeMarks(fading, after, null, 1300, FOREST_FADE_MS)
    expect(still.links.get(key('silt', 'delta'))?.fadeUntil).toBe(1000 + FOREST_FADE_MS)
    const gone = fadeMarks(still, after, null, 1000 + FOREST_FADE_MS, FOREST_FADE_MS)
    expect(gone.links.has(key('silt', 'delta'))).toBe(false)
    expect(nextFadeEnd(gone)).toBeNull()
    const instant = fadeMarks(before, after, null, 1000, 0)
    expect(instant.links.has(key('silt', 'delta'))).toBe(false)
    expect(instant.nodes.has('delta')).toBe(false)
  })

  it('never fades a mark that moved into the snapshot', () => {
    const forest = forestToGraph(forestResponse)
    const before = streamMarks(paths('rejected', 'kept', 'rejected'), null)
    const after = streamMarks(paths('rejected', 'kept', 'rejected'), forest)
    expect(before.links.has(key('lake sediment', 'varve'))).toBe(true)
    const m = fadeMarks(before, after, forest, 1000, FOREST_FADE_MS)
    expect(m.links.size).toBe(0)
    expect(m.nodes.size).toBe(0)
  })

  it('a mark that a path uses again stops fading', () => {
    const before = streamMarks(paths('pending', 'pending', 'pending'), null)
    const dropped = fadeMarks(before, streamMarks(paths('pending', 'pending', 'rejected'), null), null, 1000, FOREST_FADE_MS)
    expect(dropped.links.get(key('silt', 'delta'))?.status).toBe('fading')
    const back = fadeMarks(dropped, before, null, 1100, FOREST_FADE_MS)
    expect(back.links.get(key('silt', 'delta'))?.status).toBe('pending')
  })

  describe('composed with the thesaurus', () => {
    const marks = () => streamMarks(paths('rejected', 'kept', 'pending'), null)

    it('draws a stream with no snapshot yet: an overlay whose source is depth 0, and no dangling link', () => {
      const { data, overlay } = composeForest(thesaurusGraph(), null, { marks: marks(), pool: new Map() })
      expect(overlay).not.toBeNull()
      expect(overlay!.byNodeId.get('patience')).toMatchObject({ role: 'source', depth: 0 })
      const ids = new Set(data.nodes.map(n => n.id))
      const streamed = metaphorLinks(data)
      expect(streamed.length).toBe(4)
      for (const l of streamed) {
        expect(ids.has(endOf(l.source)) && ids.has(endOf(l.target))).toBe(true)
        expect(l.metaphor!.stream).toBeDefined()
      }
    })

    // Rule: a node keeps one object from its first hop to the final forest, so its position holds.
    it('reuses one node object from pending mark to snapshot node', () => {
      const pool = new Map()
      const first = composeForest(thesaurusGraph(), null, { marks: marks(), pool }).data
      const varve = first.nodes.find(n => n.id === 'varve')!
      expect(varve).toBeDefined()
      const forest = forestToGraph(forestResponse, pool)
      const second = composeForest(thesaurusGraph(), forest, { marks: streamMarks(paths('rejected', 'kept', 'pending'), forest), pool }).data
      expect(second.nodes.find(n => n.id === 'varve')).toBe(varve)
      expect(second.nodes.find(n => n.id === 'delta')).toBe(first.nodes.find(n => n.id === 'delta'))
    })

    it('places a new node at its parent, so the graph grows out from it rather than from the origin', () => {
      const pool = new Map()
      const base = thesaurusGraph()
      Object.assign(base.nodes[0], { x: 10, y: -20, z: 5 })
      const data = composeForest(base, null, { marks: marks(), pool }).data
      const sediment = data.nodes.find(n => n.id === 'lake sediment')!
      expect(sediment.x).toBeDefined()
      expect(Math.hypot(sediment.x! - 10, sediment.y! + 20, sediment.z! - 5)).toBeLessThan(5)
      // a node with a position already keeps it
      sediment.x = 99
      const again = composeForest(base, null, { marks: marks(), pool }).data
      expect(again.nodes.find(n => n.id === 'lake sediment')!.x).toBe(99)
    })
  })
})

describe('litEndpoints', () => {
  const forest = forestToGraph(forestResponse)

  it('lights nothing when there is no target', () => {
    expect(litEndpoints(forest, null)).toBeNull()
  })

  // Rule: hovering a node lights every path through it and only those.
  it('lights exactly the paths that contain a node', () => {
    for (const id of forest.info.keys()) {
      const expected = new Set(forestResponse.endpoints.filter(e => e.path.includes(id)).map(e => e.id))
      expect(litEndpoints(forest, { kind: 'node', id }), id).toEqual(expected)
    }
  })

  it('lights exactly the paths that use a link', () => {
    const lit = litEndpoints(forest, { kind: 'link', source: 'scar tissue', target: 'hypertrophic scar' })
    expect(lit).toEqual(new Set(['keloid']))
  })

  it('lights one path for a path target', () => {
    expect(litEndpoints(forest, { kind: 'path', endpointId: 'varve' })).toEqual(new Set(['varve']))
  })

  it('lights nothing for a target that is not in this forest', () => {
    expect(litEndpoints(forest, { kind: 'node', id: 'nowhere' })).toEqual(new Set())
  })
})

describe('forestDepthForce', () => {
  // Rule: the forest reads as a tree growing out of the source: under the force,
  // a node settles farther from the root the more hops it is from the source.
  it('settles nodes in rings by depth around the root', () => {
    const depth = new Map<object, number>()
    const root = { x: 0, y: 0, z: 0, vx: 0, vy: 0, vz: 0 }
    depth.set(root, 0)
    const nodes = [root]
    for (let i = 0; i < 30; i++) {
      // start everyone bunched near the root in a random direction
      const n = { x: Math.sin(i) * 5, y: Math.cos(i * 1.7) * 5, z: Math.sin(i * 0.3) * 5, vx: 0, vy: 0, vz: 0 }
      depth.set(n, (i % 3) + 1)
      nodes.push(n)
    }
    const thesaurusNode = { x: 3, y: 0, z: 0, vx: 0, vy: 0, vz: 0 }
    nodes.push(thesaurusNode)

    const force = forestDepthForce(n => depth.get(n), { spacing: 40, offset: 20, strength: 0.2 })
    force.initialize(nodes)
    for (let t = 0; t < 300; t++) {
      force(1)
      for (const n of nodes) { n.x += n.vx; n.y += n.vy; n.z += n.vz; n.vx *= 0.5; n.vy *= 0.5; n.vz *= 0.5 }
    }
    const meanDist = (d: number) => {
      const ring = nodes.filter(n => depth.get(n) === d)
      return ring.reduce((s, n) => s + Math.hypot(n.x - root.x, n.y - root.y, n.z - root.z), 0) / ring.length
    }
    // the first ring clears the thesaurus cloud by the offset
    expect(meanDist(1)).toBeCloseTo(60, 0)
    expect(meanDist(2)).toBeCloseTo(100, 0)
    expect(meanDist(3)).toBeCloseTo(140, 0)
    expect(thesaurusNode.x).toBe(3) // nodes outside the forest are left alone
  })

  // Rule: from the default camera the forest reads as a flat burst, not a 3D tangle.
  it('with flatten set, draws forest nodes toward the root plane facing the camera', () => {
    const root = { x: 0, y: 0, z: 0, vx: 0, vy: 0, vz: 0 }
    const n = { x: 50, y: 0, z: 60, vx: 0, vy: 0, vz: 0 }
    const depth = (node: object) => (node === root ? 0 : 1)
    const force = forestDepthForce(depth, { spacing: 60, flatten: 0.5, strength: 0.2 })
    force.initialize([root, n])
    for (let t = 0; t < 300; t++) {
      force(1)
      n.x += n.vx; n.y += n.vy; n.z += n.vz; n.vx *= 0.5; n.vy *= 0.5; n.vz *= 0.5
    }
    expect(Math.abs(n.z)).toBeLessThan(5)
    expect(Math.hypot(n.x, n.y, n.z)).toBeCloseTo(60, 0)
  })

  it('does nothing when no node has depth 0', () => {
    const n = { x: 1, y: 1, z: 1, vx: 0, vy: 0, vz: 0 }
    const force = forestDepthForce(() => 2, { spacing: 40 })
    force.initialize([n])
    force(1)
    expect([n.vx, n.vy, n.vz]).toEqual([0, 0, 0])
  })
})
