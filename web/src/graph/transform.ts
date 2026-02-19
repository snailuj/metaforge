import type { LookupResult, RelatedWord } from '@/types/api'
import type { GraphData, GraphLink, GraphNode, RelationType } from './types'
import { toRarity } from './types'

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
    rarity: toRarity(result.rarity),
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
        rarity: toRarity(rw.rarity),
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

const DEFAULT_MAX_SECOND_ORDER = 30

/**
 * Merge second-order lookup results into an existing graph.
 *
 * When a user selects a first-order node, we fetch that node's thesaurus
 * data and merge it as second-order nodes/links into the existing graph.
 *
 * - Existing nodes are NOT duplicated — only a cross-link is added
 * - New nodes get `order: 2` and `val: 1` (small)
 * - The selected node itself is skipped (already in graph)
 * - Priority: synonyms > hyponyms > hypernyms > similar
 * - New second-order nodes are capped at maxSecondOrder
 */
export function mergeSecondOrderGraph(
  existingGraph: GraphData,
  selectedNodeId: string,
  secondaryResult: LookupResult,
  maxSecondOrder = DEFAULT_MAX_SECOND_ORDER,
): GraphData {
  const existingNodeIds = new Set(existingGraph.nodes.map(n => n.id))
  const newNodes: GraphNode[] = []
  const newLinks: GraphLink[] = []

  // Collect related words by priority tier (same order as first-order transform)
  const tiers: { words: RelatedWord[]; type: RelationType }[] = [
    { words: [], type: 'synonym' },
    { words: [], type: 'hyponym' },
    { words: [], type: 'hypernym' },
    { words: [], type: 'similar' },
  ]

  for (const sense of secondaryResult.senses) {
    tiers[0].words.push(...sense.synonyms)
    tiers[1].words.push(...sense.relations.hyponyms)
    tiers[2].words.push(...sense.relations.hypernyms)
    tiers[3].words.push(...sense.relations.similar)
  }

  let remaining = maxSecondOrder
  const addedNodeIds = new Set<string>()

  for (const tier of tiers) {
    if (remaining <= 0) break

    for (const rw of tier.words) {
      if (remaining <= 0) break

      const nodeId = rw.word

      // Skip the selected node itself (already in graph as first-order)
      if (nodeId === selectedNodeId) continue

      // Skip if we already added this as a second-order node in this merge
      if (addedNodeIds.has(nodeId)) continue

      if (existingNodeIds.has(nodeId)) {
        // Node exists — add cross-link only (no duplicate node)
        newLinks.push({
          source: selectedNodeId,
          target: nodeId,
          relationType: tier.type,
          order: 2,
        })
        addedNodeIds.add(nodeId)
      } else {
        // New node — create as second-order
        newNodes.push({
          id: nodeId,
          word: rw.word,
          synsetId: rw.synset_id,
          relationType: tier.type,
          val: 1,
          rarity: toRarity(rw.rarity),
          order: 2,
        })

        newLinks.push({
          source: selectedNodeId,
          target: nodeId,
          relationType: tier.type,
          order: 2,
        })

        addedNodeIds.add(nodeId)
        remaining--
      }
    }
  }

  return {
    nodes: [...existingGraph.nodes, ...newNodes],
    links: [...existingGraph.links, ...newLinks],
  }
}

/**
 * Resolve a link endpoint to its node ID string.
 * d3-force mutates source/target from strings to full node objects at runtime,
 * so we must handle both representations.
 */
function resolveEndpoint(endpoint: unknown): string {
  if (typeof endpoint === 'string') return endpoint
  return (endpoint as GraphNode).id
}

/**
 * Strip all second-order nodes and their links from a graph.
 * Used when switching selection to clear previous second-order expansion.
 */
export function stripSecondOrderNodes(graph: GraphData): GraphData {
  const secondOrderIds = new Set(
    graph.nodes.filter(n => n.order === 2).map(n => n.id),
  )

  return {
    nodes: graph.nodes.filter(n => n.order !== 2),
    links: graph.links.filter(
      l =>
        l.order !== 2 &&
        !secondOrderIds.has(resolveEndpoint(l.source)) &&
        !secondOrderIds.has(resolveEndpoint(l.target)),
    ),
  }
}
