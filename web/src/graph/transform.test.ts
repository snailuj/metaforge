import { describe, it, expect } from 'vitest'
import {
  transformLookupToGraph,
  mergeExpansion,
  recentreGraph,
  mergeGlimpse,
  solidify,
  relationReach,
} from './transform'
import type { LookupResult } from '@/types/api'
import type { GraphData, GraphLink } from './types'

const melancholy: LookupResult = {
  word: 'melancholy',
  senses: [
    {
      synset_id: '62100',
      pos: 'noun',
      definition: 'a humor once believed to cause sadness',
      synonyms: [{ word: 'black bile', synset_id: '62100' }],
      relations: {
        hypernyms: [{ word: 'bodily fluid', synset_id: '62054' }],
        hyponyms: [],
        similar: [],
        antonyms: [],
      },
    },
    {
      synset_id: '72858',
      pos: 'noun',
      definition: 'a feeling of thoughtful sadness',
      synonyms: [],
      relations: {
        hypernyms: [{ word: 'sadness', synset_id: '72855' }],
        hyponyms: [
          { word: 'gloom', synset_id: '72859' },
          { word: 'heavyheartedness', synset_id: '72860' },
        ],
        similar: [],
        antonyms: [],
      },
    },
  ],
}

describe('transformLookupToGraph', () => {
  it('creates a central node for the searched word', () => {
    const graph = transformLookupToGraph(melancholy)
    const central = graph.nodes.find(n => n.relationType === 'central')
    expect(central).toBeDefined()
    expect(central!.word).toBe('melancholy')
    expect(central!.val).toBeGreaterThan(1)
  })

  it('creates synonym nodes with links to central', () => {
    const graph = transformLookupToGraph(melancholy)
    const blackBile = graph.nodes.find(n => n.word === 'black bile')
    expect(blackBile).toBeDefined()
    expect(blackBile!.relationType).toBe('synonym')

    const link = graph.links.find(
      l => l.target === blackBile!.id && l.relationType === 'synonym',
    )
    expect(link).toBeDefined()
  })

  it('creates hypernym nodes with links', () => {
    const graph = transformLookupToGraph(melancholy)
    const sadness = graph.nodes.find(n => n.word === 'sadness')
    expect(sadness).toBeDefined()
    expect(sadness!.relationType).toBe('hypernym')
  })

  it('creates hyponym nodes with links', () => {
    const graph = transformLookupToGraph(melancholy)
    const gloom = graph.nodes.find(n => n.word === 'gloom')
    expect(gloom).toBeDefined()
    expect(gloom!.relationType).toBe('hyponym')
  })

  it('deduplicates nodes that appear in multiple senses', () => {
    const graph = transformLookupToGraph(melancholy)
    const words = graph.nodes.map(n => n.word)
    const unique = new Set(words)
    expect(words.length).toBe(unique.size)
  })

  it('caps nodes at maxNodes (default 80)', () => {
    const bigResult: LookupResult = {
      word: 'test',
      senses: [
        {
          synset_id: '1',
          pos: 'noun',
          definition: 'test',
          synonyms: Array.from({ length: 100 }, (_, i) => ({
            word: `syn${i}`,
            synset_id: `${i + 100}`,
          })),
          relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
        },
      ],
    }
    const graph = transformLookupToGraph(bigResult)
    expect(graph.nodes.length).toBeLessThanOrEqual(80)
  })

  it('prioritises synonyms over hyponyms when capping', () => {
    const mixedResult: LookupResult = {
      word: 'test',
      senses: [
        {
          synset_id: '1',
          pos: 'noun',
          definition: 'test',
          synonyms: Array.from({ length: 40 }, (_, i) => ({
            word: `syn${i}`,
            synset_id: `${i + 100}`,
          })),
          relations: {
            hypernyms: Array.from({ length: 20 }, (_, i) => ({
              word: `hyper${i}`,
              synset_id: `${i + 200}`,
            })),
            hyponyms: Array.from({ length: 40 }, (_, i) => ({
              word: `hypo${i}`,
              synset_id: `${i + 300}`,
            })),
            similar: [],
            antonyms: [],
          },
        },
      ],
    }
    const graph = transformLookupToGraph(mixedResult)
    const synNodes = graph.nodes.filter(n => n.relationType === 'synonym')
    expect(synNodes.length).toBe(40)
  })

  it('returns empty graph for empty senses', () => {
    const empty: LookupResult = { word: 'xyz', senses: [] }
    const graph = transformLookupToGraph(empty)
    expect(graph.nodes.length).toBe(1)
    expect(graph.links.length).toBe(0)
  })

  it('assigns order 0 to the central node', () => {
    const graph = transformLookupToGraph(melancholy)
    const central = graph.nodes.find(n => n.relationType === 'central')!
    expect(central.order).toBe(0)
  })

  it('assigns order 1 to first-order nodes', () => {
    const graph = transformLookupToGraph(melancholy)
    const firstOrder = graph.nodes.filter(n => n.relationType !== 'central')
    expect(firstOrder.length).toBeGreaterThan(0)
    for (const node of firstOrder) {
      expect(node.order).toBe(1)
    }
  })

  it('assigns order 1 to first-order links', () => {
    const graph = transformLookupToGraph(melancholy)
    for (const link of graph.links) {
      expect(link.order).toBe(1)
    }
  })

  it('filters self-references from synonyms', () => {
    const selfRef: LookupResult = {
      word: 'happy',
      senses: [
        {
          synset_id: '1',
          pos: 'adjective',
          definition: 'feeling pleasure',
          synonyms: [
            { word: 'happy', synset_id: '1' },  // self-reference
            { word: 'joyful', synset_id: '2' },
          ],
          relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
        },
      ],
    }
    const graph = transformLookupToGraph(selfRef)
    const happyNodes = graph.nodes.filter(n => n.word === 'happy')
    expect(happyNodes.length).toBe(1) // only the central node
    expect(happyNodes[0].relationType).toBe('central')
  })
})

