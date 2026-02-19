/** Relationship type between nodes — determines colour and edge style */
export type RelationType =
  | 'central'
  | 'synonym'
  | 'hypernym'
  | 'hyponym'
  | 'similar'

/** Frequency-based rarity bucket for visibility filtering */
export type Rarity = 'common' | 'unusual' | 'rare'

const RARITIES: ReadonlySet<string> = new Set<Rarity>(['common', 'unusual', 'rare'])

/** Narrow an API rarity string to the Rarity union, or undefined if unrecognised. */
export function toRarity(value?: string): Rarity | undefined {
  return value && RARITIES.has(value) ? value as Rarity : undefined
}

/** Graph depth: 1 = direct relation to central, 2 = relation of a relation */
export type GraphOrder = 1 | 2

/** A node in the force graph */
export interface GraphNode {
  id: string            // Unique: word or word__synsetId for disambiguation
  word: string          // Display label
  synsetId?: string     // Optional synset reference for navigation
  relationType: RelationType
  val: number           // Affects node size in 3d-force-graph
  rarity?: Rarity       // Frequency bucket; defaults to 'unusual' when absent
  order?: GraphOrder    // Depth from central node; defaults to 1
}

/** A link (edge) in the force graph */
export interface GraphLink {
  source: string        // GraphNode.id
  target: string        // GraphNode.id
  relationType: RelationType
  order?: GraphOrder    // Depth from central node; defaults to 1
}

/** Complete graph data, ready for 3d-force-graph */
export interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
}
