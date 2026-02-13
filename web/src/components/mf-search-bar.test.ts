import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { AutocompleteSuggestion } from '@/api/client'

// Mock autocompleteWord before importing the component
const mockAutocomplete = vi.fn<(prefix: string, limit?: number) => Promise<AutocompleteSuggestion[]>>()
  .mockResolvedValue([])

vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client')
  return {
    ...actual,
    autocompleteWord: (...args: Parameters<typeof mockAutocomplete>) => mockAutocomplete(...args),
  }
})

// Import after mock setup
import { MfSearchBar } from './mf-search-bar'

const TEST_SUGGESTIONS: AutocompleteSuggestion[] = [
  { word: 'fire', definition: 'the event of something burning', sense_count: 21, rarity: 'common' },
  { word: 'firearm', definition: 'a portable gun', sense_count: 1, rarity: 'unusual' },
  { word: 'firebrand', definition: 'a piece of wood that has been burned', sense_count: 2, rarity: 'rare' },
]

/** Trigger input event with a value, advance debounce, and wait for Lit update. */
async function typeAndDebounce(el: MfSearchBar, value: string) {
  const input = el.shadowRoot!.querySelector('input')!
  input.value = value
  input.dispatchEvent(new Event('input'))
  vi.advanceTimersByTime(250)
  // Allow microtasks (async autocomplete resolve + Lit update)
  await new Promise(r => queueMicrotask(r))
  await el.updateComplete
}