// -- Fixtures for second-order tests --

/** Build a first-order graph: central "melancholy" with first-order nodes */
function makeFirstOrderGraph(): GraphData {
  return transformLookupToGraph(melancholy)
}

/** Lookup result for "gloom" — used as the second-order expansion */
const gloomLookup: LookupResult = {
  word: 'gloom',
  senses: [
    {
      synset_id: '72859',
      pos: 'noun',
      definition: 'a state of partial darkness',
      synonyms: [
        { word: 'darkness', synset_id: '72861' },
        { word: 'murk', synset_id: '72862' },
      ],
      relations: {
        hypernyms: [{ word: 'sadness', synset_id: '72855' }], // already in graph
        hyponyms: [{ word: 'despair', synset_id: '72870' }],
        similar: [{ word: 'bleakness', synset_id: '72880' }],
      },
    },
  ],
}

describe('mergeExpansion', () => {
  it('adds new second-order nodes with order 2 and val 1', () => {
    const base = makeFirstOrderGraph()
    const merged = mergeExpansion(base, 'gloom', gloomLookup)

    const darkness = merged.nodes.find(n => n.word === 'darkness')
    expect(darkness).toBeDefined()
    expect(darkness!.order).toBe(2)
    expect(darkness!.val).toBe(1)
  })

  it('does not duplicate existing first-order nodes', () => {
    const base = makeFirstOrderGraph()
    const merged = mergeExpansion(base, 'gloom', gloomLookup)

    // "sadness" is already a first-order hypernym — should not be duplicated
    const sadnessNodes = merged.nodes.filter(n => n.word === 'sadness')
    expect(sadnessNodes.length).toBe(1)
    // Its order should remain 1 (first-order, existing — not overwritten)
    expect(sadnessNodes[0].order).toBe(1)
  })

  it('creates cross-links to existing nodes with order 2', () => {
    const base = makeFirstOrderGraph()
    const merged = mergeExpansion(base, 'gloom', gloomLookup)

    // "sadness" exists — should get a cross-link from "gloom" with order 2
    const crossLink = merged.links.find(
      l => l.source === 'gloom' && l.target === 'sadness' && l.order === 2,
    )
    expect(crossLink).toBeDefined()
  })

  it('second-order links have order 2', () => {
    const base = makeFirstOrderGraph()
    const merged = mergeExpansion(base, 'gloom', gloomLookup)

    const secondOrderLinks = merged.links.filter(l => l.order === 2)
    expect(secondOrderLinks.length).toBeGreaterThan(0)

    // Every new link from gloom should be order 2
    const gloomLinks = merged.links.filter(
      l => l.source === 'gloom' && l.order === 2,
    )
    expect(gloomLinks.length).toBeGreaterThan(0)
  })

  it('skips the selected node itself from its own results', () => {
    // "gloom" is the selected node and also appears as the central word
    // of gloomLookup — it should not create a self-link
    const base = makeFirstOrderGraph()
    const merged = mergeExpansion(base, 'gloom', gloomLookup)

    const selfLink = merged.links.find(
      l => l.source === 'gloom' && l.target === 'gloom',
    )
    expect(selfLink).toBeUndefined()
  })

  it('caps new second-order nodes at maxSecondOrder', () => {
    const base = makeFirstOrderGraph()
    const bigLookup: LookupResult = {
      word: 'gloom',
      senses: [
        {
          synset_id: '72859',
          pos: 'noun',
          definition: 'test',
          synonyms: Array.from({ length: 50 }, (_, i) => ({
            word: `second-syn-${i}`,
            synset_id: `${i + 5000}`,
          })),
          relations: { hypernyms: [], hyponyms: [], similar: [] },
        },
      ],
    }

    const merged = mergeExpansion(base, 'gloom', bigLookup, 10)
    const secondOrderNodes = merged.nodes.filter(n => n.order === 2)
    expect(secondOrderNodes.length).toBeLessThanOrEqual(10)
  })

  it('prioritises synonyms over other relation types', () => {
    const base = makeFirstOrderGraph()
    const priorityLookup: LookupResult = {
      word: 'gloom',
      senses: [
        {
          synset_id: '72859',
          pos: 'noun',
          definition: 'test',
          synonyms: Array.from({ length: 5 }, (_, i) => ({
            word: `prio-syn-${i}`,
            synset_id: `${i + 6000}`,
          })),
          relations: {
            hypernyms: Array.from({ length: 5 }, (_, i) => ({
              word: `prio-hyper-${i}`,
              synset_id: `${i + 7000}`,
            })),
            hyponyms: [],
            similar: [],
          },
        },
      ],
    }

    // Cap at 5 — should get all synonyms, no hypernyms
    const merged = mergeExpansion(base, 'gloom', priorityLookup, 5)
    const secondOrderNodes = merged.nodes.filter(n => n.order === 2)
    const synNodes = secondOrderNodes.filter(n => n.relationType === 'synonym')
    expect(synNodes.length).toBe(5)
    const hyperNodes = secondOrderNodes.filter(
      n => n.relationType === 'hypernym',
    )
    expect(hyperNodes.length).toBe(0)
  })

  it('preserves all existing nodes and links', () => {
    const base = makeFirstOrderGraph()
    const baseNodeCount = base.nodes.length
    const baseLinkCount = base.links.length

    const merged = mergeExpansion(base, 'gloom', gloomLookup)

    // All original nodes still present
    for (const node of base.nodes) {
      expect(merged.nodes.find(n => n.id === node.id)).toBeDefined()
    }
    // At least as many links (new ones added)
    expect(merged.links.length).toBeGreaterThanOrEqual(baseLinkCount)
    expect(merged.nodes.length).toBeGreaterThanOrEqual(baseNodeCount)
  })

  it('does not mutate the existing graph', () => {
    const base = makeFirstOrderGraph()
    const originalNodeCount = base.nodes.length
    const originalLinkCount = base.links.length

    mergeExpansion(base, 'gloom', gloomLookup)

    expect(base.nodes.length).toBe(originalNodeCount)
    expect(base.links.length).toBe(originalLinkCount)
  })
})

