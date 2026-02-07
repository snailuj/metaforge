import { describe, it, expect, vi } from 'vitest'
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
  it('is defined as a custom element', () => {
    expect(MfResultsPanel).toBeDefined()
    expect(customElements.get('mf-results-panel')).toBeDefined()
  })

  it('renders the word heading when result is set', async () => {
    const el = document.createElement('mf-results-panel') as MfResultsPanel
    el.result = melancholy
    document.body.appendChild(el)
    await el.updateComplete

    const heading = el.shadowRoot!.querySelector('h2')
    expect(heading?.textContent).toContain('melancholy')

    document.body.removeChild(el)
  })

  it('renders sense definitions', async () => {
    const el = document.createElement('mf-results-panel') as MfResultsPanel
    el.result = melancholy
    document.body.appendChild(el)
    await el.updateComplete

    const defs = el.shadowRoot!.querySelectorAll('.definition')
    expect(defs.length).toBeGreaterThan(0)
    expect(defs[0].textContent).toContain('thoughtful sadness')

    document.body.removeChild(el)
  })

  it('fires mf-word-navigate on double-click of a related word', async () => {
    const el = document.createElement('mf-results-panel') as MfResultsPanel
    el.result = melancholy
    document.body.appendChild(el)
    await el.updateComplete

    const handler = vi.fn()
    el.addEventListener('mf-word-navigate', handler)

    const wordEl = el.shadowRoot!.querySelector('[data-word]')
    wordEl?.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))

    expect(handler).toHaveBeenCalledOnce()

    document.body.removeChild(el)
  })
})
