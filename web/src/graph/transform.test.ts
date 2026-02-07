import { describe, it, expect } from 'vitest'
import { transformLookupToGraph } from './transform'
import type { LookupResult } from '@/types/api'

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
})