describe('mergeExpansion, recursively', () => {
  const darknessLookup: LookupResult = {
    word: 'darkness',
    senses: [{
      synset_id: '72861',
      pos: 'noun',
      definition: 'absence of light',
      synonyms: [
        { word: 'shadow', synset_id: '72990' },
        { word: 'gloom', synset_id: '72859' }, // already joined to darkness
      ],
      relations: { hypernyms: [], hyponyms: [], similar: [] },
    }],
  }

  it('expands a second-order node into third-order nodes and links', () => {
    const second = mergeExpansion(makeFirstOrderGraph(), 'gloom', gloomLookup)
    const third = mergeExpansion(second, 'darkness', darknessLookup)

    const shadow = third.nodes.find(n => n.id === 'shadow')
    expect(shadow).toMatchObject({ order: 3, val: 1, relationType: 'synonym' })
    expect(third.links.find(l => l.source === 'darkness' && l.target === 'shadow')?.order).toBe(3)
  })

  it('does not add a second link between nodes already joined', () => {
    const second = mergeExpansion(makeFirstOrderGraph(), 'gloom', gloomLookup)
    // d3-force swaps link endpoints for node objects once the graph is fed.
    const byId = new Map(second.nodes.map(n => [n.id, n]))
    const fed: GraphData = {
      nodes: second.nodes,
      links: second.links.map(l => ({ ...l, source: byId.get(l.source)!, target: byId.get(l.target)! })) as unknown as GraphLink[],
    }
    const third = mergeExpansion(fed, 'darkness', darknessLookup)

    const ends = (l: GraphLink) => [l.source, l.target].map(e => typeof e === 'string' ? e : (e as { id: string }).id).sort().join('|')
    expect(third.links.filter(l => ends(l) === 'darkness|gloom')).toHaveLength(1)
  })

  it('leaves the graph as it is when the node is not in it', () => {
    const base = makeFirstOrderGraph()
    expect(mergeExpansion(base, 'nowhere', gloomLookup)).toBe(base)
  })
})

