// Frame-time statistics for speed checks. Percentiles use the nearest-rank
// method so the numbers can be reproduced by hand from a sorted list.

export interface FrameSummary {
  count: number
  median: number
  p95: number
  /** Fraction of samples strictly greater than the budget. */
  overBudgetShare: number
}

function nearestRank(sorted: readonly number[], p: number): number {
  return sorted[Math.max(0, Math.ceil(p * sorted.length) - 1)]
}

export function summarise(samples: readonly number[], budgetMs: number): FrameSummary {
  const n = samples.length
  if (n === 0) return { count: 0, median: 0, p95: 0, overBudgetShare: 0 }
  const sorted = [...samples].sort((a, b) => a - b)
  const mid = n >> 1
  const median = n % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
  let over = 0
  for (const s of sorted) if (s > budgetMs) over++
  return { count: n, median, p95: nearestRank(sorted, 0.95), overBudgetShare: over / n }
}

export interface FrameTimer {
  record(ms: number): void
  /** Oldest first. A copy, so callers may sort it. */
  samples(): number[]
  reset(): void
}

/** A ring over a preallocated buffer: recording allocates nothing per frame. */
export function createFrameTimer(capacity: number): FrameTimer {
  const buf = new Float64Array(capacity)
  let next = 0
  let filled = 0
  return {
    record(ms) {
      buf[next] = ms
      next = (next + 1) % capacity
      if (filled < capacity) filled++
    },
    samples() {
      const start = filled < capacity ? 0 : next
      const out = new Array<number>(filled)
      for (let i = 0; i < filled; i++) out[i] = buf[(start + i) % capacity]
      return out
    },
    reset() {
      next = 0
      filled = 0
    },
  }
}
