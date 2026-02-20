import { describe, it, expect } from 'vitest'
import { NODE_COLOURS, RARITY_COLOURS, DEFAULT_NODE_COLOUR, FORGE_TIER_COLOURS } from './colours'

describe('colours', () => {
  it('exports NODE_COLOURS for each relation type', () => {
    expect(NODE_COLOURS.central).toBe('#d4af37')
    expect(NODE_COLOURS.synonym).toBeDefined()
    expect(NODE_COLOURS.hypernym).toBeDefined()
    expect(NODE_COLOURS.hyponym).toBeDefined()
    expect(NODE_COLOURS.similar).toBeDefined()
  })

  it('exports RARITY_COLOURS for each rarity tier', () => {
    expect(RARITY_COLOURS.common).toBe('#8bb89a')
    expect(RARITY_COLOURS.unusual).toBe('#c4956a')
    expect(RARITY_COLOURS.rare).toBe('#a88bc4')
  })

  it('exports DEFAULT_NODE_COLOUR', () => {
    expect(DEFAULT_NODE_COLOUR).toBe('#e8e0d4')
  })
})

describe('FORGE_TIER_COLOURS', () => {
  it('includes ironic tier', () => {
    expect(FORGE_TIER_COLOURS.ironic).toBeDefined()
  })

  it('includes complex tier', () => {
    expect(FORGE_TIER_COLOURS.complex).toBeDefined()
  })

  it('includes all seven tiers', () => {
    const tiers = ['legendary', 'complex', 'interesting', 'ironic', 'strong', 'obvious', 'unlikely'] as const
    for (const tier of tiers) {
      expect(FORGE_TIER_COLOURS[tier]).toBeDefined()
    }
  })
})