describe('recentreGraph', () => {
  /** melancholy → gloom (first order) → darkness, murk, … (second order) */
  function expanded(): GraphData {
    return mergeExpansion(makeFirstOrderGraph(), 'gloom', gloomLookup)
  }

  it('makes the chosen node the central node', () => {
    const g = recentreGraph(expanded(), 'gloom')
    expect(g.nodes.find(n => n.id === 'gloom')).toMatchObject({ relationType: 'central', order: 0, val: 8 })
    expect(g.nodes.filter(n => n.relationType === 'central')).toHaveLength(1)
  })

  it('turns the old centre into an ordinary node, inverting the relation that joins them', () => {
    // gloom is a hyponym of melancholy, so from gloom melancholy is a hypernym.
    const g = recentreGraph(expanded(), 'gloom')
    expect(g.nodes.find(n => n.id === 'melancholy')).toMatchObject({ relationType: 'hypernym', order: 1, val: 2 })
  })

  it('recomputes every depth from the new centre', () => {
    const g = recentreGraph(expanded(), 'gloom')
    const order = (id: string) => g.nodes.find(n => n.id === id)!.order
    expect(order('darkness')).toBe(1) // was second order
    expect(order('black bile')).toBe(2) // was first order, now via melancholy
    expect(g.nodes.find(n => n.id === 'darkness')!.val).toBe(4) // a first-order synonym
    for (const l of g.links) {
      expect(l.order).toBe(Math.max(order(l.source), order(l.target)))
    }
  })

  it('keeps every node and link, with string endpoints, and carries positions across', () => {
    const base = expanded()
    const byId = new Map(base.nodes.map(n => [n.id, n]))
    base.nodes.forEach((n, i) => Object.assign(n, { x: i, y: i * 2, z: i * 3, vx: 0.5 }))
    const fed: GraphData = {
      nodes: base.nodes,
      links: base.links.map(l => ({ ...l, source: byId.get(l.source)!, target: byId.get(l.target)! })) as unknown as GraphLink[],
    }
    const g = recentreGraph(fed, 'gloom')

    expect(g.nodes.map(n => n.id)).toEqual(base.nodes.map(n => n.id))
    expect(g.links).toHaveLength(base.links.length)
    for (const l of g.links) {
      expect(typeof l.source).toBe('string')
      expect(typeof l.target).toBe('string')
    }
    const gloom = g.nodes.find(n => n.id === 'gloom')!
    const before = byId.get('gloom')!
    expect(gloom).toMatchObject({ x: before.x, y: before.y, z: before.z, vx: 0.5 })
    expect(gloom).not.toBe(before)
  })

  it('does not mutate the input graph', () => {
    const base = expanded()
    recentreGraph(base, 'gloom')
    expect(base.nodes.find(n => n.id === 'melancholy')!.relationType).toBe('central')
    expect(base.nodes.find(n => n.id === 'gloom')!.order).toBe(1)
  })

  it('leaves the graph as it is when the node is not in it', () => {
    const base = expanded()
    expect(recentreGraph(base, 'nowhere')).toBe(base)
  })
})

