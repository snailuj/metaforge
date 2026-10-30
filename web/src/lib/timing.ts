/// <reference types="vite/client" />

// Timing for routines worth measuring (lookups, glimpses). Off unless asked
// for, and always off in production builds, where every timer is a shared no-op.
// Turn on with VITE_MF_TIMING=1 at build time, or localStorage 'mf-timing' = '1'
// (read once, at load).

export type StopTimer = (details?: Record<string, unknown>) => void
export type StartTimer = (label: string) => StopTimer

const NOOP: StopTimer = () => {}
const STORAGE_KEY = 'mf-timing'

export function timingEnabled({ prod, envFlag, stored }: {
  prod: boolean
  envFlag: string | undefined
  stored: () => string | null
}): boolean {
  if (prod) return false
  if (envFlag === '1') return true
  try {
    return stored() === '1'
  } catch (err) {
    console.warn('[timing] could not read the timing flag; timing stays off', err)
    return false
  }
}

export function makeTimer(
  enabled: boolean,
  now: () => number = () => performance.now(),
  log: (label: string, details: Record<string, unknown>) => void = (label, details) => console.debug(`[timing] ${label}`, details),
): StartTimer {
  if (!enabled) return () => NOOP
  return label => {
    const started = now()
    return details => log(label, { ...details, ms: Math.round(now() - started) })
  }
}

export const startTimer: StartTimer = makeTimer(timingEnabled({
  prod: import.meta.env.PROD,
  envFlag: import.meta.env.VITE_MF_TIMING,
  stored: () => localStorage.getItem(STORAGE_KEY),
}))
