import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { LookupResult } from '@/types/api'

// Mock 3D dependencies that require WebGL (unavailable in happy-dom).
// ForceGraph3D is a curried factory: ForceGraph3D(opts)(container) → instance with chainable methods.
const chainable = new Proxy({}, { get: () => () => chainable })
vi.mock('3d-force-graph', () => ({ default: () => () => chainable }))
vi.mock('three-spritetext', () => ({ default: vi.fn() }))

// Mock the API client module
vi.mock('@/api/client', () => ({
  lookupWord: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number
    constructor(message: string, status: number) {
      super(message)
      this.name = 'ApiError'
      this.status = status
    }
  },
}))

// Mock the strings module
vi.mock('@/lib/strings', () => ({
  initStrings: vi.fn().mockResolvedValue(undefined),
  getString: vi.fn((id: string, args?: Record<string, string | number>) => {
    if (id === 'results-word-not-found' && args?.word) return `Not found: ${args.word}`
    if (id === 'error-generic') return 'Something went wrong'
    return id
  }),
}))

import { MfApp } from './mf-app'
import { lookupWord } from '@/api/client'

const mockResult: LookupResult = {
  word: 'fire',
  senses: [{
    synset_id: '1',
    pos: 'noun',
    definition: 'combustion',
    synonyms: [],
    relations: { hypernyms: [], hyponyms: [], similar: [] },
  }],
}

describe('MfApp', () => {
  let el: MfApp

  beforeEach(async () => {
    window.location.hash = ''
    el = new MfApp()
    document.body.appendChild(el)
    await el.updateComplete
    // Wait for connectedCallback async work (initStrings)
    await new Promise(r => setTimeout(r, 0))
    await el.updateComplete
  })

  afterEach(() => {
    document.body.removeChild(el)
    vi.restoreAllMocks()
    window.location.hash = ''
  })

  it('is defined as a custom element', () => {
    expect(MfApp).toBeDefined()
  })

  it('starts in idle state', () => {
    const status = el.shadowRoot!.querySelector('.status-message')
    expect(status).not.toBeNull()
    expect(status?.textContent).toContain('status-idle')
  })

  it('transitions to ready state on successful lookup', async () => {
    // Use mockResolvedValue (not Once) — setWordHash triggers hashchange → second doLookup
    vi.mocked(lookupWord).mockResolvedValue(mockResult)

    const searchBar = el.shadowRoot!.querySelector('mf-search-bar')
    searchBar?.dispatchEvent(new CustomEvent('mf-search', {
      detail: { word: 'fire' },
      bubbles: true,
      composed: true,
    }))

    // Wait for the async lookup + hashchange re-lookup to complete
    await new Promise(r => setTimeout(r, 100))
    await el.updateComplete

    // In ready state, status-message should not be visible
    const status = el.shadowRoot!.querySelector('.status-message')
    expect(status).toBeNull()
  })

  it('transitions to error state on 404', async () => {
    const { ApiError } = await import('@/api/client')
    vi.mocked(lookupWord).mockRejectedValueOnce(new ApiError('not found', 404))

    const searchBar = el.shadowRoot!.querySelector('mf-search-bar')
    searchBar?.dispatchEvent(new CustomEvent('mf-search', {
      detail: { word: 'xyznoword' },
      bubbles: true,
      composed: true,
    }))

    await new Promise(r => setTimeout(r, 50))
    await el.updateComplete

    const error = el.shadowRoot!.querySelector('.error-message')
    expect(error).not.toBeNull()
    expect(error?.textContent).toContain('Not found')
  })

  it('ignores errors silently for suggest searches', async () => {
    vi.mocked(lookupWord).mockRejectedValueOnce(new Error('fail'))

    const searchBar = el.shadowRoot!.querySelector('mf-search-bar')
    searchBar?.dispatchEvent(new CustomEvent('mf-search', {
      detail: { word: 'xyz', suggest: true },
      bubbles: true,
      composed: true,
    }))

    await new Promise(r => setTimeout(r, 50))
    await el.updateComplete

    // Should stay in idle, not show error
    const error = el.shadowRoot!.querySelector('.error-message')
    expect(error).toBeNull()
    const status = el.shadowRoot!.querySelector('.status-message')
    expect(status?.textContent).toContain('status-idle')
  })

  it('handles mf-node-navigate by looking up the word', async () => {
    vi.mocked(lookupWord).mockResolvedValue(mockResult)

    const graph = el.shadowRoot!.querySelector('mf-force-graph')
    graph?.dispatchEvent(new CustomEvent('mf-node-navigate', {
      detail: { word: 'navigate-test' },
      bubbles: true,
      composed: true,
    }))

    await new Promise(r => setTimeout(r, 100))
    await el.updateComplete

    expect(lookupWord).toHaveBeenCalledWith('navigate-test')
  })

  it('handles mf-word-navigate by looking up the word', async () => {
    vi.mocked(lookupWord).mockResolvedValue(mockResult)

    const resultsPanel = el.shadowRoot!.querySelector('mf-results-panel')
    resultsPanel?.dispatchEvent(new CustomEvent('mf-word-navigate', {
      detail: { word: 'panel-word' },
      bubbles: true,
      composed: true,
    }))

    await new Promise(r => setTimeout(r, 100))
    await el.updateComplete

    expect(lookupWord).toHaveBeenCalledWith('panel-word')
  })

  it('shows toast on mf-word-copy event', async () => {
    const resultsPanel = el.shadowRoot!.querySelector('mf-results-panel')
    resultsPanel?.dispatchEvent(new CustomEvent('mf-word-copy', {
      detail: { word: 'copied-word' },
      bubbles: true,
      composed: true,
    }))

    await el.updateComplete

    const toast = el.shadowRoot!.querySelector('mf-toast')
    expect(toast).not.toBeNull()
  })

  it('shows generic error for non-404 failures', async () => {
    vi.mocked(lookupWord).mockRejectedValueOnce(new Error('network error'))

    const searchBar = el.shadowRoot!.querySelector('mf-search-bar')
    searchBar?.dispatchEvent(new CustomEvent('mf-search', {
      detail: { word: 'fail-word' },
      bubbles: true,
      composed: true,
    }))

    await new Promise(r => setTimeout(r, 50))
    await el.updateComplete

    const error = el.shadowRoot!.querySelector('.error-message')
    expect(error).not.toBeNull()
    expect(error?.textContent).toContain('Something went wrong')
  })
})
