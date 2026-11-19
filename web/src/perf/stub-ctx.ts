// A recording 2D context for tests: methods count calls, properties keep what was set.

export interface Stub {
  ctx: CanvasRenderingContext2D
  calls: Record<string, number>
  shadowBlurSets: number[]
}

export function stubCtx(): Stub {
  const calls: Record<string, number> = {}
  const shadowBlurSets: number[] = []
  const state: Record<string, unknown> = {}
  const ctx = new Proxy({}, {
    get(_t, p: string) {
      if (p === 'measureText') return (s: string) => ({ width: s.length * 7 })
      if (p === 'createRadialGradient') return () => ({ addColorStop() {} })
      if (p in state) return state[p]
      return () => { calls[p] = (calls[p] ?? 0) + 1 }
    },
    set(_t, p: string, v) {
      if (p === 'shadowBlur') shadowBlurSets.push(v as number)
      state[p] = v
      return true
    },
  }) as unknown as CanvasRenderingContext2D
  return { ctx, calls, shadowBlurSets }
}
