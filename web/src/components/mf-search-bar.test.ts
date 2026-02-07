import { describe, it, expect, vi } from 'vitest'
import { MfSearchBar } from './mf-search-bar'

describe('MfSearchBar', () => {
  it('is defined as a custom element', () => {
    expect(MfSearchBar).toBeDefined()
    expect(customElements.get('mf-search-bar')).toBeDefined()
  })

  it('fires mf-search event with trimmed, lowercased word', async () => {
    const el = document.createElement('mf-search-bar') as MfSearchBar
    document.body.appendChild(el)
    await el.updateComplete

    const handler = vi.fn()
    el.addEventListener('mf-search', handler)

    // Simulate typing and submitting
    const input = el.shadowRoot!.querySelector('input')!
    input.value = '  Melancholy  '
    input.dispatchEvent(new Event('input'))
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))

    expect(handler).toHaveBeenCalledOnce()
    expect(handler.mock.calls[0][0].detail.word).toBe('melancholy')

    document.body.removeChild(el)
  })

  it('does not fire mf-search for empty input', async () => {
    const el = document.createElement('mf-search-bar') as MfSearchBar
    document.body.appendChild(el)
    await el.updateComplete

    const handler = vi.fn()
    el.addEventListener('mf-search', handler)

    const input = el.shadowRoot!.querySelector('input')!
    input.value = '   '
    input.dispatchEvent(new Event('input'))
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))

    expect(handler).not.toHaveBeenCalled()

    document.body.removeChild(el)
  })
})