describe('MfSearchBar', () => {
  let el: MfSearchBar

  beforeEach(async () => {
    vi.useFakeTimers()
    mockAutocomplete.mockReset().mockResolvedValue([])
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

  it('fires mf-search event with trimmed, lowercased word on Enter', async () => {
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

  it('calls autocompleteWord after debounce instead of emitting mf-search', async () => {
    const searchHandler = vi.fn()
    el.addEventListener('mf-search', searchHandler)
    mockAutocomplete.mockResolvedValue(TEST_SUGGESTIONS)

    await typeAndDebounce(el, 'fir')

    expect(mockAutocomplete).toHaveBeenCalledWith('fir')
    expect(searchHandler).not.toHaveBeenCalled()
  })

  it('resets debounce timer on subsequent input', async () => {
    mockAutocomplete.mockResolvedValue(TEST_SUGGESTIONS)

    const input = el.shadowRoot!.querySelector('input')!
    input.value = 'fir'
    input.dispatchEvent(new Event('input'))

    vi.advanceTimersByTime(150)
    expect(mockAutocomplete).not.toHaveBeenCalled()

    input.value = 'fire'
    input.dispatchEvent(new Event('input'))

    vi.advanceTimersByTime(150)
    expect(mockAutocomplete).not.toHaveBeenCalled()

    vi.advanceTimersByTime(100)
    await new Promise(r => queueMicrotask(r))
    expect(mockAutocomplete).toHaveBeenCalledOnce()
    expect(mockAutocomplete).toHaveBeenCalledWith('fire')
  })

  it('Enter bypasses debounce and fires mf-search immediately', async () => {
    const handler = vi.fn()
    el.addEventListener('mf-search', handler)

    const input = el.shadowRoot!.querySelector('input')!
    input.value = 'ephemeral'
    input.dispatchEvent(new Event('input'))
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))

    expect(handler).toHaveBeenCalledOnce()

    vi.advanceTimersByTime(500)
    expect(handler).toHaveBeenCalledOnce()
  })

  it('does not fire debounced search for short input', async () => {
    const input = el.shadowRoot!.querySelector('input')!
    input.value = 'ab'
    input.dispatchEvent(new Event('input'))

    vi.advanceTimersByTime(500)
    expect(mockAutocomplete).not.toHaveBeenCalled()
  })

  it('Escape clears input and cancels pending debounce', async () => {
    const handler = vi.fn()
    el.addEventListener('mf-search', handler)

    const input = el.shadowRoot!.querySelector('input')!
    input.value = 'ephemeral'
    input.dispatchEvent(new Event('input'))

    vi.advanceTimersByTime(100)
    expect(mockAutocomplete).not.toHaveBeenCalled()

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))

    expect(input.value).toBe('')
    vi.advanceTimersByTime(500)
    expect(mockAutocomplete).not.toHaveBeenCalled()
    expect(handler).not.toHaveBeenCalled()
  })

  // --- Dropdown-specific tests ---

  it('renders suggestion dropdown after autocomplete returns results', async () => {
    mockAutocomplete.mockResolvedValue(TEST_SUGGESTIONS)

    await typeAndDebounce(el, 'fir')

    const items = el.shadowRoot!.querySelectorAll('.suggestion-item')
    expect(items.length).toBe(3)

    const firstItem = items[0]
    expect(firstItem.querySelector('.suggestion-word')?.textContent).toContain('fire')
    expect(firstItem.querySelector('.suggestion-definition')?.textContent).toContain('the event of something burning')
  })

  it('shows sense count badge when sense_count > 1', async () => {
    mockAutocomplete.mockResolvedValue(TEST_SUGGESTIONS)

    await typeAndDebounce(el, 'fir')

    const items = el.shadowRoot!.querySelectorAll('.suggestion-item')
    // "fire" has 21 senses
    const fireBadge = items[0].querySelector('.sense-badge')
    expect(fireBadge?.textContent).toContain('21')

    // "firearm" has 1 sense — no badge
    const firearmBadge = items[1].querySelector('.sense-badge')
    expect(firearmBadge).toBeNull()
  })

  it('shows rarity badge on suggestions', async () => {
    mockAutocomplete.mockResolvedValue(TEST_SUGGESTIONS)

    await typeAndDebounce(el, 'fir')

    const items = el.shadowRoot!.querySelectorAll('.suggestion-item')
    const rarityBadge = items[0].querySelector('.rarity-badge')
    expect(rarityBadge?.textContent).toContain('common')
  })

  it('arrow down selects the first suggestion', async () => {
    mockAutocomplete.mockResolvedValue(TEST_SUGGESTIONS)

    await typeAndDebounce(el, 'fir')

    const input = el.shadowRoot!.querySelector('input')!
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown' }))
    await el.updateComplete

    const items = el.shadowRoot!.querySelectorAll('.suggestion-item')
    expect(items[0].classList.contains('selected')).toBe(true)
  })

  it('arrow up from first wraps to last', async () => {
    mockAutocomplete.mockResolvedValue(TEST_SUGGESTIONS)

    await typeAndDebounce(el, 'fir')

    const input = el.shadowRoot!.querySelector('input')!
    // ArrowDown to select first
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown' }))
    await el.updateComplete
    // ArrowUp wraps to last
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp' }))
    await el.updateComplete

    const items = el.shadowRoot!.querySelectorAll('.suggestion-item')
    expect(items[2].classList.contains('selected')).toBe(true)
  })

  it('Enter on selected suggestion emits mf-search with that word', async () => {
    mockAutocomplete.mockResolvedValue(TEST_SUGGESTIONS)
    const handler = vi.fn()
    el.addEventListener('mf-search', handler)

    await typeAndDebounce(el, 'fir')

    const input = el.shadowRoot!.querySelector('input')!
    // Select second item (firearm)
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown' }))
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown' }))
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))

    expect(handler).toHaveBeenCalledOnce()
    expect(handler.mock.calls[0][0].detail.word).toBe('firearm')
  })

  it('click on suggestion emits mf-search with that word', async () => {
    mockAutocomplete.mockResolvedValue(TEST_SUGGESTIONS)
    const handler = vi.fn()
    el.addEventListener('mf-search', handler)

    await typeAndDebounce(el, 'fir')

    const items = el.shadowRoot!.querySelectorAll('.suggestion-item')
    ;(items[2] as HTMLElement).click()

    expect(handler).toHaveBeenCalledOnce()
    expect(handler.mock.calls[0][0].detail.word).toBe('firebrand')
  })

  it('Escape closes the dropdown', async () => {
    mockAutocomplete.mockResolvedValue(TEST_SUGGESTIONS)

    await typeAndDebounce(el, 'fir')
    expect(el.shadowRoot!.querySelectorAll('.suggestion-item').length).toBe(3)

    const input = el.shadowRoot!.querySelector('input')!
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await el.updateComplete

    expect(el.shadowRoot!.querySelectorAll('.suggestion-item').length).toBe(0)
  })

  it('clears dropdown when input drops below 3 chars', async () => {
    mockAutocomplete.mockResolvedValue(TEST_SUGGESTIONS)

    await typeAndDebounce(el, 'fir')
    expect(el.shadowRoot!.querySelectorAll('.suggestion-item').length).toBe(3)

    const input = el.shadowRoot!.querySelector('input')!
    input.value = 'fi'
    input.dispatchEvent(new Event('input'))
    await el.updateComplete

    expect(el.shadowRoot!.querySelectorAll('.suggestion-item').length).toBe(0)
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
