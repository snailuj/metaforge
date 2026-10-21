/** Mirrors Go thesaurus.RelatedWord */
export interface RelatedWord {
  word: string
  synset_id: string
  rarity?: string
}

/** Mirrors Go thesaurus.Relations */
export interface Relations {
  hypernyms: RelatedWord[]
  hyponyms: RelatedWord[]
  similar: RelatedWord[]
  antonyms: RelatedWord[]
}

/** Mirrors Go thesaurus.Sense */
export interface Sense {
  synset_id: string
  pos: string
  definition: string
  register?: string
  connotation?: string
  usage_example?: string
  synonyms: RelatedWord[]
  relations: Relations
  collocations?: RelatedWord[]
}

/** Mirrors Go thesaurus.LookupResult */
export interface LookupResult {
  word: string
  senses: Sense[]
  rarity?: string
}

/** Mirrors GET /forge/forest (docs/plans/2026-10-21-metaphor-forest.md, API contract). */
export type ForestRole = 'source' | 'hop' | 'endpoint'

export interface ForestNode {
  id: string   // normalised word; matches the browse graph's bare-word ids
  word: string
  role: ForestRole
}

/** Directed source outward. A shared edge can carry more than one ground. */
export interface ForestEdge {
  source: string
  target: string
  grounds: string[]
}

/** One kept path. `path[i]` to `path[i+1]` is joined by `grounds[i]`. */
export interface ForestEndpoint {
  id: string
  path: string[]
  grounds: string[]
  line: string
  score: number
  reason: string
}

export interface ForestStats {
  generated: number
  kept: number
  // Open-ended: the server adds rejection reasons over time (e.g. `duplicate`).
  rejected: Record<string, number>
}

export interface ForestResponse {
  source: string
  max_hops: number
  model: string
  nodes: ForestNode[]
  edges: ForestEdge[]
  endpoints: ForestEndpoint[] // score descending, then path length ascending
  stats: ForestStats
}
