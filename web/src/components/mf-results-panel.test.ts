import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MfResultsPanel } from './mf-results-panel'
import type { LookupResult } from '@/types/api'

const melancholy: LookupResult = {
  word: 'melancholy',
  senses: [
    {
      synset_id: '72858',
      pos: 'noun',
      definition: 'a feeling of thoughtful sadness',
      synonyms: [{ word: 'sadness', synset_id: '72855' }],
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

  it('fires mf-word-navigate on double-click of a related word', async () => {
    el.result = melancholy
    await el.updateComplete

    const handler = vi.fn()
    el.addEventListener('mf-word-navigate', handler)

    const wordEl = el.shadowRoot!.querySelector('[data-word]')
    wordEl?.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))

    expect(handler).toHaveBeenCalledOnce()
  })
})
