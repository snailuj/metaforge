import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MfToast } from './mf-toast'

describe('MfToast', () => {
  let el: MfToast

  beforeEach(async () => {
    vi.useFakeTimers()
    el = new MfToast()
    document.body.appendChild(el)
    await el.updateComplete
  })

  afterEach(() => {
    document.body.removeChild(el)
    vi.useRealTimers()
  })

  it('is defined as a custom element', () => {
    expect(MfToast).toBeDefined()
  })

  it('renders with aria-live="polite" and role="status"', () => {
    const div = el.shadowRoot!.querySelector('.toast')
    expect(div?.getAttribute('role')).toBe('status')
    expect(div?.getAttribute('aria-live')).toBe('polite')
  })

  it('shows message and hides after duration', async () => {
    el.show('Copied!')
    await el.updateComplete

    const div = el.shadowRoot!.querySelector('.toast')
    expect(div?.classList.contains('visible')).toBe(true)
    expect(div?.textContent).toContain('Copied!')

    vi.advanceTimersByTime(1600)
    await el.updateComplete
    expect(div?.classList.contains('visible')).toBe(false)
  })

  it('clears timer on disconnect', () => {
    el.show('Test', 5000)
    document.body.removeChild(el)
    // Should not throw — timer was cleaned up
    vi.advanceTimersByTime(6000)
    // Re-add for afterEach cleanup
    document.body.appendChild(el)
  })

  it('respects custom duration', async () => {
    el.show('Custom duration', 500)
    await el.updateComplete

    const div = el.shadowRoot!.querySelector('.toast')
    expect(div?.classList.contains('visible')).toBe(true)

    vi.advanceTimersByTime(500)
    await el.updateComplete
    expect(div?.classList.contains('visible')).toBe(false)
  })

  it('multiple show() calls reset timer', async () => {
    el.show('First message', 1000)
    await el.updateComplete

    const div = el.shadowRoot!.querySelector('.toast')
    expect(div?.classList.contains('visible')).toBe(true)

    vi.advanceTimersByTime(800)
    expect(div?.classList.contains('visible')).toBe(true)

    el.show('Second message', 1000)
    await el.updateComplete
    expect(div?.textContent).toContain('Second message')

    vi.advanceTimersByTime(500)
    await el.updateComplete
    expect(div?.classList.contains('visible')).toBe(true)

    vi.advanceTimersByTime(600)
    await el.updateComplete
    expect(div?.classList.contains('visible')).toBe(false)
  })
})
