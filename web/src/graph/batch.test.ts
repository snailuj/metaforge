import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { arrivalBatch } from './batch'

describe('arrivalBatch', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  // Rule: arrivals within the window of the first one reach the graph in one flush.
  it('flushes every arrival inside the window once, at the window end', () => {
    const flush = vi.fn()
    const batch = arrivalBatch(300, flush)
    batch.arrive(true)
    vi.advanceTimersByTime(100)
    batch.arrive(true)
    vi.advanceTimersByTime(150)
    batch.arrive(true)
    expect(flush).not.toHaveBeenCalled()
    vi.advanceTimersByTime(50)
    expect(flush).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(1000)
    expect(flush).toHaveBeenCalledTimes(1)
  })

  // Rule: the window never delays the last arrival: when nothing more is expected it flushes at once.
  it('flushes at once when no more arrivals are expected, taking any waiting ones with it', () => {
    const flush = vi.fn()
    const batch = arrivalBatch(300, flush)
    batch.arrive(true)
    batch.arrive(false)
    expect(flush).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(1000)
    expect(flush).toHaveBeenCalledTimes(1)
  })

  // Rule: a cancelled batch never flushes (an immediate graph update already carried it).
  it('cancel drops the pending flush', () => {
    const flush = vi.fn()
    const batch = arrivalBatch(300, flush)
    batch.arrive(true)
    expect(batch.pending).toBe(true)
    batch.cancel()
    expect(batch.pending).toBe(false)
    vi.advanceTimersByTime(1000)
    expect(flush).not.toHaveBeenCalled()
  })
})
