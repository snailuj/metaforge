/** Glimpse results that finish close together go to the graph together. */
export const ARRIVAL_WINDOW_MS = 300

export interface ArrivalBatch {
  /** One arrival is ready. `moreExpected`: others are still in flight and may join it. */
  arrive(moreExpected: boolean): void
  /** Drop the pending flush: a graph update that already carries these arrivals ran. */
  cancel(): void
  readonly pending: boolean
}

/**
 * Collects arrivals into one `flush`: the first opens a window of `windowMs`
 * and the flush runs when it closes, or at once when no more are expected, so
 * the last arrival of a wave is never delayed. The window is fixed from the
 * first arrival, so a steady trickle cannot postpone the flush forever.
 */
export function arrivalBatch(windowMs: number, flush: () => void): ArrivalBatch {
  let timer: ReturnType<typeof setTimeout> | null = null
  const cancel = () => {
    if (timer !== null) clearTimeout(timer)
    timer = null
  }
  const run = () => {
    cancel()
    flush()
  }
  return {
    arrive(moreExpected) {
      if (!moreExpected) run()
      else if (timer === null) timer = setTimeout(run, windowMs)
    },
    cancel,
    get pending() { return timer !== null },
  }
}
