/** Relationship type between nodes — determines colour and edge style */
export type RelationType =
  | 'central'
  | 'synonym'
  | 'hypernym'
  | 'hyponym'
  | 'similar'
  | 'metaphor' // forest-only node or link (the metaphor forest overlay)

/** Frequency-based rarity bucket for visibility filtering */
export type Rarity = 'common' | 'unusual' | 'rare'

const RARITIES: ReadonlySet<string> = new Set<Rarity>(['common', 'unusual', 'rare'])

/** Narrow an API rarity string to the Rarity union, or undefined if unrecognised. */
export function toRarity(value?: string): Rarity | undefined {
  return value && RARITIES.has(value) ? value as Rarity : undefined
}

/** Graph depth from the central node: 0 = central, 1 = direct relation,
 *  2 = relation of a relation, and so on as the user expands outwards. */
export type GraphOrder = number

/** Forge tier — all tiers including curated vocabulary tiers */
export type ForgeTier = 'legendary' | 'complex' | 'interesting' | 'ironic' | 'strong' | 'obvious' | 'unlikely'

/** A node in the force graph */
export interface GraphNode {
  id: string            // Unique: word or word__synsetId for disambiguation
  word: string          // Display label
  synsetId?: string     // Optional synset reference for navigation
  relationType: RelationType
  val: number           // Affects node size in 3d-force-graph
  rarity?: Rarity       // Frequency bucket; defaults to 'unusual' when absent
  order: GraphOrder     // Depth from central node (0=central, 1=direct, 2+=expanded)
  ghost?: boolean       // a glimpsed word not yet opened: drawn faint, label on hover
  x?: number            // set by the force simulation; a new forest node may be seeded with one
  y?: number
  z?: number
}

/** A streamed mark that the latest snapshot does not hold yet: pending (unjudged),
 *  kept (judged, not yet in a snapshot) or fading (no path uses it any more). */
export type StreamMarkStatus = 'pending' | 'kept' | 'fading'

/** What a metaphor-forest link carries: the shared qualities that join its two
 *  words, and the kept paths (by endpoint id) that run along it. */
export interface MetaphorLinkInfo {
  grounds: string[]
  pathKeys: string[]
  forestSource: string  // forest ids, stable across recompositions
  forestTarget: string
  stream?: StreamMarkStatus  // set only on streamed marks
  fadeUntil?: number         // performance.now() time a fading mark is gone
}

/** A link (edge) in the force graph */
export interface GraphLink {
  source: string        // GraphNode.id
  target: string        // GraphNode.id
  relationType: RelationType
  order: GraphOrder     // Depth from central node (0=central, 1=direct, 2+=expanded)
  metaphor?: MetaphorLinkInfo // set only on metaphor-forest links
  ghost?: boolean       // leads to a ghost node
}

/** Complete graph data, ready for 3d-force-graph */
export interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
}
