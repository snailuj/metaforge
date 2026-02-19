import { describe, it, expect } from 'vitest'
import {
  transformLookupToGraph,
  mergeSecondOrderGraph,
  stripSecondOrderNodes,
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
          relations: { hypernyms: [], hyponyms: [], similar: [] },
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
          relations: { hypernyms: [], hyponyms: [], similar: [] },
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

describe('mergeSecondOrderGraph', () => {
  it('adds new second-order nodes with order 2 and val 1', () => {
    const base = makeFirstOrderGraph()
    const merged = mergeSecondOrderGraph(base, 'gloom', gloomLookup)

    const darkness = merged.nodes.find(n => n.word === 'darkness')
    expect(darkness).toBeDefined()
    expect(darkness!.order).toBe(2)
    expect(darkness!.val).toBe(1)
  })

  it('does not duplicate existing first-order nodes', () => {
    const base = makeFirstOrderGraph()
    const merged = mergeSecondOrderGraph(base, 'gloom', gloomLookup)

    // "sadness" is already a first-order hypernym — should not be duplicated
    const sadnessNodes = merged.nodes.filter(n => n.word === 'sadness')
    expect(sadnessNodes.length).toBe(1)
    // Its order should remain undefined (first-order, existing)
    expect(sadnessNodes[0].order).toBeUndefined()
  })

  it('creates cross-links to existing nodes with order 2', () => {
    const base = makeFirstOrderGraph()
    const merged = mergeSecondOrderGraph(base, 'gloom', gloomLookup)

    // "sadness" exists — should get a cross-link from "gloom" with order 2
    const crossLink = merged.links.find(
      l => l.source === 'gloom' && l.target === 'sadness' && l.order === 2,
    )
    expect(crossLink).toBeDefined()
  })

  it('second-order links have order 2', () => {
    const base = makeFirstOrderGraph()
    const merged = mergeSecondOrderGraph(base, 'gloom', gloomLookup)

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
    const merged = mergeSecondOrderGraph(base, 'gloom', gloomLookup)

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

    const merged = mergeSecondOrderGraph(base, 'gloom', bigLookup, 10)
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
    const merged = mergeSecondOrderGraph(base, 'gloom', priorityLookup, 5)
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

    const merged = mergeSecondOrderGraph(base, 'gloom', gloomLookup)

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

    mergeSecondOrderGraph(base, 'gloom', gloomLookup)

    expect(base.nodes.length).toBe(originalNodeCount)
    expect(base.links.length).toBe(originalLinkCount)
  })
})

describe('stripSecondOrderNodes', () => {
  it('removes all order-2 nodes', () => {
    const base = makeFirstOrderGraph()
    const merged = mergeSecondOrderGraph(base, 'gloom', gloomLookup)

    // Verify there are second-order nodes to strip
    expect(merged.nodes.some(n => n.order === 2)).toBe(true)

    const stripped = stripSecondOrderNodes(merged)
    const remaining = stripped.nodes.filter(n => n.order === 2)
    expect(remaining.length).toBe(0)
  })

  it('removes links connected to order-2 nodes', () => {
    const base = makeFirstOrderGraph()
    const merged = mergeSecondOrderGraph(base, 'gloom', gloomLookup)

    const stripped = stripSecondOrderNodes(merged)

    // No link should reference a node that was removed
    const nodeIds = new Set(stripped.nodes.map(n => n.id))
    for (const link of stripped.links) {
      expect(nodeIds.has(link.source as string)).toBe(true)
      expect(nodeIds.has(link.target as string)).toBe(true)
    }
  })

  it('removes order-2 cross-links even between first-order nodes', () => {
    const base = makeFirstOrderGraph()
    const merged = mergeSecondOrderGraph(base, 'gloom', gloomLookup)

    const stripped = stripSecondOrderNodes(merged)

    // All order-2 links should be gone
    const order2Links = stripped.links.filter(l => l.order === 2)
    expect(order2Links.length).toBe(0)
  })

  it('preserves all first-order nodes and links', () => {
    const base = makeFirstOrderGraph()
    const merged = mergeSecondOrderGraph(base, 'gloom', gloomLookup)

    const stripped = stripSecondOrderNodes(merged)

    // All original first-order nodes should remain
    for (const node of base.nodes) {
      expect(stripped.nodes.find(n => n.id === node.id)).toBeDefined()
    }

    // All original links (which have no order) should remain
    for (const link of base.links) {
      expect(
        stripped.links.find(
          l =>
            l.source === link.source &&
            l.target === link.target &&
            l.relationType === link.relationType,
        ),
      ).toBeDefined()
    }
  })

  it('handles d3-force mutated links where source/target are objects', () => {
    const base = makeFirstOrderGraph()
    const merged = mergeSecondOrderGraph(base, 'gloom', gloomLookup)

    // Simulate d3-force mutation: replace string IDs with node objects
    const nodeById = new Map(merged.nodes.map(n => [n.id, n]))
    const mutated: GraphData = {
      nodes: merged.nodes,
      links: merged.links.map(l => ({
        ...l,
        source: nodeById.get(l.source as string) ?? l.source,
        target: nodeById.get(l.target as string) ?? l.target,
      })) as GraphLink[],
    }

    const stripped = stripSecondOrderNodes(mutated)

    // No order-2 nodes should remain
    expect(stripped.nodes.filter(n => n.order === 2).length).toBe(0)
    // No order-2 links should remain
    expect(stripped.links.filter(l => l.order === 2).length).toBe(0)
  })

  it('does not mutate the input graph', () => {
    const base = makeFirstOrderGraph()
    const merged = mergeSecondOrderGraph(base, 'gloom', gloomLookup)
    const nodeCount = merged.nodes.length
    const linkCount = merged.links.length

    stripSecondOrderNodes(merged)

    expect(merged.nodes.length).toBe(nodeCount)
    expect(merged.links.length).toBe(linkCount)
  })
})
