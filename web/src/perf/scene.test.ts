import { describe, it, expect } from 'vitest'
import { buildScene, PILL_COUNT } from './scene'

// Rule: the same seed builds the same scene on every device.
describe('buildScene', () => {
  it('gives identical arrays for the same seed', () => {
    const a = buildScene(1, 100, 150)
    const b = buildScene(1, 100, 150)
    expect(Array.from(a.positions)).toEqual(Array.from(b.positions))
    expect(Array.from(a.edges)).toEqual(Array.from(b.edges))
    expect(a.labels).toEqual(b.labels)
    expect(a.pills).toEqual(b.pills)
  })

  it('differs between seeds', () => {
    const a = buildScene(1, 100, 150)
    const b = buildScene(2, 100, 150)
    expect(Array.from(a.positions)).not.toEqual(Array.from(b.positions))
    expect(Array.from(a.edges)).not.toEqual(Array.from(b.edges))
  })

  it('matches the requested counts', () => {
    const s = buildScene(1, 100, 150)
    expect(s.nodeCount).toBe(100)
    expect(s.positions.length).toBe(300)
    expect(s.edges.length).toBe(300)
    expect(s.labels.length).toBe(100)
    expect(s.pills.length).toBe(PILL_COUNT)
    expect(PILL_COUNT).toBe(12)
  })

  it('keeps every edge index in range and never joins a node to itself', () => {
    const s = buildScene(7, 300, 450)
    for (let e = 0; e < 450; e++) {
      const a = s.edges[2 * e]
      const b = s.edges[2 * e + 1]
      expect(a).toBeGreaterThanOrEqual(0)
      expect(a).toBeLessThan(300)
      expect(b).toBeGreaterThanOrEqual(0)
      expect(b).toBeLessThan(300)
      expect(a).not.toBe(b)
    }
  })

  it('picks distinct, in-range pill nodes', () => {
    const s = buildScene(1, 100, 150)
    expect(new Set(s.pills).size).toBe(12)
    for (const p of s.pills) {
      expect(p).toBeGreaterThanOrEqual(0)
      expect(p).toBeLessThan(100)
    }
  })

  it('has finite positions and non-empty labels of mixed length, repeating the word list for large scenes', () => {
    const s = buildScene(1, 1000, 1500)
    expect(Array.from(s.positions).every(Number.isFinite)).toBe(true)
    expect(s.labels.every(l => l.length > 0)).toBe(true)
    expect(new Set(s.labels.map(l => l.length)).size).toBeGreaterThan(3)
    expect(s.labels.length).toBe(1000)
  })

  it('caps the pill count at the node count for tiny scenes', () => {
    expect(buildScene(1, 5, 4).pills.length).toBe(5)
  })
})
