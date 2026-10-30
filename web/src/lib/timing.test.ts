import { describe, it, expect, vi } from 'vitest'
import { makeTimer, timingEnabled } from './timing'

describe('timing flag', () => {
  // Rule: a production build never times, whatever the flags say.
  it('is off in production even with both flags set', () => {
    expect(timingEnabled({ prod: true, envFlag: '1', stored: () => '1' })).toBe(false)
  })

  // Rule: outside production, either the build flag or the stored key turns timing on.
  it('is on in development when the env flag or the stored key is set', () => {
    expect(timingEnabled({ prod: false, envFlag: '1', stored: () => null })).toBe(true)
    expect(timingEnabled({ prod: false, envFlag: undefined, stored: () => '1' })).toBe(true)
    expect(timingEnabled({ prod: false, envFlag: undefined, stored: () => null })).toBe(false)
  })

  // Rule: storage that throws (private mode, blocked site data) leaves timing off and is logged.
  it('treats unreadable storage as off and logs it', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(timingEnabled({ prod: false, envFlag: undefined, stored: () => { throw new Error('blocked') } })).toBe(false)
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })
})

describe('makeTimer', () => {
  // Rule: a disabled timer does no work at all: no clock reads, no log.
  it('is a no-op when disabled', () => {
    const now = vi.fn(() => 0)
    const log = vi.fn()
    const stop = makeTimer(false, now, log)('lookup')
    stop({ word: 'fire' })
    expect(now).not.toHaveBeenCalled()
    expect(log).not.toHaveBeenCalled()
  })

  // Rule: an enabled timer logs its label, the caller's details and the elapsed whole milliseconds.
  it('logs the duration when enabled', () => {
    let t = 100
    const log = vi.fn()
    const stop = makeTimer(true, () => t, log)('lookup')
    t = 342.6
    stop({ word: 'fire' })
    expect(log).toHaveBeenCalledWith('lookup', { word: 'fire', ms: 243 })
  })
})
