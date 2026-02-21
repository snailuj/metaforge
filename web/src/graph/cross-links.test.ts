import { describe, it, expect } from 'vitest'
import { computeCrossLinks } from './cross-links'
import type { LookupResult, Sense } from '@/types/api'
import type { GraphLink } from './types'

/** Helper: build a minimal Sense with defaults */
function makeSense(overrides: Partial<Sense> & { synset_id: string }): Sense {
  return {
    pos: 'n',
    definition: 'test definition',
    synonyms: [],
    relations: { hypernyms: [], hyponyms: [], similar: [] },
    ...overrides,
  }
}

/** Helper: build a minimal LookupResult */
function makeResult(word: string, senses: Sense[]): LookupResult {
  return { word, senses }
}

/** Sort links deterministically for comparison */
function sortLinks(links: GraphLink[]): GraphLink[] {
  return [...links].sort((a, b) => {
    const cmp = a.source.localeCompare(b.source)
    return cmp !== 0 ? cmp : a.target.localeCompare(b.target)
  })
}

describe('computeCrossLinks', () => {
  it('returns empty array when senses are empty', () => {
    const result = makeResult('cat', [])
    const nodeIds = new Set(['cat', 'feline', 'kitty'])

    expect(computeCrossLinks(result, nodeIds)).toEqual([])
  })

  it('cross-links two synonyms from the same sense', () => {
    const result = makeResult('cat', [
      makeSense({
        synset_id: 's1',
        synonyms: [
          { word: 'feline', synset_id: 's1' },
          { word: 'kitty', synset_id: 's1' },
        ],
      }),
    ])
    const nodeIds = new Set(['cat', 'feline', 'kitty'])

    const links = computeCrossLinks(result, nodeIds)

    expect(links).toHaveLength(1)
    expect(links[0]).toMatchObject({
      relationType: 'synonym',
      order: 1,
    })
    // Should connect feline and kitty (not cat — that's the central node)
    const ends = [links[0].source, links[0].target].sort()
    expect(ends).toEqual(['feline', 'kitty'])
  })

  it('ignores synonyms not present in nodeIds', () => {
    const result = makeResult('cat', [
      makeSense({
        synset_id: 's1',
        synonyms: [
          { word: 'feline', synset_id: 's1' },
          { word: 'kitty', synset_id: 's1' },
          { word: 'moggy', synset_id: 's1' },
        ],
      }),
    ])
    // moggy is NOT in the graph
    const nodeIds = new Set(['cat', 'feline', 'kitty'])

    const links = computeCrossLinks(result, nodeIds)

    expect(links).toHaveLength(1)
    const ends = [links[0].source, links[0].target].sort()
    expect(ends).toEqual(['feline', 'kitty'])
  })

  it('does not create self-links', () => {
    const result = makeResult('cat', [
      makeSense({
        synset_id: 's1',
        synonyms: [
          { word: 'feline', synset_id: 's1' },
        ],
      }),
      makeSense({
        synset_id: 's2',
        synonyms: [
          { word: 'feline', synset_id: 's2' },
        ],
      }),
    ])
    const nodeIds = new Set(['cat', 'feline'])

    const links = computeCrossLinks(result, nodeIds)

    // feline appears in both senses but should not link to itself
    expect(links).toEqual([])
  })

  it('does not create duplicate links', () => {
    const result = makeResult('cat', [
      makeSense({
        synset_id: 's1',
        synonyms: [
          { word: 'feline', synset_id: 's1' },
          { word: 'kitty', synset_id: 's1' },
        ],
      }),
      // Second sense with same pair
      makeSense({
        synset_id: 's1',
        synonyms: [
          { word: 'feline', synset_id: 's1' },
          { word: 'kitty', synset_id: 's1' },
        ],
      }),
    ])
    const nodeIds = new Set(['cat', 'feline', 'kitty'])

    const links = computeCrossLinks(result, nodeIds)

    expect(links).toHaveLength(1)
  })

  it('cross-links nodes across senses via shared synsetId', () => {
    const result = makeResult('fast', [
      makeSense({
        synset_id: 's1',
        synonyms: [
          { word: 'quick', synset_id: 's1' },
        ],
        relations: {
          hypernyms: [{ word: 'speedy', synset_id: 's5' }],
          hyponyms: [],
          similar: [],
        },
      }),
      makeSense({
        synset_id: 's2',
        synonyms: [],
        relations: {
          hypernyms: [],
          hyponyms: [],
          similar: [{ word: 'rapid', synset_id: 's5' }],
        },
      }),
    ])
    // speedy (hypernym from s1) and rapid (similar from s2) share synset s5
    const nodeIds = new Set(['fast', 'quick', 'speedy', 'rapid'])

    const links = sortLinks(computeCrossLinks(result, nodeIds))

    // Expect: speedy ↔ rapid (shared s5)
    expect(links).toHaveLength(1)
    expect(links[0]).toMatchObject({
      relationType: 'synonym',
      order: 1,
    })
    const ends = [links[0].source, links[0].target].sort()
    expect(ends).toEqual(['rapid', 'speedy'])
  })

  it('excludes the central word from cross-links', () => {
    const result = makeResult('cat', [
      makeSense({
        synset_id: 's1',
        synonyms: [
          { word: 'cat', synset_id: 's1' },
          { word: 'feline', synset_id: 's1' },
          { word: 'kitty', synset_id: 's1' },
        ],
      }),
    ])
    const nodeIds = new Set(['cat', 'feline', 'kitty'])

    const links = computeCrossLinks(result, nodeIds)

    // Should only have feline ↔ kitty, not cat ↔ feline or cat ↔ kitty
    expect(links).toHaveLength(1)
    const ends = [links[0].source, links[0].target].sort()
    expect(ends).toEqual(['feline', 'kitty'])
  })

  it('creates multiple cross-links in a large synonym group', () => {
    const result = makeResult('colour', [
      makeSense({
        synset_id: 's1',
        synonyms: [
          { word: 'hue', synset_id: 's1' },
          { word: 'shade', synset_id: 's1' },
          { word: 'tint', synset_id: 's1' },
        ],
      }),
    ])
    const nodeIds = new Set(['colour', 'hue', 'shade', 'tint'])

    const links = sortLinks(computeCrossLinks(result, nodeIds))

    // 3 nodes form a triangle: hue↔shade, hue↔tint, shade↔tint
    expect(links).toHaveLength(3)
    const pairs = links.map(l => [l.source, l.target].sort().join('↔'))
    expect(pairs).toContain('hue↔shade')
    expect(pairs).toContain('hue↔tint')
    expect(pairs).toContain('shade↔tint')
  })

  it('handles disambiguated node IDs (word__synsetId format)', () => {
    const result = makeResult('bank', [
      makeSense({
        synset_id: 's1',
        synonyms: [
          { word: 'shore', synset_id: 's1' },
          { word: 'riverside', synset_id: 's1' },
        ],
      }),
    ])
    // Nodes use disambiguated IDs
    const nodeIds = new Set(['bank__s1', 'shore__s1', 'riverside__s1'])

    const links = computeCrossLinks(result, nodeIds)

    expect(links).toHaveLength(1)
    const ends = [links[0].source, links[0].target].sort()
    expect(ends).toEqual(['riverside__s1', 'shore__s1'])
  })

  it('produces no links when only one synonym is in the graph', () => {
    const result = makeResult('cat', [
      makeSense({
        synset_id: 's1',
        synonyms: [
          { word: 'feline', synset_id: 's1' },
          { word: 'kitty', synset_id: 's1' },
        ],
      }),
    ])
    const nodeIds = new Set(['cat', 'feline'])

    const links = computeCrossLinks(result, nodeIds)

    expect(links).toEqual([])
  })
})
