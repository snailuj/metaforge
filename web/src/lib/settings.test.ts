import { describe, it, expect, vi } from 'vitest'
import { holdGraphEnabled } from './settings'

describe('hold-graph setting', () => {
  // Rule: holding the graph still during arrivals is off unless the hidden key says '1'.
  it('is off by default and on only for the stored value 1', () => {
    expect(holdGraphEnabled(() => null)).toBe(false)
    expect(holdGraphEnabled(() => '0')).toBe(false)
    expect(holdGraphEnabled(() => '1')).toBe(true)
  })

  // Rule: storage that throws leaves the setting off and is logged.
  it('treats unreadable storage as off and logs it', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(holdGraphEnabled(() => { throw new Error('blocked') })).toBe(false)
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })

  // Rule: the default reader uses the 'mf-hold-graph' key.
  it('reads the mf-hold-graph key by default', () => {
    localStorage.setItem('mf-hold-graph', '1')
    expect(holdGraphEnabled()).toBe(true)
    localStorage.removeItem('mf-hold-graph')
    expect(holdGraphEnabled()).toBe(false)
  })
})
