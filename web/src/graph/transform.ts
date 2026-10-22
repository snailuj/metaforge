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
    order: 0,
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
        order: 1,
      })

      links.push({
        source: centralId,
        target: nodeId,
        relationType: tier.type,
        order: 1,
      })

      remaining--
    }
  }

  return {
    nodes: Array.from(nodeMap.values()),
    links,
  }
}

const DEFAULT_MAX_EXPANSION = 30

/** Node size by depth from the central node: the centre is largest, direct
 *  synonyms next, everything further out small. */
function valFor(order: number, relationType: RelationType, ghost = false): number {
  if (ghost) return 0.5
  if (order === 0) return 8
  if (order === 1) return relationType === 'synonym' ? 4 : 2
  return 1
}

/**
 * Resolve a link endpoint to its node ID string.
 * d3-force mutates source/target from strings to full node objects at runtime,
 * so we must handle both representations.
 */
export function resolveEndpoint(endpoint: unknown): string {
  if (typeof endpoint === 'string') return endpoint
  return (endpoint as GraphNode).id
}

function pairKey(a: string, b: string): string {
  return a < b ? JSON.stringify([a, b]) : JSON.stringify([b, a])
}

/**
 * Expand one node of an existing graph with that node's own lookup result.
 *
 * Expansion is recursive: any node can be expanded, and its new neighbours
 * sit one level deeper than it (`order + 1`).
 *
 * - Existing nodes are NOT duplicated — only a link is added, and only when
 *   the pair is not already joined
 * - New nodes get `order: parent.order + 1` and a small `val`
 * - Priority: synonyms > hyponyms > hypernyms > similar
 * - New nodes are capped at maxNew, so one click adds a bounded amount
 */
export function mergeExpansion(
  existingGraph: GraphData,
  selectedNodeId: string,
  secondaryResult: LookupResult,
  maxNew = DEFAULT_MAX_EXPANSION,
): GraphData {
  const parent = existingGraph.nodes.find(n => n.id === selectedNodeId)
  if (!parent) return existingGraph
  const order = parent.order + 1

  const existingNodeIds = new Set(existingGraph.nodes.map(n => n.id))
  const joined = new Set(existingGraph.links.map(l => pairKey(resolveEndpoint(l.source), resolveEndpoint(l.target))))
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

  let remaining = maxNew

  for (const tier of tiers) {
    if (remaining <= 0) break

    for (const rw of tier.words) {
      if (remaining <= 0) break

      const nodeId = rw.word
      if (nodeId === selectedNodeId) continue
      const key = pairKey(selectedNodeId, nodeId)
      if (joined.has(key)) continue
      joined.add(key)

      if (!existingNodeIds.has(nodeId)) {
        newNodes.push({
          id: nodeId,
          word: rw.word,
          synsetId: rw.synset_id,
          relationType: tier.type,
          val: valFor(order, tier.type),
          rarity: toRarity(rw.rarity),
          order,
        })
        existingNodeIds.add(nodeId)
        remaining--
      }

      newLinks.push({
        source: selectedNodeId,
        target: nodeId,
        relationType: tier.type,
        order,
      })
    }
  }

  return {
    nodes: [...existingGraph.nodes, ...newNodes],
    links: [...existingGraph.links, ...newLinks],
  }
}

/** The relation a link names, read from its target's end back to its source. */
const INVERSE: Partial<Record<RelationType, RelationType>> = { hyponym: 'hypernym', hypernym: 'hyponym' }

/** Simulation state d3-force writes onto a node; carried across so a
 *  replaced node stays exactly where it was. */
const SIM_FIELDS = ['x', 'y', 'z', 'vx', 'vy', 'vz', 'fx', 'fy', 'fz'] as const

/** A fresh node object with the node's data and simulation position, so the
 *  renderer rebuilds its label. Library bookkeeping (`__threeObj`, …) is left behind. */
function copyNode(n: GraphNode, changes: Partial<GraphNode>): GraphNode {
  const node: GraphNode = {
    id: n.id, word: n.word, synsetId: n.synsetId, relationType: n.relationType,
    val: n.val, rarity: n.rarity, order: n.order, ...changes,
  }
  if (n.ghost && !('ghost' in changes)) node.ghost = true
  if (node.ghost === false) delete node.ghost
  for (const f of SIM_FIELDS) {
    const v = (n as unknown as Record<string, unknown>)[f]
    if (v !== undefined) (node as unknown as Record<string, unknown>)[f] = v
  }
  return node
}

/**
 * Re-centre a graph on one of its nodes, keeping every node and link.
 *
 * The chosen node becomes the central node; depths, sizes and link orders are
 * recomputed breadth-first from it, and the old centre takes the relation of
 * the link that now reaches it. Nodes come back as fresh objects (so the
 * renderer rebuilds their labels) carrying their simulation positions, and
 * links come back with string endpoints so d3 resolves them to those objects.
 */
