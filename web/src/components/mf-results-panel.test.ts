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
        antonyms: [],
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
        relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
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
          relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
        },
        {
          synset_id: '2',
          pos: 'noun',
          definition: 'sloping land beside a river',
          synonyms: [],
          relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
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

  // --- Usage example, register, connotation, collocations ---

  it('renders usage example as italic quote', async () => {
    const withUsage: LookupResult = {
      word: 'candle',
      senses: [{
        synset_id: '1',
        pos: 'noun',
        definition: 'stick of wax with a wick',
        usage_example: 'She lit a candle in the draught.',
        synonyms: [],
        relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
      }],
    }
    el.result = withUsage
    await el.updateComplete

    const example = el.shadowRoot!.querySelector('.usage-example')
    expect(example).toBeTruthy()
    expect(example?.textContent).toContain('She lit a candle')
  })

  it('does not render usage example when absent', async () => {
    el.result = melancholy
    await el.updateComplete

    const example = el.shadowRoot!.querySelector('.usage-example')
    expect(example).toBeNull()
  })

  it('renders register badge for non-neutral register', async () => {
    const formal: LookupResult = {
      word: 'taper',
      senses: [{
        synset_id: '1',
        pos: 'noun',
        definition: 'a slender candle',
        register: 'formal',
        synonyms: [],
        relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
      }],
    }
    el.result = formal
    await el.updateComplete

    const badge = el.shadowRoot!.querySelector('.meta-badge.register')
    expect(badge).toBeTruthy()
    expect(badge?.textContent?.trim()).toBe('register-formal')
  })

  it('does not render register badge for neutral', async () => {
    const neutral: LookupResult = {
      word: 'candle',
      senses: [{
        synset_id: '1',
        pos: 'noun',
        definition: 'stick of wax',
        register: 'neutral',
        synonyms: [],
        relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
      }],
    }
    el.result = neutral
    await el.updateComplete

    const badge = el.shadowRoot!.querySelector('.meta-badge.register')
    expect(badge).toBeNull()
  })

  it('renders connotation badge for non-neutral connotation', async () => {
    const negative: LookupResult = {
      word: 'storm',
      senses: [{
        synset_id: '1',
        pos: 'noun',
        definition: 'violent weather',
        connotation: 'negative',
        synonyms: [],
        relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
      }],
    }
    el.result = negative
    await el.updateComplete

    const badge = el.shadowRoot!.querySelector('.meta-badge.connotation-negative')
    expect(badge).toBeTruthy()
    expect(badge?.textContent?.trim()).toBe('connotation-negative')
  })

  it('renders collocations section', async () => {
    const withColloc: LookupResult = {
      word: 'fire',
      senses: [{
        synset_id: '1',
        pos: 'noun',
        definition: 'combustion',
        synonyms: [],
        relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
        collocations: [
          { word: 'brigade', synset_id: '100' },
          { word: 'alarm', synset_id: '101' },
        ],
      }],
    }
    el.result = withColloc
    await el.updateComplete

    const labels = el.shadowRoot!.querySelectorAll('.section-label')
    const collocLabel = Array.from(labels).find(l => l.textContent === 'results-collocations')
    expect(collocLabel).toBeTruthy()

    const chips = el.shadowRoot!.querySelectorAll('.word-chip.collocation')
    expect(chips.length).toBe(2)
    expect(chips[0].textContent).toBe('brigade')
    expect(chips[1].textContent).toBe('alarm')
  })

  it('does not render collocations when empty', async () => {
    el.result = melancholy
    await el.updateComplete

    const chips = el.shadowRoot!.querySelectorAll('.word-chip.collocation')
    expect(chips.length).toBe(0)
  })

  it('renders both register and connotation badges together', async () => {
    const both: LookupResult = {
      word: 'slaughter',
      senses: [{
        synset_id: '1',
        pos: 'noun',
        definition: 'killing of animals for food',
        register: 'informal',
        connotation: 'negative',
        synonyms: [],
        relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
      }],
    }
    el.result = both
    await el.updateComplete

    const badges = el.shadowRoot!.querySelectorAll('.meta-badge')
    expect(badges.length).toBe(2)
  })

  it('collocation chips fire navigation event', async () => {
    const withColloc: LookupResult = {
      word: 'fire',
      senses: [{
        synset_id: '1',
        pos: 'noun',
        definition: 'combustion',
        synonyms: [],
        relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
        collocations: [{ word: 'brigade', synset_id: '100' }],
      }],
    }
    el.result = withColloc
    await el.updateComplete

    const handler = vi.fn()
    el.addEventListener('mf-word-navigate', handler)

    const chip = el.shadowRoot!.querySelector('.word-chip.collocation')
    chip?.dispatchEvent(new MouseEvent('click', { bubbles: true }))

    expect(handler).toHaveBeenCalledOnce()
    expect(handler.mock.calls[0][0].detail.word).toBe('brigade')
  })
})