describe('mergeGlimpse', () => {
  const synonyms = (word: string, n: number): LookupResult => ({
    word,
    senses: [{
      synset_id: 's', pos: 'noun', definition: 'd',
      synonyms: Array.from({ length: n }, (_, i) => ({ word: `${word}-syn-${i}`, synset_id: `${i}` })),
      relations: {
        hypernyms: [{ word: `${word}-hyper`, synset_id: 'h' }],
        hyponyms: [{ word: `${word}-hypo`, synset_id: 'o' }],
        similar: [{ word: `${word}-sim`, synset_id: 'm' }],
      },
    }],
  })

  it('adds the first 3 synonyms in full and the next 5 as ghosts, one level down', () => {
    const g = mergeGlimpse(makeFirstOrderGraph(), 'gloom', synonyms('gloom', 12))
    const added = g.nodes.filter(n => n.word.startsWith('gloom-syn-'))
    expect(added.map(n => n.word)).toEqual([0, 1, 2, 3, 4, 5, 6, 7].map(i => `gloom-syn-${i}`))
    expect(added.slice(0, 3).every(n => !n.ghost && n.order === 2)).toBe(true)
    expect(added.slice(3).every(n => n.ghost === true && n.order === 2)).toBe(true)
    const ghostLinks = g.links.filter(l => l.source === 'gloom' && String(l.target).startsWith('gloom-syn-') && l.ghost)
    expect(ghostLinks).toHaveLength(5)
  })

  it('takes synonyms only, never other relations', () => {
    const g = mergeGlimpse(makeFirstOrderGraph(), 'gloom', synonyms('gloom', 2))
    expect(g.nodes.some(n => /gloom-(hyper|hypo|sim)$/.test(n.word))).toBe(false)
  })

  it('links a synonym already on the graph without counting it', () => {
    const base = makeFirstOrderGraph()
    const result = synonyms('gloom', 8)
    result.senses[0].synonyms.unshift({ word: 'sadness', synset_id: 'x' }) // already a first-order node
    const g = mergeGlimpse(base, 'gloom', result)
    expect(g.nodes.filter(n => n.word === 'sadness')).toHaveLength(1)
    expect(g.links.some(l => l.source === 'gloom' && l.target === 'sadness' && !l.ghost)).toBe(true)
    expect(g.nodes.filter(n => n.word.startsWith('gloom-syn-'))).toHaveLength(8)
  })

  it('leaves the graph as it is when the parent is not in it', () => {
    const base = makeFirstOrderGraph()
    expect(mergeGlimpse(base, 'nowhere', synonyms('x', 3))).toBe(base)
  })
})

