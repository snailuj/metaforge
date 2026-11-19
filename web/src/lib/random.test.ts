import { describe, it, expect } from 'vitest'
import { mulberry32 } from './random'

// Rule: a seed fixes the whole sequence, and every value lies in [0, 1).
describe('mulberry32', () => {
  it('gives the same sequence for the same seed', () => {
    const a = mulberry32(42)
    const b = mulberry32(42)
    const first = Array.from({ length: 50 }, () => a())
    const second = Array.from({ length: 50 }, () => b())
    expect(second).toEqual(first)
    expect(new Set(first).size).toBeGreaterThan(40)
  })

  it('differs between seeds', () => {
    expect(mulberry32(1)()).not.toBe(mulberry32(2)())
  })

  it('keeps every value in [0, 1)', () => {
    const rand = mulberry32(0x5eed)
    for (let i = 0; i < 10000; i++) {
      const v = rand()
      expect(v).toBeGreaterThanOrEqual(0)
      expect(v).toBeLessThan(1)
    }
  })
})
