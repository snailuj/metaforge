import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MfSearchBar } from './mf-search-bar'

describe('MfSearchBar', () => {
  let el: MfSearchBar

  beforeEach(async () => {
    vi.useFakeTimers()
    el = document.createElement('mf-search-bar') as MfSearchBar
    document.body.appendChild(el)
    await el.updateComplete
  })

  afterEach(() => {
    document.body.removeChild(el)
    vi.useRealTimers()
  })

  it('is defined as a custom element', () => {
    expect(MfSearchBar).toBeDefined()
    expect(customElements.get('mf-search-bar')).toBeDefined()
  })

  it('fires mf-search event with trimmed, lowercased word', async () => {
    const handler = vi.fn()
    el.addEventListener('mf-search', handler)

    const input = el.shadowRoot!.querySelector('input')!
    input.value = '  Melancholy  '
    input.dispatchEvent(new Event('input'))
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))

    expect(handler).toHaveBeenCalledOnce()
    expect(handler.mock.calls[0][0].detail.word).toBe('melancholy')
  })

  it('does not fire mf-search for empty input', async () => {
    const handler = vi.fn()
    el.addEventListener('mf-search', handler)

    const input = el.shadowRoot!.querySelector('input')!
    input.value = '   '
    input.dispatchEvent(new Event('input'))
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))

    expect(handler).not.toHaveBeenCalled()
  })

  it('stops keydown propagation from input to prevent FlyControls capture', async () => {
    const input = el.shadowRoot!.querySelector('input')!
    const windowHandler = vi.fn()
    window.addEventListener('keydown', windowHandler)

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'w', bubbles: true, composed: true }))

    expect(windowHandler).not.toHaveBeenCalled()
    window.removeEventListener('keydown', windowHandler)
  })

  it('stops keyup propagation from input to prevent FlyControls capture', async () => {
    const input = el.shadowRoot!.querySelector('input')!
    const windowHandler = vi.fn()
    window.addEventListener('keyup', windowHandler)

    input.dispatchEvent(new KeyboardEvent('keyup', { key: 'w', bubbles: true, composed: true }))

    expect(windowHandler).not.toHaveBeenCalled()
    window.removeEventListener('keyup', windowHandler)
  })

  it('fires mf-search with suggest flag after 200ms debounce', async () => {
    const handler = vi.fn()
    el.addEventListener('mf-search', handler)

    const input = el.shadowRoot!.querySelector('input')!
    input.value = 'ephemeral'
    input.dispatchEvent(new Event('input'))

    expect(handler).not.toHaveBeenCalled()

    vi.advanceTimersByTime(250)
    expect(handler).toHaveBeenCalledOnce()
    expect(handler.mock.calls[0][0].detail.word).toBe('ephemeral')
    expect(handler.mock.calls[0][0].detail.suggest).toBe(true)
  })

  it('Enter fires without suggest flag', async () => {
    const handler = vi.fn()
    el.addEventListener('mf-search', handler)

    const input = el.shadowRoot!.querySelector('input')!
    input.value = 'ephemeral'
    input.dispatchEvent(new Event('input'))
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))

    expect(handler).toHaveBeenCalledOnce()
    expect(handler.mock.calls[0][0].detail.suggest).toBeFalsy()
  })

  it('resets debounce timer on subsequent input', async () => {
    const handler = vi.fn()
    el.addEventListener('mf-search', handler)

    const input = el.shadowRoot!.querySelector('input')!
    input.value = 'eph'
    input.dispatchEvent(new Event('input'))

    vi.advanceTimersByTime(150)
    expect(handler).not.toHaveBeenCalled()

    // New input resets the timer
    input.value = 'ephemeral'
    input.dispatchEvent(new Event('input'))

    vi.advanceTimersByTime(150)
    expect(handler).not.toHaveBeenCalled()

    vi.advanceTimersByTime(100)
    expect(handler).toHaveBeenCalledOnce()
    expect(handler.mock.calls[0][0].detail.word).toBe('ephemeral')
  })

  it('Enter bypasses debounce and fires immediately', async () => {
    const handler = vi.fn()
    el.addEventListener('mf-search', handler)

    const input = el.shadowRoot!.querySelector('input')!
    input.value = 'ephemeral'
    input.dispatchEvent(new Event('input'))
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))

    // Should fire once immediately (Enter), not again after debounce
    expect(handler).toHaveBeenCalledOnce()

    vi.advanceTimersByTime(500)
    expect(handler).toHaveBeenCalledOnce() // still just once
  })

  it('does not fire debounced search for short input', async () => {
    const handler = vi.fn()
    el.addEventListener('mf-search', handler)

    const input = el.shadowRoot!.querySelector('input')!
    input.value = 'ab'
    input.dispatchEvent(new Event('input'))

    vi.advanceTimersByTime(500)
    expect(handler).not.toHaveBeenCalled()
  })

  it('Escape clears input and cancels pending debounce', async () => {
    const handler = vi.fn()
    el.addEventListener('mf-search', handler)

    const input = el.shadowRoot!.querySelector('input')!
    input.value = 'ephemeral'
    input.dispatchEvent(new Event('input'))

    vi.advanceTimersByTime(100)
    expect(handler).not.toHaveBeenCalled()

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))

    expect(input.value).toBe('')
    vi.advanceTimersByTime(500)
    expect(handler).not.toHaveBeenCalled()
  })
})
