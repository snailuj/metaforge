import type { ForgeTier, Rarity, RelationType } from './types'

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

/** Colour map for forge tiers — used in results panel and future forge UI. */
export const FORGE_TIER_COLOURS: Record<ForgeTier, string> = {
  legendary: '#d4af37',   // Gold — best metaphors
  complex: '#c49a6c',     // Amber — simultaneously alike and opposed
  interesting: '#6a8b6f', // Green — wild cards
  ironic: '#8b4a6f',      // Magenta — ironic contrast metaphors
  strong: '#c4956a',      // Copper — solid matches
  obvious: '#8b6f47',     // Russet — too close
  unlikely: '#6b6560',    // Slate — weak
}

export const DEFAULT_NODE_COLOUR = '#e8e0d4'
