import type { RelationType } from './types'

/** Colour map for node relation types — single source of truth for JS side.
 * CSS tokens in tokens.css define the same values for stylesheet use. */
export const NODE_COLOURS: Record<RelationType, string> = {
  central: '#d4af37',
  synonym: '#c4956a',
  hypernym: '#8b6f47',
  hyponym: '#6a8b6f',
  similar: '#7a6a8b',
}

export const DEFAULT_NODE_COLOUR = '#e8e0d4'