describe('solidify', () => {
  function glimpsed(): GraphData {
    return mergeGlimpse(makeFirstOrderGraph(), 'gloom', {
      word: 'gloom',
      senses: [{ synset_id: 's', pos: 'noun', definition: 'd', synonyms: Array.from({ length: 8 }, (_, i) => ({ word: `g${i}`, synset_id: `${i}` })), relations: { hypernyms: [], hyponyms: [], similar: [] } }],
    })
  }

  it('turns ghosts into full nodes and their links into full links', () => {
    const base = glimpsed()
    const g = solidify(base, ['g5', 'g6'])
    expect(g.nodes.find(n => n.id === 'g5')!.ghost).toBeFalsy()
    expect(g.nodes.find(n => n.id === 'g7')!.ghost).toBe(true)
    expect(g.links.find(l => l.target === 'g5')!.ghost).toBeFalsy()
    expect(g.links.find(l => l.target === 'g7')!.ghost).toBe(true)
  })

  it('gives a solidified node a fresh object carrying its position, and fresh string-ended links', () => {
    const base = glimpsed()
    const before = base.nodes.find(n => n.id === 'g5')!
    Object.assign(before, { x: 3, y: 4, z: 5 })
    const byId = new Map(base.nodes.map(n => [n.id, n]))
    const fed: GraphData = {
      nodes: base.nodes,
      links: base.links.map(l => ({ ...l, source: byId.get(l.source)!, target: byId.get(l.target)! })) as unknown as GraphLink[],
    }
    const g = solidify(fed, ['g5'])
    const after = g.nodes.find(n => n.id === 'g5')!
    expect(after).not.toBe(before)
    expect(after).toMatchObject({ x: 3, y: 4, z: 5 })
    const link = g.links.find(l => (typeof l.target === 'string' ? l.target : (l.target as { id: string }).id) === 'g5')!
    expect(link.target).toBe('g5')
    // Untouched nodes keep their objects.
    expect(g.nodes.find(n => n.id === 'g7')).toBe(byId.get('g7'))
  })

  it('ghosts stay ghosts through a re-centre', () => {
    const g = recentreGraph(glimpsed(), 'gloom')
    expect(g.nodes.find(n => n.id === 'g7')!.ghost).toBe(true)
    expect(g.nodes.find(n => n.id === 'g0')!.ghost).toBeUndefined()
    expect(g.links.find(l => l.target === 'g7')!.ghost).toBe(true)
  })

  it('returns the same graph when nothing is a ghost', () => {
    const base = makeFirstOrderGraph()
    expect(solidify(base, ['gloom'])).toBe(base)
  })
})

describe('relationReach', () => {
  it('is null when nothing is hidden', () => {
    expect(relationReach(makeFirstOrderGraph(), new Set())).toBeNull()
  })

  it('reaches only what enabled relations connect to the source', () => {
    // melancholy: synonym "black bile"; hypernym "bodily fluid"; gloom is a hyponym
    let g = makeFirstOrderGraph()
    g = mergeExpansion(g, 'gloom', gloomLookup) // gloom → darkness (synonym), …
    const reach = relationReach(g, new Set(['hyponym', 'hypernym', 'similar']))!
    expect(reach.has('melancholy')).toBe(true)
    expect(reach.has('black bile')).toBe(true)
    expect(reach.has('bodily fluid')).toBe(false)
    expect(reach.has('gloom')).toBe(false)
    expect(reach.has('darkness')).toBe(false) // a synonym, but only of a hidden hyponym
  })

  it('reaches through a re-enabled relation', () => {
    let g = makeFirstOrderGraph()
    g = mergeExpansion(g, 'gloom', gloomLookup)
    const reach = relationReach(g, new Set(['hypernym', 'similar']))!
    expect(reach.has('gloom')).toBe(true)
    expect(reach.has('darkness')).toBe(true)
  })

  it('ignores metaphor links', () => {
    const g = makeFirstOrderGraph()
    g.nodes.push({ id: 'far', word: 'far', relationType: 'metaphor', val: 1, order: 1 })
    g.links.push({ source: 'melancholy', target: 'far', relationType: 'metaphor', order: 1 })
    expect(relationReach(g, new Set(['hyponym']))!.has('far')).toBe(false)
  })
})
