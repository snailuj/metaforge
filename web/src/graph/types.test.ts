import { describe, it, expect } from 'vitest'
import { toRarity } from './types'

describe('toRarity', () => {
  it('returns the value for valid rarity strings', () => {
    expect(toRarity('common')).toBe('common')
    expect(toRarity('unusual')).toBe('unusual')
    expect(toRarity('rare')).toBe('rare')
  })

  it('returns undefined for unknown strings', () => {
    expect(toRarity('legendary')).toBeUndefined()
    expect(toRarity('')).toBeUndefined()
  })

  it('returns undefined for undefined input', () => {
    expect(toRarity(undefined)).toBeUndefined()
  })
})
