import type { Rarity, RelationType } from './types'

/** Colour map for node relation types — used in results panel word chips. */
export const NODE_COLOURS: Record<RelationType, string> = {
  central: '#d4af37',
  synonym: '#c4956a',
  hypernym: '#8b6f47',
  hyponym: '#6a8b6f',
  similar: '#7a6a8b',
}

/** Colour map for rarity tiers — used for 3D graph nodes, edges, and filter UI. */
export const RARITY_COLOURS: Record<Rarity, string> = {
  common: '#8bb89a',
  unusual: '#c4956a',
  rare: '#a88bc4',
}

export const DEFAULT_NODE_COLOUR = '#e8e0d4'