export function recentreGraph(graph: GraphData, centreId: string): GraphData {
  if (!graph.nodes.some(n => n.id === centreId)) return graph

  const adjacency = new Map<string, { other: string; relation: RelationType }[]>()
  const edge = (from: string, other: string, relation: RelationType) => {
    const list = adjacency.get(from) ?? []
    list.push({ other, relation })
    adjacency.set(from, list)
  }
  for (const l of graph.links) {
    const s = resolveEndpoint(l.source)
    const t = resolveEndpoint(l.target)
    edge(s, t, l.relationType)
    edge(t, s, INVERSE[l.relationType] ?? l.relationType)
  }

  const depth = new Map<string, number>([[centreId, 0]])
  const reachedBy = new Map<string, RelationType>()
  const queue = [centreId]
  for (let i = 0; i < queue.length; i++) {
    const id = queue[i]
    for (const { other, relation } of adjacency.get(id) ?? []) {
      if (depth.has(other)) continue
      depth.set(other, depth.get(id)! + 1)
      reachedBy.set(other, relation)
      queue.push(other)
    }
  }

  const nodes = graph.nodes.map(n => {
    const order = depth.get(n.id) ?? n.order
    const relationType: RelationType = n.id === centreId
      ? 'central'
      : n.relationType === 'central' ? reachedBy.get(n.id) ?? 'synonym' : n.relationType
    return copyNode(n, { relationType, order, val: valFor(order, relationType, n.ghost) })
  })
  const orderOf = new Map(nodes.map(n => [n.id, n.order]))
  const links = graph.links.map(l => {
    const source = resolveEndpoint(l.source)
    const target = resolveEndpoint(l.target)
    return { ...l, source, target, order: Math.max(orderOf.get(source) ?? 0, orderOf.get(target) ?? 0) }
  })
  return { nodes, links }
}

const GLIMPSE_FULL = 3
const GLIMPSE_GHOSTS = 5

/**
 * A glimpse of one node's own synonyms, one level below it: the first `full`
 * new synonyms are full nodes, the next `ghosts` are ghosts (drawn faint, label
 * on hover). Synonyms already on the graph are linked without counting. Other
 * relations never glimpse: they appear when the node itself is expanded.
 */
export function mergeGlimpse(
  graph: GraphData,
  parentId: string,
  result: LookupResult,
  { full = GLIMPSE_FULL, ghosts = GLIMPSE_GHOSTS }: { full?: number; ghosts?: number } = {},
): GraphData {
  const parent = graph.nodes.find(n => n.id === parentId)
  if (!parent) return graph
  const order = parent.order + 1
  const existing = new Set(graph.nodes.map(n => n.id))
  const joined = new Set(graph.links.map(l => pairKey(resolveEndpoint(l.source), resolveEndpoint(l.target))))
  const nodes: GraphNode[] = []
  const links: GraphLink[] = []

  for (const rw of result.senses.flatMap(s => s.synonyms)) {
    if (nodes.length >= full + ghosts) break
    if (rw.word === parentId) continue
    const key = pairKey(parentId, rw.word)
    if (joined.has(key)) continue
    joined.add(key)
    if (existing.has(rw.word)) {
      links.push({ source: parentId, target: rw.word, relationType: 'synonym', order })
      continue
    }
    const ghost = nodes.length >= full
    const node: GraphNode = {
      id: rw.word, word: rw.word, synsetId: rw.synset_id, relationType: 'synonym',
      val: valFor(order, 'synonym', ghost), rarity: toRarity(rw.rarity), order,
    }
    const link: GraphLink = { source: parentId, target: rw.word, relationType: 'synonym', order }
    if (ghost) {
      node.ghost = true
      link.ghost = true
    }
    existing.add(rw.word)
    nodes.push(node)
    links.push(link)
  }
  return { nodes: [...graph.nodes, ...nodes], links: [...graph.links, ...links] }
}

/**
 * Make ghosts full. Each changed node is a fresh object (its label must be
 * rebuilt), so links touching one are rebuilt with string endpoints that d3
 * resolves to it; a link stays a ghost while either end is.
 */
export function solidify(graph: GraphData, ids: Iterable<string>): GraphData {
  const wanted = new Set(ids)
  const changed = new Set(graph.nodes.filter(n => n.ghost && wanted.has(n.id)).map(n => n.id))
  if (changed.size === 0) return graph
  const nodes = graph.nodes.map(n => changed.has(n.id) ? copyNode(n, { ghost: false, val: valFor(n.order, n.relationType) }) : n)
  const ghostIds = new Set(nodes.filter(n => n.ghost).map(n => n.id))
  const links = graph.links.map(l => {
    const source = resolveEndpoint(l.source)
    const target = resolveEndpoint(l.target)
    if (!changed.has(source) && !changed.has(target)) return l
    const link: GraphLink = { ...l, source, target }
    if (ghostIds.has(source) || ghostIds.has(target)) link.ghost = true
    else delete link.ghost
    return link
  })
  return { nodes, links }
}

/**
 * The nodes the source reaches through links of shown relations, or null when
 * every relation is shown. A synonym of a hidden hyponym stays hidden with it.
 * Metaphor-forest links are not thesaurus relations and never carry reach.
 */
export function relationReach(graph: GraphData, hidden: ReadonlySet<RelationType>): Set<string> | null {
  if (hidden.size === 0) return null
  const adjacency = new Map<string, string[]>()
  for (const l of graph.links) {
    if (l.metaphor || l.relationType === 'metaphor' || hidden.has(l.relationType)) continue
    const s = resolveEndpoint(l.source)
    const t = resolveEndpoint(l.target)
    for (const [a, b] of [[s, t], [t, s]]) {
      const list = adjacency.get(a)
      if (list) list.push(b)
      else adjacency.set(a, [b])
    }
  }
  const queue = graph.nodes.filter(n => n.relationType === 'central').map(n => n.id)
  const reached = new Set(queue)
  for (let i = 0; i < queue.length; i++) {
    for (const next of adjacency.get(queue[i]) ?? []) {
      if (reached.has(next)) continue
      reached.add(next)
      queue.push(next)
    }
  }
  return reached
}
