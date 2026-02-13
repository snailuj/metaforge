import type { LookupResult, RelatedWord } from '@/types/api'
import type { GraphData, GraphLink, GraphNode, Rarity, RelationType } from './types'

const DEFAULT_MAX_NODES = 80

/**
 * Transform a LookupResult from the API into GraphData for 3d-force-graph.
 *
 * - Central node = the searched word (gold, larger)
 * - Synonym/relation nodes radiate outward
 * - Deduplicate: same word across senses -> one node, first relation type wins
 * - Cap at maxNodes, prioritising: synonyms > hyponyms > hypernyms > similar
 */
export function transformLookupToGraph(
  result: LookupResult,
  maxNodes = DEFAULT_MAX_NODES,
): GraphData {
  const centralId = result.word
  const nodeMap = new Map<string, GraphNode>()
  const links: GraphLink[] = []

  // Central node — always present
  nodeMap.set(centralId, {
    id: centralId,
    word: result.word,
    relationType: 'central',
    val: 8,
    rarity: result.rarity as Rarity | undefined,
  })

  // Collect all related words by priority tier
  const tiers: { words: RelatedWord[]; type: RelationType }[] = [
    { words: [], type: 'synonym' },
    { words: [], type: 'hyponym' },
    { words: [], type: 'hypernym' },
    { words: [], type: 'similar' },
  ]

  for (const sense of result.senses) {
    tiers[0].words.push(...sense.synonyms)
    tiers[1].words.push(...sense.relations.hyponyms)
    tiers[2].words.push(...sense.relations.hypernyms)
    tiers[3].words.push(...sense.relations.similar)
  }

  // Add nodes by priority until we hit the cap
  let remaining = maxNodes - 1 // minus central node

  for (const tier of tiers) {
    if (remaining <= 0) break

    for (const rw of tier.words) {
      if (remaining <= 0) break
      if (rw.word === result.word) continue // skip self-references

      const nodeId = rw.word
      if (nodeMap.has(nodeId)) continue // deduplicate

      nodeMap.set(nodeId, {
        id: nodeId,
        word: rw.word,
        synsetId: rw.synset_id,
        relationType: tier.type,
        val: tier.type === 'synonym' ? 4 : 2,
        rarity: rw.rarity as Rarity | undefined,
      })

      links.push({
        source: centralId,
        target: nodeId,
        relationType: tier.type,
      })

      remaining--
    }
  }

  return {
    nodes: Array.from(nodeMap.values()),
    links,
  }
}
