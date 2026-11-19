import { describe, it, expect } from 'vitest'
import { summarise, createFrameTimer } from './frame-timer'

// Rule: the timer reports the same median and 95th percentile as a
// hand-computed list of frame times.

// 20 frame intervals, deliberately unsorted. Sorted they are
// 10,11,12,13,14,15,16,16.5,16.6,16.7,16.8,17,17.5,18,19,20,22,25,30,40.
// Median (n=20) is the mean of ranks 10 and 11: (16.7 + 16.8) / 2 = 16.75.
// p95 by nearest rank is index ceil(0.95 * 20) - 1 = 18, so 30.
// Strictly over 16.7: 16.8,17,17.5,18,19,20,22,25,30,40 = 10 of 20.
const TWENTY = [16.5, 40, 12, 17, 10, 25, 16.7, 14, 18, 11, 30, 16, 13, 19, 16.8, 22, 15, 20, 16.6, 17.5]

describe('summarise', () => {
  it('matches a hand-computed list of twenty frame times', () => {
    expect(summarise(TWENTY, 16.7)).toEqual({ count: 20, median: 16.75, p95: 30, overBudgetShare: 0.5 })
  })

  it('takes the middle value for an odd count', () => {
    // Sorted 3,5,9,12,20: median 9; p95 index ceil(4.75) - 1 = 4.
    const s = summarise([12, 3, 20, 5, 9], 100)
    expect(s.median).toBe(9)
    expect(s.p95).toBe(20)
  })

  it('averages the two middle values for an even count', () => {
    const s = summarise([4, 1, 3, 2], 100)
    expect(s.median).toBe(2.5)
    expect(s.p95).toBe(4)
  })

  it('sorts a copy and leaves the input order alone', () => {
    const input = [30, 10, 20]
    const before = [...input]
    const s = summarise(input, 100)
    expect(input).toEqual(before)
    expect(s.median).toBe(20)
  })

  it('returns zeros, not NaN, for an empty list', () => {
    expect(summarise([], 16.7)).toEqual({ count: 0, median: 0, p95: 0, overBudgetShare: 0 })
  })

  it('does not count a sample equal to the budget as over it', () => {
    expect(summarise([16.7, 16.7, 16.7, 16.7], 16.7).overBudgetShare).toBe(0)
    expect(summarise([16.7, 16.7, 16.7, 16.8], 16.7).overBudgetShare).toBe(0.25)
  })

  it('reports a single sample as its own median and p95', () => {
    expect(summarise([7], 16.7)).toEqual({ count: 1, median: 7, p95: 7, overBudgetShare: 0 })
  })
})

describe('createFrameTimer', () => {
  it('returns samples in the order recorded', () => {
    const t = createFrameTimer(5)
    ;[1, 2, 3].forEach(v => t.record(v))
    expect(t.samples()).toEqual([1, 2, 3])
  })

  it('overwrites the oldest samples once capacity is exceeded', () => {
    const t = createFrameTimer(3)
    ;[1, 2, 3, 4, 5].forEach(v => t.record(v))
    expect(t.samples()).toEqual([3, 4, 5])
  })

  it('summarises the same as a plain list after wrapping', () => {
    const t = createFrameTimer(20)
    for (let i = 0; i < 7; i++) t.record(999) // overwritten below
    TWENTY.forEach(v => t.record(v))
    expect(summarise(t.samples(), 16.7)).toEqual(summarise(TWENTY, 16.7))
  })

  it('forgets everything on reset', () => {
    const t = createFrameTimer(3)
    ;[1, 2, 3, 4].forEach(v => t.record(v))
    t.reset()
    expect(t.samples()).toEqual([])
    t.record(9)
    expect(t.samples()).toEqual([9])
  })
})
