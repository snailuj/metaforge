import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest'
import { MfResultsPanel } from './mf-results-panel'
import type { LookupResult } from '@/types/api'

const melancholy: LookupResult = {
  word: 'melancholy',
  rarity: 'unusual',
  senses: [
    {
      synset_id: '72858',
      pos: 'noun',
      definition: 'a feeling of thoughtful sadness',
      synonyms: [
        { word: 'sadness', synset_id: '72855', rarity: 'common' },
      ],
      relations: {
        hypernyms: [{ word: 'emotion', synset_id: '1' }],
        hyponyms: [{ word: 'gloom', synset_id: '2' }],
        similar: [],
      },
    },
  ],
}

describe('MfResultsPanel', () => {
  let el: MfResultsPanel

  beforeEach(async () => {
    el = document.createElement('mf-results-panel') as MfResultsPanel
    document.body.appendChild(el)
    await el.updateComplete
  })

  afterEach(() => {
    document.body.removeChild(el)
  })

  it('is defined as a custom element', () => {
    expect(MfResultsPanel).toBeDefined()
    expect(customElements.get('mf-results-panel')).toBeDefined()
  })

  it('renders the word heading when result is set', async () => {
    el.result = melancholy
    await el.updateComplete

    const heading = el.shadowRoot!.querySelector('h2')
    expect(heading?.textContent).toContain('melancholy')
  })

  it('renders sense definitions', async () => {
    el.result = melancholy
    await el.updateComplete

    const defs = el.shadowRoot!.querySelectorAll('.definition')
    expect(defs.length).toBeGreaterThan(0)
    expect(defs[0].textContent).toContain('thoughtful sadness')
  })

  it('renders a rarity badge for the looked-up word', async () => {
    el.result = melancholy
    await el.updateComplete

    const badge = el.shadowRoot!.querySelector('.rarity-badge')
    expect(badge).toBeTruthy()
    expect(badge?.textContent?.trim()).toBe('rarity-unusual')
  })

  it('applies correct CSS class for rarity tier', async () => {
    el.result = melancholy
    await el.updateComplete

    const badge = el.shadowRoot!.querySelector('.rarity-badge')
    expect(badge?.classList.contains('unusual')).toBe(true)
  })

  it('renders data-rarity attribute on word chips', async () => {
    el.result = melancholy
    await el.updateComplete

    const chip = el.shadowRoot!.querySelector('[data-word="sadness"]')
    expect(chip?.getAttribute('data-rarity')).toBe('common')
  })

  it('does not render rarity badge when rarity is missing', async () => {
    const noRarity: LookupResult = {
      word: 'test',
      senses: [{
        synset_id: '1',
        pos: 'noun',
        definition: 'a test',
        synonyms: [],
        relations: { hypernyms: [], hyponyms: [], similar: [] },
      }],
    }
    el.result = noRarity
    await el.updateComplete

    const badge = el.shadowRoot!.querySelector('.rarity-badge')
    expect(badge).toBeNull()
  })

  it('fires mf-word-navigate on single click of a related word', async () => {
    el.result = melancholy
    await el.updateComplete

    const handler = vi.fn()
    el.addEventListener('mf-word-navigate', handler)

    const wordEl = el.shadowRoot!.querySelector('[data-word]')
    wordEl?.dispatchEvent(new MouseEvent('click', { bubbles: true }))

    expect(handler).toHaveBeenCalledOnce()
    expect(handler.mock.calls[0][0].detail.word).toBe('sadness')
  })

  it('fires mf-word-copy on right-click', async () => {
    el.result = melancholy
    await el.updateComplete

    const handler = vi.fn()
    el.addEventListener('mf-word-copy', handler)

    const wordEl = el.shadowRoot!.querySelector('[data-word]')
    const contextMenuEvent = new MouseEvent('contextmenu', { bubbles: true, cancelable: true })
    wordEl?.dispatchEvent(contextMenuEvent)

    expect(handler).toHaveBeenCalledOnce()
    expect(handler.mock.calls[0][0].detail.word).toBe('sadness')
  })

  it('fires mf-word-navigate on Enter keydown', async () => {
    el.result = melancholy
    await el.updateComplete

    const handler = vi.fn()
    el.addEventListener('mf-word-navigate', handler)

    const wordEl = el.shadowRoot!.querySelector('[data-word]')
    wordEl?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))

    expect(handler).toHaveBeenCalledOnce()
    expect(handler.mock.calls[0][0].detail.word).toBe('sadness')
  })

  it('renders nothing when result is null', async () => {
    el.result = null
    await el.updateComplete

    const panel = el.shadowRoot!.querySelector('.panel')
    expect(panel).toBeNull()
  })

  it('renders multiple senses', async () => {
    const multiSense: LookupResult = {
      word: 'bank',
      senses: [
        {
          synset_id: '1',
          pos: 'noun',
          definition: 'financial institution',
          synonyms: [],
          relations: { hypernyms: [], hyponyms: [], similar: [] },
        },
        {
          synset_id: '2',
          pos: 'noun',
          definition: 'sloping land beside a river',
          synonyms: [],
          relations: { hypernyms: [], hyponyms: [], similar: [] },
        },
      ],
    }

    el.result = multiSense
    await el.updateComplete

    const senses = el.shadowRoot!.querySelectorAll('.sense')
    expect(senses.length).toBe(2)
    expect(senses[0].textContent).toContain('financial institution')
    expect(senses[1].textContent).toContain('sloping land')
  })

  // --- Collapsible panel tests ---

  it('wraps .panel inside .panel-track', async () => {
    el.result = melancholy
    await el.updateComplete

    const track = el.shadowRoot!.querySelector('.panel-track')
    expect(track).toBeTruthy()
    const panel = track!.querySelector('.panel')
    expect(panel).toBeTruthy()
  })

  it('renders toggle button when result is set', async () => {
    el.result = melancholy
    await el.updateComplete

    const btn = el.shadowRoot!.querySelector('.toggle-btn')
    expect(btn).toBeTruthy()
  })

  it('is not collapsed by default', () => {
    expect(el.collapsed).toBe(false)
    expect(el.hasAttribute('collapsed')).toBe(false)
  })

  it('reflects collapsed property to attribute', async () => {
    el.collapsed = true
    await el.updateComplete

    expect(el.hasAttribute('collapsed')).toBe(true)
  })

  it('toggles collapsed state on button click', async () => {
    el.result = melancholy
    await el.updateComplete

    const btn = el.shadowRoot!.querySelector('.toggle-btn') as HTMLButtonElement
    btn.click()
    await el.updateComplete

    expect(el.collapsed).toBe(true)

    btn.click()
    await el.updateComplete

    expect(el.collapsed).toBe(false)
  })

  it('sets aria-expanded on toggle button', async () => {
    el.result = melancholy
    await el.updateComplete

    const btn = el.shadowRoot!.querySelector('.toggle-btn') as HTMLButtonElement
    expect(btn.getAttribute('aria-expanded')).toBe('true')

    el.collapsed = true
    await el.updateComplete
    expect(btn.getAttribute('aria-expanded')).toBe('false')
  })

  it('does not render toggle button when result is null', async () => {
    el.result = null
    await el.updateComplete

    const btn = el.shadowRoot!.querySelector('.toggle-btn')
    expect(btn).toBeNull()
  })

  it('starts collapsed on small screen', async () => {
    const listeners: Array<(e: MediaQueryListEvent) => void> = []
    const mockMql = {
      matches: true,
      addEventListener: vi.fn((_: string, cb: (e: MediaQueryListEvent) => void) => { listeners.push(cb) }),
      removeEventListener: vi.fn(),
    }
    const origMatchMedia = window.matchMedia
    window.matchMedia = vi.fn().mockReturnValue(mockMql) as unknown as typeof window.matchMedia

    const smallEl = document.createElement('mf-results-panel') as MfResultsPanel
    document.body.appendChild(smallEl)
    await smallEl.updateComplete

    expect(smallEl.collapsed).toBe(true)

    document.body.removeChild(smallEl)
    window.matchMedia = origMatchMedia
  })

  it('responds to media query change events', async () => {
    const listeners: Array<(e: MediaQueryListEvent) => void> = []
    const mockMql = {
      matches: false,
      addEventListener: vi.fn((_: string, cb: (e: MediaQueryListEvent) => void) => { listeners.push(cb) }),
      removeEventListener: vi.fn(),
    }
    const origMatchMedia = window.matchMedia
    window.matchMedia = vi.fn().mockReturnValue(mockMql) as unknown as typeof window.matchMedia

    const mqEl = document.createElement('mf-results-panel') as MfResultsPanel
    document.body.appendChild(mqEl)
    await mqEl.updateComplete

    expect(mqEl.collapsed).toBe(false)

    // Simulate media change to small screen
    listeners.forEach(cb => cb({ matches: true } as MediaQueryListEvent))
    expect(mqEl.collapsed).toBe(true)

    // Simulate media change back to large screen
    listeners.forEach(cb => cb({ matches: false } as MediaQueryListEvent))
    expect(mqEl.collapsed).toBe(false)

    document.body.removeChild(mqEl)
    window.matchMedia = origMatchMedia
  })
})
