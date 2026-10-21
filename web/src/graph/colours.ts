import type { ForgeTier, Rarity, RelationType } from './types'

/** Colour map for node relation types — used in results panel word chips. */
export const NODE_COLOURS: Record<RelationType, string> = {
  central: '#d4af37',
  synonym: '#c4956a',
  hypernym: '#8b6f47',
  hyponym: '#6a8b6f',
  similar: '#7a6a8b',
  metaphor: '#5cc8e0',
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

/**
 * Metaphor forest palette for the WebGL scene (mirrored as --colour-forest-*
 * tokens in styles/tokens.css for the panel). Cosmic theme: the source keeps the
 * central gold, branches are cold aether cyan, endpoints are white-hot stars at
 * the branch tips, hops are the dimmer teal joints between them.
 */
export const FOREST_COLOURS = {
  branch: '#5cc8e0',
  spark: '#e8fbff',
  endpoint: '#dff9ff',
  hop: '#3e9db3',
  live: '#d4af37',
} as const

/** A hex colour at the given alpha, as rgba(). The graph library multiplies
 *  this alpha into the material opacity, which is how marks are dimmed. */
export function withAlpha(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}
