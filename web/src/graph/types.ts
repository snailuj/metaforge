/** Relationship type between nodes — determines colour and edge style */
export type RelationType =
  | 'central'
  | 'synonym'
  | 'hypernym'
  | 'hyponym'
  | 'similar'

/** A node in the force graph */
export interface GraphNode {
  id: string            // Unique: word or word__synsetId for disambiguation
  word: string          // Display label
  synsetId?: string     // Optional synset reference for navigation
  relationType: RelationType
  val: number           // Affects node size in 3d-force-graph
  rarity?: string       // 'common' | 'unusual' | 'rare'
}

/** A link (edge) in the force graph */
export interface GraphLink {
  source: string        // GraphNode.id
  target: string        // GraphNode.id
  relationType: RelationType
}

/** Complete graph data, ready for 3d-force-graph */
export interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
}
