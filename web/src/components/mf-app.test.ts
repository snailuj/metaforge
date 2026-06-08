import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { LookupResult } from '@/types/api'

// Mock 3D dependencies that require WebGL (unavailable in happy-dom).
// ForceGraph3D is a curried factory: ForceGraph3D(opts)(container) → instance with chainable methods.
const chainable = new Proxy({}, { get: () => () => chainable })
vi.mock('3d-force-graph', () => ({ default: () => () => chainable }))

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
    synonyms: [
      { word: 'blaze', synset_id: '1' },
      { word: 'flame', synset_id: '1' },
    ],
    relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
  }],
}

const blazeLookup: LookupResult = {
  word: 'blaze',
  senses: [{
    synset_id: '1',
    pos: 'noun',
    definition: 'a strong flame',
    synonyms: [{ word: 'inferno', synset_id: '10' }],
    relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
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
    vi.mocked(lookupWord).mockResolvedValue(mockResult)

    const searchBar = el.shadowRoot!.querySelector('mf-search-bar')
    searchBar?.dispatchEvent(new CustomEvent('mf-search', {
      detail: { word: 'fire' },
      bubbles: true,
      composed: true,
    }))

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

  it('renders three rarity filter toggles when in ready state', async () => {
    ;(el as any).appState = 'ready'
    ;(el as any).result = { word: 'test', senses: [], rarity: 'common' }
    ;(el as any).graphData = { nodes: [{ id: 'test', word: 'test', relationType: 'central', val: 8, rarity: 'common' }], links: [] }
    await el.updateComplete

    const toggles = el.shadowRoot!.querySelectorAll('.rarity-toggle')
    expect(toggles.length).toBe(3)
  })

  it('all rarity filter toggles default to checked', async () => {
    ;(el as any).appState = 'ready'
    ;(el as any).result = { word: 'test', senses: [], rarity: 'common' }
    ;(el as any).graphData = { nodes: [{ id: 'test', word: 'test', relationType: 'central', val: 8 }], links: [] }
    await el.updateComplete

    const checkboxes = el.shadowRoot!.querySelectorAll<HTMLInputElement>('.rarity-toggle input[type="checkbox"]')
    expect(checkboxes.length).toBe(3)
    for (const cb of checkboxes) {
      expect(cb.checked).toBe(true)
    }
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

  it('does not double-lookup when hash matches current word', async () => {
    vi.mocked(lookupWord).mockResolvedValue(mockResult)

    // Perform initial lookup
    const searchBar = el.shadowRoot!.querySelector('mf-search-bar')
    searchBar?.dispatchEvent(new CustomEvent('mf-search', {
      detail: { word: 'fire' },
      bubbles: true,
      composed: true,
    }))

    await new Promise(r => setTimeout(r, 100))
    await el.updateComplete

    // lookupWord called once for the search, plus once from hashchange = 2 calls
    // (without fix; with fix it should be exactly 1)
    const callsBefore = vi.mocked(lookupWord).mock.calls.length
    vi.mocked(lookupWord).mockClear()

    // Manually fire hashchange with the same word already looked up
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    await new Promise(r => setTimeout(r, 100))

    // Should NOT have called lookupWord again — word hasn't changed
    expect(vi.mocked(lookupWord)).not.toHaveBeenCalled()
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

  it('discards stale response when a newer lookup overtakes it', async () => {
    const slowResult: LookupResult = {
      word: 'slow',
      senses: [{
        synset_id: '1',
        pos: 'adjective',
        definition: 'not fast',
        synonyms: [],
        relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
      }],
    }
    const fastResult: LookupResult = {
      word: 'fast',
      senses: [{
        synset_id: '2',
        pos: 'adjective',
        definition: 'moving quickly',
        synonyms: [],
        relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
      }],
    }

    // First lookup resolves slowly, second resolves immediately
    let resolveFirst!: (v: LookupResult) => void
    const firstPromise = new Promise<LookupResult>(r => { resolveFirst = r })
    vi.mocked(lookupWord)
      .mockReturnValueOnce(firstPromise)
      .mockResolvedValueOnce(fastResult)

    // Call doLookup directly to avoid event propagation issues
    ;(el as any).doLookup('slow')
    // Immediately start second lookup (before first resolves)
    ;(el as any).doLookup('fast')

    // Let the fast result resolve and all hashchange events settle
    await new Promise(r => setTimeout(r, 100))
    await el.updateComplete

    // Now the slow result resolves after the fast one
    resolveFirst(slowResult)
    await new Promise(r => setTimeout(r, 100))
    await el.updateComplete

    // The staleness guard should discard the slow result.
    // The app should show the FAST result (latest request).
    expect((el as any).result.word).toBe('fast')
    expect((el as any).appState).toBe('ready')
  })

  describe('rarity filter', () => {
    it('passes hiddenRarities to mf-force-graph', async () => {
      await el.updateComplete
      const graph = el.shadowRoot!.querySelector('mf-force-graph')!
      // By default all toggles are on, so hiddenRarities should be empty
      expect((graph as unknown as { hiddenRarities: Set<string> }).hiddenRarities.size).toBe(0)
    })

    it('adds rarity to hiddenRarities when toggle is unchecked', async () => {
      // Access internal state to toggle off 'rare'
      ;(el as unknown as { showRare: boolean }).showRare = false
      await el.updateComplete

      const graph = el.shadowRoot!.querySelector('mf-force-graph')!
      const hidden = (graph as unknown as { hiddenRarities: Set<string> }).hiddenRarities
      expect(hidden.has('rare')).toBe(true)
      expect(hidden.has('common')).toBe(false)
      expect(hidden.has('unusual')).toBe(false)
    })

    it('includes multiple rarities when multiple toggles are off', async () => {
      ;(el as unknown as { showCommon: boolean }).showCommon = false
      ;(el as unknown as { showRare: boolean }).showRare = false
      await el.updateComplete

      const graph = el.shadowRoot!.querySelector('mf-force-graph')!
      const hidden = (graph as unknown as { hiddenRarities: Set<string> }).hiddenRarities
      expect(hidden.has('common')).toBe(true)
      expect(hidden.has('rare')).toBe(true)
      expect(hidden.has('unusual')).toBe(false)
    })
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

  describe('second-order linkages', () => {
    it('adds cross-links between co-synonyms after lookup', async () => {
      vi.mocked(lookupWord).mockResolvedValue(mockResult)

      const searchBar = el.shadowRoot!.querySelector('mf-search-bar')
      searchBar?.dispatchEvent(new CustomEvent('mf-search', {
        detail: { word: 'fire' },
        bubbles: true,
        composed: true,
      }))

      await new Promise(r => setTimeout(r, 100))
      await el.updateComplete

      // "blaze" and "flame" share synset '1' — should have a cross-link
      const graphData = (el as any).graphData
      const crossLink = graphData.links.find(
        (l: any) =>
          (l.source === 'blaze' && l.target === 'flame') ||
          (l.source === 'flame' && l.target === 'blaze'),
      )
      expect(crossLink).toBeDefined()
    })

    it('fetches second-order data on mf-node-select', async () => {
      vi.mocked(lookupWord).mockResolvedValue(mockResult)

      // Initial lookup
      const searchBar = el.shadowRoot!.querySelector('mf-search-bar')
      searchBar?.dispatchEvent(new CustomEvent('mf-search', {
        detail: { word: 'fire' },
        bubbles: true,
        composed: true,
      }))
      await new Promise(r => setTimeout(r, 100))
      await el.updateComplete

      // Now select a node
      vi.mocked(lookupWord).mockResolvedValue(blazeLookup)
      const graph = el.shadowRoot!.querySelector('mf-force-graph')
      graph?.dispatchEvent(new CustomEvent('mf-node-select', {
        detail: { id: 'blaze', word: 'blaze', relationType: 'synonym', val: 4 },
        bubbles: true,
        composed: true,
      }))

      await new Promise(r => setTimeout(r, 100))
      await el.updateComplete

      expect(lookupWord).toHaveBeenCalledWith('blaze')
    })

    it('merges second-order nodes into graphData on select', async () => {
      vi.mocked(lookupWord).mockResolvedValue(mockResult)

      const searchBar = el.shadowRoot!.querySelector('mf-search-bar')
      searchBar?.dispatchEvent(new CustomEvent('mf-search', {
        detail: { word: 'fire' },
        bubbles: true,
        composed: true,
      }))
      await new Promise(r => setTimeout(r, 100))
      await el.updateComplete

      vi.mocked(lookupWord).mockResolvedValue(blazeLookup)
      const graph = el.shadowRoot!.querySelector('mf-force-graph')
      graph?.dispatchEvent(new CustomEvent('mf-node-select', {
        detail: { id: 'blaze', word: 'blaze', relationType: 'synonym', val: 4 },
        bubbles: true,
        composed: true,
      }))

      await new Promise(r => setTimeout(r, 100))
      await el.updateComplete

      // "inferno" should appear as a second-order node
      const graphData = (el as any).graphData
      const inferno = graphData.nodes.find((n: any) => n.word === 'inferno')
      expect(inferno).toBeDefined()
      expect(inferno.order).toBe(2)
    })

    it('strips previous second-order nodes when selecting a different node', async () => {
      vi.mocked(lookupWord).mockResolvedValue(mockResult)

      const searchBar = el.shadowRoot!.querySelector('mf-search-bar')
      searchBar?.dispatchEvent(new CustomEvent('mf-search', {
        detail: { word: 'fire' },
        bubbles: true,
        composed: true,
      }))
      await new Promise(r => setTimeout(r, 100))
      await el.updateComplete

      // Select "blaze" → adds "inferno" as order-2
      vi.mocked(lookupWord).mockResolvedValue(blazeLookup)
      const graph = el.shadowRoot!.querySelector('mf-force-graph')
      graph?.dispatchEvent(new CustomEvent('mf-node-select', {
        detail: { id: 'blaze', word: 'blaze', relationType: 'synonym', val: 4 },
        bubbles: true,
        composed: true,
      }))
      await new Promise(r => setTimeout(r, 100))
      await el.updateComplete

      // Select "flame" → strips "inferno", adds flame's second-order
      const flameLookup: LookupResult = {
        word: 'flame',
        senses: [{
          synset_id: '1',
          pos: 'noun',
          definition: 'fire',
          synonyms: [{ word: 'spark', synset_id: '20' }],
          relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
        }],
      }
      vi.mocked(lookupWord).mockResolvedValue(flameLookup)
      graph?.dispatchEvent(new CustomEvent('mf-node-select', {
        detail: { id: 'flame', word: 'flame', relationType: 'synonym', val: 4 },
        bubbles: true,
        composed: true,
      }))
      await new Promise(r => setTimeout(r, 100))
      await el.updateComplete

      const graphData = (el as any).graphData
      // "inferno" should be gone (was blaze's second-order)
      expect(graphData.nodes.find((n: any) => n.word === 'inferno')).toBeUndefined()
      // "spark" should be present (flame's second-order)
      expect(graphData.nodes.find((n: any) => n.word === 'spark')).toBeDefined()
    })

    it('logs a warning when second-order lookup fails', async () => {
      vi.mocked(lookupWord).mockResolvedValue(mockResult)

      const searchBar = el.shadowRoot!.querySelector('mf-search-bar')
      searchBar?.dispatchEvent(new CustomEvent('mf-search', {
        detail: { word: 'fire' },
        bubbles: true,
        composed: true,
      }))
      await new Promise(r => setTimeout(r, 100))
      await el.updateComplete

      const networkError = new Error('network timeout')
      vi.mocked(lookupWord).mockRejectedValueOnce(networkError)
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

      const graph = el.shadowRoot!.querySelector('mf-force-graph')
      graph?.dispatchEvent(new CustomEvent('mf-node-select', {
        detail: { id: 'blaze', word: 'blaze', relationType: 'synonym', val: 4 },
        bubbles: true,
        composed: true,
      }))

      await new Promise(r => setTimeout(r, 100))
      await el.updateComplete

      expect(warnSpy).toHaveBeenCalledOnce()
      expect(warnSpy.mock.calls[0][0]).toContain('second-order')
      // Should include contextual fields: node id/word and the error
      const args = warnSpy.mock.calls[0]
      expect(args).toEqual(
        expect.arrayContaining([expect.objectContaining({ nodeId: 'blaze', word: 'blaze' })]),
      )
      expect(args).toEqual(expect.arrayContaining([networkError]))

      warnSpy.mockRestore()
    })

    it('invalidates in-flight select when a new doLookup starts', async () => {
      vi.mocked(lookupWord).mockResolvedValue(mockResult)

      // Initial lookup
      const searchBar = el.shadowRoot!.querySelector('mf-search-bar')
      searchBar?.dispatchEvent(new CustomEvent('mf-search', {
        detail: { word: 'fire' },
        bubbles: true,
        composed: true,
      }))
      await new Promise(r => setTimeout(r, 100))
      await el.updateComplete

      // Start a slow select
      let resolveSelect!: (v: LookupResult) => void
      const selectPromise = new Promise<LookupResult>(r => { resolveSelect = r })
      vi.mocked(lookupWord).mockReturnValueOnce(selectPromise)

      const graph = el.shadowRoot!.querySelector('mf-force-graph')
      graph?.dispatchEvent(new CustomEvent('mf-node-select', {
        detail: { id: 'blaze', word: 'blaze', relationType: 'synonym', val: 4 },
        bubbles: true,
        composed: true,
      }))

      // Before select resolves, start a new central lookup
      const newResult: LookupResult = {
        word: 'water',
        senses: [{
          synset_id: '100',
          pos: 'noun',
          definition: 'H2O',
          synonyms: [{ word: 'aqua', synset_id: '100' }],
          relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
        }],
      }
      vi.mocked(lookupWord).mockResolvedValueOnce(newResult)
      ;(el as any).doLookup('water')
      await new Promise(r => setTimeout(r, 100))
      await el.updateComplete

      // Now the stale select resolves
      resolveSelect(blazeLookup)
      await new Promise(r => setTimeout(r, 100))
      await el.updateComplete

      // The stale select should NOT have merged "inferno" into the graph
      const graphData = (el as any).graphData
      expect(graphData.nodes.find((n: any) => n.word === 'inferno')).toBeUndefined()
      // Should still show the water graph
      expect(graphData.nodes.find((n: any) => n.word === 'aqua')).toBeDefined()
    })

    it('does not fetch second-order for the central node', async () => {
      vi.mocked(lookupWord).mockResolvedValue(mockResult)

      const searchBar = el.shadowRoot!.querySelector('mf-search-bar')
      searchBar?.dispatchEvent(new CustomEvent('mf-search', {
        detail: { word: 'fire' },
        bubbles: true,
        composed: true,
      }))
      await new Promise(r => setTimeout(r, 100))
      await el.updateComplete

      vi.mocked(lookupWord).mockClear()

      // Select the central node
      const graph = el.shadowRoot!.querySelector('mf-force-graph')
      graph?.dispatchEvent(new CustomEvent('mf-node-select', {
        detail: { id: 'fire', word: 'fire', relationType: 'central', val: 8 },
        bubbles: true,
        composed: true,
      }))
      await new Promise(r => setTimeout(r, 100))
      await el.updateComplete

      // Should NOT trigger a lookup for the central word
      expect(lookupWord).not.toHaveBeenCalled()
    })
  })
})

describe('mf-app grading mode', () => {
  let el: MfApp

  beforeEach(async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({ ok: true, status: 200 } as Response)
    localStorage.clear()
    window.location.hash = ''
    el = new MfApp()
    document.body.appendChild(el)
    await el.updateComplete
    // let probe resolve
    await new Promise(r => setTimeout(r, 50))
    await el.updateComplete
  })

  afterEach(() => {
    document.body.removeChild(el)
    vi.restoreAllMocks()
    window.location.hash = ''
    localStorage.clear()
  })

  it('shows toggle when probe returns 200', async () => {
    expect(el.shadowRoot!.querySelector('[data-testid="grade-toggle"]')).toBeTruthy()
  })

  it('hides toggle when probe returns 404', async () => {
    document.body.removeChild(el)
    vi.spyOn(global, 'fetch').mockResolvedValue({ ok: false, status: 404 } as Response)
    el = new MfApp()
    document.body.appendChild(el)
    await el.updateComplete
    await new Promise(r => setTimeout(r, 50))
    await el.updateComplete
    expect(el.shadowRoot!.querySelector('[data-testid="grade-toggle"]')).toBeFalsy()
  })

  it('forces mode to browse on handleAuthExpired', async () => {
    ;(el as any).mode = 'grade'
    await el.updateComplete
    ;(el as any).handleAuthExpired()
    await el.updateComplete
    expect((el as any).mode).toBe('browse')
    expect((el as any).errorMessage).toContain('Auth expired')
  })

  it('persists mode to localStorage on toggle click', async () => {
    const btn = el.shadowRoot!.querySelector('[data-testid="grade-toggle"]') as HTMLButtonElement
    expect(btn).toBeTruthy()
    btn.click()
    await el.updateComplete
    expect(localStorage.getItem('mf-mode')).toBeTruthy()
  })
})

describe('mf-app grade-mode integration', () => {
  let el: MfApp

  // Minimal stub for a grading fetch that returns the right shapes per endpoint
  function makeFetchStub() {
    return vi.spyOn(global, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      const url = input.toString()
      if (url.includes('/healthz')) {
        return { ok: true, status: 200, json: async () => ({}) } as Response
      }
      if (url.includes('/topics')) {
        return {
          ok: true, status: 200,
          json: async () => ({ topics: [{ topic: 'fire', topic_synset_id: 's1' }] }),
        } as Response
      }
      if (url.includes('/chains')) {
        return {
          ok: true, status: 200,
          json: async () => ({
            count: 1,
            records: [{
              schema_version: 'chain.v1',
              topic: 'fire', topic_synset_id: 's1',
              vehicle: 'blaze', vehicle_synset_id: 'v1',
              proposer: 'test', round: 1,
              chain: [{ phrase: 'fire', head: 'fire', synset_id: 's1' }, { phrase: 'blaze', head: 'blaze', synset_id: 'v1' }],
              chain_signature: 'sig1',
              generated_at: '2026-01-01T00:00:00Z',
            }],
          }),
        } as Response
      }
      if (url.includes('/judgements') && (input as Request).method === 'POST') {
        return {
          ok: true, status: 200,
          json: async () => ({ schema_version: 'judgement.v1', ts: '2026-01-01T00:00:00Z' }),
        } as Response
      }
      if (url.includes('/judgements')) {
        return {
          ok: true, status: 200,
          json: async () => ({ count: 0, records: [] }),
        } as Response
      }
      if (url.includes('/design-notes') && (input as Request).method === 'POST') {
        return { ok: true, status: 200, json: async () => ({ ts: '2026-01-01T00:00:00Z' }) } as Response
      }
      if (url.includes('/design-notes')) {
        return { ok: true, status: 200, json: async () => ({ content: 'existing note' }) } as Response
      }
      return { ok: false, status: 404, json: async () => ({}) } as Response
    })
  }

  beforeEach(async () => {
    makeFetchStub()
    localStorage.clear()
    window.location.hash = ''
    el = new MfApp()
    document.body.appendChild(el)
    await el.updateComplete
    // let probe resolve
    await new Promise(r => setTimeout(r, 50))
    await el.updateComplete
  })

  afterEach(() => {
    document.body.removeChild(el)
    vi.restoreAllMocks()
    window.location.hash = ''
    localStorage.clear()
  })

  it('renders mobile flat-text layout when viewportWidth < 900', async () => {
    ;(el as any).mode = 'grade'
    ;(el as any).viewportWidth = 600
    await el.updateComplete
    const mobileLayout = el.shadowRoot!.querySelector('[data-testid="grade-layout-mobile"]')
    expect(mobileLayout).not.toBeNull()
    const desktopLayout = el.shadowRoot!.querySelector('[data-testid="grade-layout"]')
    expect(desktopLayout).toBeNull()
  })

  it('renders desktop layout when viewportWidth >= 900', async () => {
    ;(el as any).mode = 'grade'
    ;(el as any).viewportWidth = 1200
    await el.updateComplete
    const desktopLayout = el.shadowRoot!.querySelector('[data-testid="grade-layout"]')
    expect(desktopLayout).not.toBeNull()
    const mobileLayout = el.shadowRoot!.querySelector('[data-testid="grade-layout-mobile"]')
    expect(mobileLayout).toBeNull()
  })

  it('mobile chain-card label shows snapped heads, not prose phrases (bad_head visibility)', async () => {
    ;(el as any).mode = 'grade'
    ;(el as any).viewportWidth = 600
    ;(el as any).pathFilter = 'both'
    ;(el as any).gradeChains = [{
      schema_version: 'chain.v1',
      topic: 'anchor', vehicle: 'habit',
      topic_synset_id: '', vehicle_synset_id: '',
      chain_signature: 'c'.repeat(64),
      chain: [
        { phrase: 'anchor', head: 'anchor', synset_id: '' },
        { phrase: 'resists change', head: 'resistance', synset_id: '' },
        { phrase: 'habit', head: 'habit', synset_id: '' },
      ],
      proposer: 'sonnet_v1', round: 1, generated_at: 'x',
    }]
    await el.updateComplete
    const card = el.shadowRoot!.querySelector('[data-testid="chain-card"]')!
    const text = card.textContent || ''
    expect(text).toContain('resistance')        // the snapped head
    expect(text).not.toContain('resists change') // not the prose phrase
  })

  it('topic-selected event fetches chains and judgements then populates gradeChains', async () => {
    ;(el as any).mode = 'grade'
    ;(el as any).viewportWidth = 600
    await el.updateComplete

    const picker = el.shadowRoot!.querySelector('mf-topic-picker')
    picker!.dispatchEvent(new CustomEvent('topic-selected', {
      detail: { topic: 'fire', topic_synset_id: 's1' },
      bubbles: true,
      composed: true,
    }))

    await new Promise(r => setTimeout(r, 50))
    await el.updateComplete

    const cards = el.shadowRoot!.querySelectorAll('[data-testid="chain-card"]')
    expect(cards.length).toBeGreaterThan(0)
    expect(cards[0].textContent).toContain('fire')
  })

  it('verdict-submit POSTs to judgements and clears selectedChain', async () => {
    ;(el as any).mode = 'grade'
    ;(el as any).viewportWidth = 600
    // Simulate a chain being loaded and selected
    ;(el as any).gradeChains = [{
      schema_version: 'chain.v1',
      topic: 'fire', topic_synset_id: 's1',
      vehicle: 'blaze', vehicle_synset_id: 'v1',
      proposer: 'test', round: 1,
      chain: [{ phrase: 'fire', head: 'fire', synset_id: 's1' }, { phrase: 'blaze', head: 'blaze', synset_id: 'v1' }],
      chain_signature: 'sig1',
      generated_at: '2026-01-01T00:00:00Z',
    }]
    ;(el as any).selectedChain = (el as any).gradeChains[0]
    await el.updateComplete

    const postSpy = vi.spyOn((el as any).gradingClient, 'postJudgement')

    const gradePanel = el.shadowRoot!.querySelector('mf-grade-panel')
    expect(gradePanel).not.toBeNull()
    gradePanel!.dispatchEvent(new CustomEvent('verdict-submit', {
      detail: { linkage: 'good', metaphor: 'live', tiers: ['strong', 'surprising'], confidence: 'high', notes: '' },
      bubbles: true,
      composed: true,
    }))

    await new Promise(r => setTimeout(r, 50))
    await el.updateComplete

    // The posted judgement is a v2 record built from the two-axis detail
    expect(postSpy).toHaveBeenCalledTimes(1)
    const posted = postSpy.mock.calls[0][0] as any
    expect(posted).toMatchObject({
      schema_version: 'judgement.v2',
      judged_by: 'julian',
      chain_signature: 'sig1',
      linkage: 'good',
      metaphor: 'live',
      confidence: 'high',
    })
    // tiers from the detail ride onto the posted v2 record verbatim
    expect(posted.tiers).toEqual(['strong', 'surprising'])
    expect(posted).not.toHaveProperty('label')
    expect(posted).not.toHaveProperty('tier')

    // After submit, selectedChain should be cleared
    expect((el as any).selectedChain).toBeNull()
  })

  it('desktop grade layout passes .mode, .gradeChains, .judgements, .viewportWidth to force-graph', async () => {
    ;(el as any).mode = 'grade'
    ;(el as any).viewportWidth = 1200
    ;(el as any).gradeChains = [{
      schema_version: 'chain.v1',
      topic: 'fire', topic_synset_id: 's1',
      vehicle: 'blaze', vehicle_synset_id: 'v1',
      proposer: 'test', round: 1,
      chain: [{ phrase: 'fire', head: 'fire', synset_id: 's1' }, { phrase: 'blaze', head: 'blaze', synset_id: 'v1' }],
      chain_signature: 'sig1',
      generated_at: '2026-01-01T00:00:00Z',
    }]
    ;(el as any).gradeJudgements = [{
      schema_version: 'judgement.v1', judged_by: 'julian', round: 1,
      topic: 'fire', topic_synset_id: 's1',
      vehicle: 'blaze', vehicle_synset_id: 'v1',
      proposer: 'test', chain_signature: 'sig1',
      label: 'live', confidence: 'high', notes: '', supersedes_ts: null,
    }]
    await el.updateComplete

    const desktopLayout = el.shadowRoot!.querySelector('[data-testid="grade-layout"]')
    expect(desktopLayout).not.toBeNull()

    const fg = el.shadowRoot!.querySelector('.grade-graph-pane mf-force-graph') as any
    expect(fg).not.toBeNull()
    expect(fg.mode).toBe('grade')
    expect(fg.gradeChains).toHaveLength(1)
    expect(fg.judgements).toHaveLength(1)
    expect(fg.viewportWidth).toBe(1200)
  })

  describe('tri-state path filter (C2 v2)', () => {
    it('renders an always-visible 3-way path filter in desktop grade view, defaulting to Both', async () => {
      ;(el as any).mode = 'grade'
      ;(el as any).viewportWidth = 1200
      await el.updateComplete

      const control = el.shadowRoot!.querySelector('[data-testid="path-filter"]')
      expect(control).not.toBeNull()
      const both = el.shadowRoot!.querySelector('[data-testid="path-filter-both"]') as HTMLButtonElement
      const ungraded = el.shadowRoot!.querySelector('[data-testid="path-filter-ungraded"]') as HTMLButtonElement
      const graded = el.shadowRoot!.querySelector('[data-testid="path-filter-graded"]') as HTMLButtonElement
      expect(both).not.toBeNull()
      expect(ungraded).not.toBeNull()
      expect(graded).not.toBeNull()
      expect((el as any).pathFilter).toBe('both')
      expect(both.getAttribute('aria-pressed')).toBe('true')
    })

    it('passes pathFilter="both" to force-graph by default', async () => {
      ;(el as any).mode = 'grade'
      ;(el as any).viewportWidth = 1200
      await el.updateComplete

      const fg = el.shadowRoot!.querySelector('.grade-graph-pane mf-force-graph') as any
      expect(fg.pathFilter).toBe('both')
    })

    it('clicking Ungraded sets pathFilter and threads it to force-graph', async () => {
      ;(el as any).mode = 'grade'
      ;(el as any).viewportWidth = 1200
      await el.updateComplete

      const ungraded = el.shadowRoot!.querySelector('[data-testid="path-filter-ungraded"]') as HTMLButtonElement
      ungraded.click()
      await el.updateComplete

      expect((el as any).pathFilter).toBe('ungraded')
      const fg = el.shadowRoot!.querySelector('.grade-graph-pane mf-force-graph') as any
      expect(fg.pathFilter).toBe('ungraded')
    })

    it('clicking Graded sets pathFilter="graded"', async () => {
      ;(el as any).mode = 'grade'
      ;(el as any).viewportWidth = 1200
      await el.updateComplete

      const graded = el.shadowRoot!.querySelector('[data-testid="path-filter-graded"]') as HTMLButtonElement
      graded.click()
      await el.updateComplete

      expect((el as any).pathFilter).toBe('graded')
      const graded2 = el.shadowRoot!.querySelector('[data-testid="path-filter-graded"]') as HTMLButtonElement
      expect(graded2.getAttribute('aria-pressed')).toBe('true')
    })

    it('renders the 3-way path filter in mobile grade view too', async () => {
      ;(el as any).mode = 'grade'
      ;(el as any).viewportWidth = 600
      await el.updateComplete

      const control = el.shadowRoot!.querySelector('[data-testid="path-filter"]')
      expect(control).not.toBeNull()
    })
  })

  describe('collapsible notes overlay (C1)', () => {
    it('hides mf-design-notes by default but shows the toggle on desktop grade view', async () => {
      ;(el as any).mode = 'grade'
      ;(el as any).viewportWidth = 1200
      await el.updateComplete

      // The collapse toggle is always visible
      const toggle = el.shadowRoot!.querySelector('[data-testid="notes-overlay-toggle"]')
      expect(toggle).not.toBeNull()

      // Collapsed by default — mf-design-notes is not rendered
      expect(el.shadowRoot!.querySelector('mf-design-notes')).toBeNull()
    })

    it('reveals mf-design-notes (with history threaded through) when the toggle is clicked', async () => {
      ;(el as any).mode = 'grade'
      ;(el as any).viewportWidth = 1200
      ;(el as any).notesHistory = 'existing note'
      await el.updateComplete

      const toggle = el.shadowRoot!.querySelector('[data-testid="notes-overlay-toggle"]') as HTMLButtonElement
      toggle.click()
      await el.updateComplete

      const notes = el.shadowRoot!.querySelector('mf-design-notes')
      expect(notes).not.toBeNull()
      expect((notes as any).history).toBe('existing note')
    })

    it('collapses again when the toggle is clicked a second time', async () => {
      ;(el as any).mode = 'grade'
      ;(el as any).viewportWidth = 1200
      await el.updateComplete

      const toggle = el.shadowRoot!.querySelector('[data-testid="notes-overlay-toggle"]') as HTMLButtonElement
      toggle.click()
      await el.updateComplete
      expect(el.shadowRoot!.querySelector('mf-design-notes')).not.toBeNull()

      toggle.click()
      await el.updateComplete
      expect(el.shadowRoot!.querySelector('mf-design-notes')).toBeNull()
    })

    it('no longer renders the bottom notes-row in the desktop flow', async () => {
      ;(el as any).mode = 'grade'
      ;(el as any).viewportWidth = 1200
      await el.updateComplete

      expect(el.shadowRoot!.querySelector('.grade-notes-row')).toBeNull()
    })
  })

  describe('pending-judgements queue (I2)', () => {
    const CHAIN = {
      schema_version: 'chain.v1' as const,
      topic: 'fire', topic_synset_id: 's1',
      vehicle: 'blaze', vehicle_synset_id: 'v1',
      proposer: 'test', round: 1,
      chain: [{ phrase: 'fire', head: 'fire', synset_id: 's1' }, { phrase: 'blaze', head: 'blaze', synset_id: 'v1' }],
      chain_signature: 'sig1',
      generated_at: '2026-01-01T00:00:00Z',
    }

    it('failed POST after retries pushes judgement to localStorage and sets banner', async () => {
      // Simulate exhausted retries — all POST calls fail with 500
      vi.spyOn(global, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
        const url = input.toString()
        if (url.includes('/healthz')) {
          return { ok: true, status: 200, json: async () => ({}) } as Response
        }
        if (url.includes('/judgements')) {
          return { ok: false, status: 500, json: async () => ({}) } as Response
        }
        return { ok: true, status: 200, json: async () => ({}) } as Response
      })

      ;(el as any).mode = 'grade'
      ;(el as any).selectedChain = CHAIN
      await el.updateComplete

      // Directly call the handler to bypass retry delays
      // We monkeypatch the client's postJudgement to throw immediately
      const clientSpy = vi.spyOn((el as any).gradingClient, 'postJudgement').mockRejectedValue(
        new Error('postJudgement: 500')
      )

      await (el as any).handleVerdictSubmit(
        new CustomEvent('verdict-submit', {
          detail: { linkage: 'good', metaphor: 'live', tiers: [], confidence: 'high', notes: '' },
          bubbles: true,
          composed: true,
        })
      )
      await el.updateComplete

      // Queue should have 1 entry
      expect((el as any).pendingQueue).toHaveLength(1)
      // localStorage should be written with a v2 record (two axes, no flat label)
      const stored = JSON.parse(localStorage.getItem('pending_judgements') ?? '[]')
      expect(stored).toHaveLength(1)
      expect(stored[0].chain_signature).toBe('sig1')
      expect(stored[0].schema_version).toBe('judgement.v2')
      expect(stored[0].linkage).toBe('good')
      expect(stored[0].metaphor).toBe('live')
      expect(stored[0]).not.toHaveProperty('label')
      // Banner should mention pending
      expect((el as any).errorMessage).toContain('pending')
      // selectedChain cleared so grading can continue
      expect((el as any).selectedChain).toBeNull()

      clientSpy.mockRestore()
    })

    it('successful POST flushes the pending queue', async () => {
      // Pre-populate the queue with one pending entry
      const pendingJudgement = {
        schema_version: 'judgement.v2' as const,
        judged_by: 'julian', round: 1,
        topic: 'fire', topic_synset_id: 's1',
        vehicle: 'smoke', vehicle_synset_id: 'v2',
        proposer: 'test', chain_signature: 'sig_pending',
        linkage: 'good' as const, metaphor: 'dead' as const, tiers: [],
        confidence: 'high' as const, notes: '', supersedes_ts: null,
      }
      ;(el as any).pendingQueue = [pendingJudgement]
      ;(el as any).savePendingQueue()

      ;(el as any).mode = 'grade'
      ;(el as any).selectedChain = CHAIN
      await el.updateComplete

      // POST succeeds for both the current judgement and the pending one
      const clientSpy = vi.spyOn((el as any).gradingClient, 'postJudgement').mockResolvedValue({
        schema_version: 'judgement.v2', ts: '2026-01-01T00:00:00Z',
      } as any)
      const getJudgementsSpy = vi.spyOn((el as any).gradingClient, 'getJudgements').mockResolvedValue({ count: 0, records: [] })

      await (el as any).handleVerdictSubmit(
        new CustomEvent('verdict-submit', {
          detail: { linkage: 'good', metaphor: 'live', tiers: [], confidence: 'high', notes: '' },
          bubbles: true,
          composed: true,
        })
      )
      await el.updateComplete

      // Queue should now be empty
      expect((el as any).pendingQueue).toHaveLength(0)
      const stored = JSON.parse(localStorage.getItem('pending_judgements') ?? '[]')
      expect(stored).toHaveLength(0)

      clientSpy.mockRestore()
      getJudgementsSpy.mockRestore()
    })

    it('initGradeMode loads pending queue from localStorage', async () => {
      const existing = [{ schema_version: 'judgement.v1', chain_signature: 'queued1' }]
      localStorage.setItem('pending_judgements', JSON.stringify(existing))

      // Trigger initGradeMode by calling it directly
      ;(el as any).pendingQueue = []
      await (el as any).initGradeMode()

      expect((el as any).pendingQueue).toHaveLength(1)
      expect((el as any).pendingQueue[0].chain_signature).toBe('queued1')
    })
  })

  it('401 from postJudgement forces browse mode and sets errorMessage', async () => {
    // Override the fetch mock so any call to /judgements returns 401
    // (GradingClient.postJudgement calls fetch(url, {method:'POST'}) — the 4xx branch
    // throws immediately without retry, which propagates to handleVerdictSubmit)
    vi.spyOn(global, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      const url = input.toString()
      if (url.includes('/judgements')) {
        return { ok: false, status: 401, json: async () => ({}) } as Response
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response
    })

    ;(el as any).mode = 'grade'
    ;(el as any).selectedChain = {
      schema_version: 'chain.v1',
      topic: 'fire', topic_synset_id: 's1',
      vehicle: 'blaze', vehicle_synset_id: 'v1',
      proposer: 'test', round: 1,
      chain: [{ phrase: 'fire', head: 'fire', synset_id: 's1' }],
      chain_signature: 'sig1',
      generated_at: '2026-01-01T00:00:00Z',
    }
    await el.updateComplete

    // Directly call the handler — this avoids depending on DOM event routing
    await (el as any).handleVerdictSubmit(
      new CustomEvent('verdict-submit', {
        detail: { linkage: 'good', metaphor: 'live', tiers: [], confidence: 'high', notes: '' },
        bubbles: true,
        composed: true,
      })
    )
    await el.updateComplete

    expect((el as any).mode).toBe('browse')
    expect((el as any).errorMessage).toContain('Auth expired')
  })

  describe('prior notes in re-grade banner (C3)', () => {
    const chain = {
      schema_version: 'chain.v1' as const,
      topic: 'fire', topic_synset_id: 's1',
      vehicle: 'blaze', vehicle_synset_id: 'v1',
      proposer: 'test', round: 1,
      chain: [{ phrase: 'fire', head: 'fire', synset_id: 's1' }, { phrase: 'blaze', head: 'blaze', synset_id: 'v1' }],
      chain_signature: 'sig1',
      generated_at: '2026-01-01T00:00:00Z',
    }

    // v2 judgement factory — the two axes + multi-select tiers replace the flat label.
    const judgement = (overrides: Record<string, unknown>) => ({
      schema_version: 'judgement.v2', judged_by: 'julian', round: 1,
      topic: 'fire', topic_synset_id: 's1',
      vehicle: 'blaze', vehicle_synset_id: 'v1',
      proposer: 'test', chain_signature: 'sig1',
      linkage: 'good', metaphor: 'dead', tiers: [],
      confidence: 'high', notes: '', supersedes_ts: null,
      ...overrides,
    })

    it('threads the latest judgement axes, tiers and notes into the priorVerdict prop', async () => {
      ;(el as any).mode = 'grade'
      ;(el as any).viewportWidth = 1200
      ;(el as any).gradeChains = [chain]
      ;(el as any).gradeJudgements = [
        judgement({ linkage: 'bad', metaphor: 'live', notes: 'first pass — padding', ts: '2026-05-30T00:00:00Z' }),
        judgement({ linkage: 'good', metaphor: 'live', tiers: ['strong', 'surprising'], notes: 'merge: too literal', ts: '2026-05-31T00:00:00Z' }),
      ]
      ;(el as any).selectedChain = chain
      await el.updateComplete

      const panel = el.shadowRoot!.querySelector('mf-grade-panel') as any
      expect(panel).not.toBeNull()
      expect(panel.priorVerdict).not.toBeNull()
      expect(panel.priorVerdict).toMatchObject({
        linkage: 'good', metaphor: 'live', notes: 'merge: too literal',
      })
      expect(panel.priorVerdict.tiers).toEqual(['strong', 'surprising'])
      expect(panel.priorVerdict.ts).toBe('2026-05-31T00:00:00Z')
      expect(panel.priorVerdict).not.toHaveProperty('label')
    })

    it('maps a stored v1 label into the v2 priorVerdict shape via normaliseJudgement', async () => {
      ;(el as any).mode = 'grade'
      ;(el as any).viewportWidth = 1200
      ;(el as any).gradeChains = [chain]
      // A legacy v1 record carrying `label` (no axes) — read-compat path.
      ;(el as any).gradeJudgements = [{
        schema_version: 'judgement.v1', judged_by: 'julian', round: 1,
        topic: 'fire', topic_synset_id: 's1', vehicle: 'blaze', vehicle_synset_id: 'v1',
        proposer: 'test', chain_signature: 'sig1',
        label: 'dead', confidence: 'high', notes: 'old pass', ts: '2026-05-31T00:00:00Z', supersedes_ts: null,
      }]
      ;(el as any).selectedChain = chain
      await el.updateComplete

      const panel = el.shadowRoot!.querySelector('mf-grade-panel') as any
      expect(panel.priorVerdict).toMatchObject({
        linkage: 'good', metaphor: 'dead', notes: 'old pass',
      })
      expect(panel.priorVerdict.tiers).toEqual([])
    })

    it('threads confidence and tags into the priorVerdict prop', async () => {
      ;(el as any).mode = 'grade'
      ;(el as any).viewportWidth = 1200
      ;(el as any).gradeChains = [chain]
      ;(el as any).gradeJudgements = [
        judgement({ confidence: 'med', tags: ['leap', 'bad_head'], ts: '2026-05-31T00:00:00Z' }),
      ]
      ;(el as any).selectedChain = chain
      await el.updateComplete
      const panel = el.shadowRoot!.querySelector('mf-grade-panel') as any
      expect(panel.priorVerdict.confidence).toBe('med')
      expect(panel.priorVerdict.tags).toEqual(['leap', 'bad_head'])
    })

    it('a re-grade sets supersedes_ts to the prior verdict ts', async () => {
      ;(el as any).mode = 'grade'
      ;(el as any).gradeChains = [chain]
      ;(el as any).gradeJudgements = [judgement({ ts: '2026-05-30T00:00:00Z' })]
      ;(el as any).selectedChain = chain
      await el.updateComplete
      const postSpy = vi.spyOn((el as any).gradingClient, 'postJudgement').mockResolvedValue({} as any)
      vi.spyOn((el as any).gradingClient, 'getJudgements').mockResolvedValue({ count: 0, records: [] })
      await (el as any).handleVerdictSubmit(new CustomEvent('verdict-submit', {
        detail: { linkage: 'good', metaphor: 'dead', tiers: [], tags: [], confidence: 'high', notes: '' },
      }))
      expect(postSpy.mock.calls[0][0].supersedes_ts).toBe('2026-05-30T00:00:00Z')
      postSpy.mockRestore()
    })

    it('a first grade (no prior) sets supersedes_ts null', async () => {
      ;(el as any).mode = 'grade'
      ;(el as any).gradeChains = [chain]
      ;(el as any).gradeJudgements = []
      ;(el as any).selectedChain = chain
      await el.updateComplete
      const postSpy = vi.spyOn((el as any).gradingClient, 'postJudgement').mockResolvedValue({} as any)
      vi.spyOn((el as any).gradingClient, 'getJudgements').mockResolvedValue({ count: 0, records: [] })
      await (el as any).handleVerdictSubmit(new CustomEvent('verdict-submit', {
        detail: { linkage: 'good', metaphor: 'live', tiers: [], tags: [], confidence: 'high', notes: '' },
      }))
      expect(postSpy.mock.calls[0][0].supersedes_ts).toBeNull()
      postSpy.mockRestore()
    })

    it('threads empty notes when the latest judgement has none', async () => {
      ;(el as any).mode = 'grade'
      ;(el as any).viewportWidth = 1200
      ;(el as any).gradeChains = [chain]
      ;(el as any).gradeJudgements = [judgement({ linkage: 'good', metaphor: 'live', notes: '', ts: '2026-05-31T00:00:00Z' })]
      ;(el as any).selectedChain = chain
      await el.updateComplete

      const panel = el.shadowRoot!.querySelector('mf-grade-panel') as any
      expect(panel.priorVerdict.notes).toBe('')
    })
  })
})

describe('mf-app walk view', () => {
  let el: MfApp

  function walkEntry(topic: string, sig: string, dwellIndex: number, dwellN: number) {
    return {
      chain_signature: sig, topic, vehicle: 'v', dwell_index: dwellIndex, dwell_n: dwellN,
      record: {
        schema_version: 'chain.v1',
        topic, topic_synset_id: 's1', vehicle: 'v', vehicle_synset_id: 'v1',
        proposer: 't', round: 2,
        chain: [{ phrase: topic, head: topic, synset_id: 's1' }, { phrase: 'v', head: 'v', synset_id: 'v1' }],
        chain_signature: sig, generated_at: '2026-01-01T00:00:00Z',
      },
    }
  }

  function makeWalkFetchStub(
    entries: ReturnType<typeof walkEntry>[],
    opts: { judgements?: any[]; walkFails?: boolean } = {},
  ) {
    const judgements = opts.judgements ?? []
    return vi.spyOn(global, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      const url = input.toString()
      const method = (input as Request).method
      if (url.includes('/healthz')) return { ok: true, status: 200, json: async () => ({}) } as Response
      if (url.includes('/topics')) return { ok: true, status: 200, json: async () => ({ topics: [{ topic: 'anger', topic_synset_id: 's1' }] }) } as Response
      if (url.includes('/walk')) {
        if (opts.walkFails) return { ok: false, status: 500, json: async () => ({}) } as Response
        return { ok: true, status: 200, json: async () => ({ count: entries.length, entries }) } as Response
      }
      if (url.includes('/judgements') && method === 'POST') return { ok: true, status: 200, json: async () => ({ schema_version: 'judgement.v2', ts: '2026-01-01T00:00:00Z' }) } as Response
      if (url.includes('/judgements')) return { ok: true, status: 200, json: async () => ({ count: judgements.length, records: judgements }) } as Response
      if (url.includes('/design-notes')) return { ok: true, status: 200, json: async () => ({ content: '' }) } as Response
      return { ok: false, status: 404, json: async () => ({}) } as Response
    })
  }

  async function mountGradeDesktop(
    entries: ReturnType<typeof walkEntry>[],
    opts: { judgements?: any[]; walkFails?: boolean } = {},
  ): Promise<MfApp> {
    makeWalkFetchStub(entries, opts)
    localStorage.clear()
    window.location.hash = ''
    const app = new MfApp()
    document.body.appendChild(app)
    await app.updateComplete
    await new Promise(r => setTimeout(r, 50))
    ;(app as any).mode = 'grade'
    ;(app as any).viewportWidth = 1200
    await app.updateComplete
    return app
  }

  async function enterWalk(app: MfApp): Promise<void> {
    const btn = app.shadowRoot!.querySelector('[data-testid="grade-view-walk"]') as HTMLButtonElement
    btn.click()
    await new Promise(r => setTimeout(r, 0))
    await app.updateComplete
  }

  afterEach(() => {
    if (el && el.parentNode) document.body.removeChild(el)
    vi.restoreAllMocks()
    window.location.hash = ''
    localStorage.clear()
  })

  it('a grade-view toggle is offered in topic view', async () => {
    el = await mountGradeDesktop([walkEntry('anger', 's1', 0, 1)])
    expect(el.shadowRoot!.querySelector('[data-testid="grade-view-walk"]')).not.toBeNull()
    expect(el.shadowRoot!.querySelector('[data-testid="grade-view-topic"]')).not.toBeNull()
  })

  it('entering walk fetches the walk and renders the shell on the first chain', async () => {
    el = await mountGradeDesktop([walkEntry('anger', 's1', 0, 2), walkEntry('anger', 's2', 1, 2)])
    await enterWalk(el)
    expect(el.shadowRoot!.querySelector('[data-testid="grade-walk-layout"]')).not.toBeNull()
    const walk = el.shadowRoot!.querySelector('mf-grade-walk') as any
    expect(walk.chain.chain_signature).toBe('s1')
    expect(walk.total).toBe(2)
  })

  it('persists the grade view to localStorage', async () => {
    el = await mountGradeDesktop([walkEntry('anger', 's1', 0, 1)])
    await enterWalk(el)
    expect(localStorage.getItem('mf-grade-view')).toBe('walk')
  })

  it('shows the force-graph context on desktop but not on mobile', async () => {
    el = await mountGradeDesktop([walkEntry('anger', 's1', 0, 1)])
    await enterWalk(el)
    expect(el.shadowRoot!.querySelector('[data-testid="grade-walk-layout"] mf-force-graph')).not.toBeNull()
    ;(el as any).viewportWidth = 500
    await el.updateComplete
    expect(el.shadowRoot!.querySelector('mf-force-graph')).toBeNull()
    expect(el.shadowRoot!.querySelector('mf-grade-walk')).not.toBeNull()
  })

  it('mobile walk uses a scroll container, not the clipped desktop grade-main', async () => {
    el = await mountGradeDesktop([walkEntry('anger', 's1', 0, 1)])
    await enterWalk(el)
    ;(el as any).viewportWidth = 500
    await el.updateComplete
    const layout = el.shadowRoot!.querySelector('[data-testid="grade-walk-layout"]')!
    // .grade-main is the desktop graph row (flex:1; overflow:hidden) — must NOT wrap the
    // mobile shell, or the panel clips with no scroll. Mobile uses a scrollable region.
    expect(layout.querySelector('.grade-main')).toBeNull()
    expect(layout.querySelector('.grade-walk-scroll')).not.toBeNull()
    expect(layout.querySelector('.grade-walk-scroll mf-grade-walk')).not.toBeNull()
  })

  it('walk-next advances to the next chain', async () => {
    el = await mountGradeDesktop([walkEntry('anger', 's1', 0, 2), walkEntry('anger', 's2', 1, 2)])
    await enterWalk(el)
    el.shadowRoot!.querySelector('mf-grade-walk')!.dispatchEvent(new CustomEvent('walk-next', { bubbles: true, composed: true }))
    await el.updateComplete
    const walk = el.shadowRoot!.querySelector('mf-grade-walk') as any
    expect(walk.chain.chain_signature).toBe('s2')
    expect((el as any).selectedChain.chain_signature).toBe('s2')
  })

  it('submitting a verdict advances past the graded chain (which stays reviewable)', async () => {
    el = await mountGradeDesktop([walkEntry('anger', 's1', 0, 2), walkEntry('anger', 's2', 1, 2)])
    await enterWalk(el)
    el.shadowRoot!.querySelector('mf-grade-walk')!.dispatchEvent(new CustomEvent('verdict-submit', {
      detail: { linkage: 'good', metaphor: 'live', tiers: [], tags: [], confidence: 'high', notes: '' },
      bubbles: true, composed: true,
    }))
    await new Promise(r => setTimeout(r, 0))
    await el.updateComplete
    const walk = el.shadowRoot!.querySelector('mf-grade-walk') as any
    expect(walk.chain.chain_signature).toBe('s2')         // advanced to the next ungraded
    expect(walk.total).toBe(2)                            // s1 stays addressable (Prev can review it)
    expect([...(el as any).walkGradedSigs]).toContain('s1')
  })

  it('Prev returns to the chain just graded (for review)', async () => {
    el = await mountGradeDesktop([walkEntry('anger', 's1', 0, 2), walkEntry('anger', 's2', 1, 2)])
    await enterWalk(el)
    el.shadowRoot!.querySelector('mf-grade-walk')!.dispatchEvent(new CustomEvent('verdict-submit', {
      detail: { linkage: 'good', metaphor: 'live', tiers: [], tags: [], confidence: 'high', notes: '' },
      bubbles: true, composed: true,
    }))
    await new Promise(r => setTimeout(r, 0))
    await el.updateComplete
    expect((el.shadowRoot!.querySelector('mf-grade-walk') as any).chain.chain_signature).toBe('s2')
    el.shadowRoot!.querySelector('mf-grade-walk')!.dispatchEvent(new CustomEvent('walk-prev', { bubbles: true, composed: true }))
    await el.updateComplete
    const walk = el.shadowRoot!.querySelector('mf-grade-walk') as any
    expect(walk.chain.chain_signature).toBe('s1')         // back to the chain we just graded
    expect(walk.graded).toBe(true)
  })

  it('shows an empty state when the walk has no ungraded chains', async () => {
    el = await mountGradeDesktop([])
    await enterWalk(el)
    expect(el.shadowRoot!.querySelector('[data-testid="walk-empty"]')).not.toBeNull()
  })

  it('walk-prev steps back to the previous chain', async () => {
    el = await mountGradeDesktop([walkEntry('anger', 's1', 0, 2), walkEntry('anger', 's2', 1, 2)])
    await enterWalk(el)
    el.shadowRoot!.querySelector('mf-grade-walk')!.dispatchEvent(new CustomEvent('walk-next', { bubbles: true, composed: true }))
    await el.updateComplete
    expect((el.shadowRoot!.querySelector('mf-grade-walk') as any).chain.chain_signature).toBe('s2')
    el.shadowRoot!.querySelector('mf-grade-walk')!.dispatchEvent(new CustomEvent('walk-prev', { bubbles: true, composed: true }))
    await el.updateComplete
    expect((el.shadowRoot!.querySelector('mf-grade-walk') as any).chain.chain_signature).toBe('s1')
    expect((el as any).walkPos).toBe(0)
  })

  it('surfaces an error and no shell when the walk fails to load', async () => {
    el = await mountGradeDesktop([], { walkFails: true })
    await enterWalk(el)
    expect((el as any).errorMessage).toBe('Failed to load walk')
    expect(el.shadowRoot!.querySelector('mf-grade-walk')).toBeNull()
  })

  it('Next skips graded chains by default; skip-off steps through them', async () => {
    el = await mountGradeDesktop([walkEntry('anger', 's1', 0, 3), walkEntry('anger', 's2', 1, 3), walkEntry('anger', 's3', 2, 3)])
    await enterWalk(el)
    // grade s1 -> auto-advance over it to s2
    el.shadowRoot!.querySelector('mf-grade-walk')!.dispatchEvent(new CustomEvent('verdict-submit', {
      detail: { linkage: 'good', metaphor: 'live', tiers: [], tags: [], confidence: 'high', notes: '' },
      bubbles: true, composed: true,
    }))
    await new Promise(r => setTimeout(r, 0))
    await el.updateComplete
    expect((el.shadowRoot!.querySelector('mf-grade-walk') as any).chain.chain_signature).toBe('s2')
    // Prev back to the graded s1, then Next (skip ON) jumps over s1 to s2
    el.shadowRoot!.querySelector('mf-grade-walk')!.dispatchEvent(new CustomEvent('walk-prev', { bubbles: true, composed: true }))
    await el.updateComplete
    expect((el.shadowRoot!.querySelector('mf-grade-walk') as any).chain.chain_signature).toBe('s1')
    el.shadowRoot!.querySelector('mf-grade-walk')!.dispatchEvent(new CustomEvent('walk-next', { bubbles: true, composed: true }))
    await el.updateComplete
    expect((el.shadowRoot!.querySelector('mf-grade-walk') as any).chain.chain_signature).toBe('s2')
    // skip OFF: from s1, Next steps to the literal next (s1 -> s2 still, but now graded ones are not skipped)
    el.shadowRoot!.querySelector('mf-grade-walk')!.dispatchEvent(new CustomEvent('walk-prev', { bubbles: true, composed: true }))
    await el.updateComplete // back to s1
    el.shadowRoot!.querySelector('mf-grade-walk')!.dispatchEvent(new CustomEvent('walk-skip-toggle', { bubbles: true, composed: true }))
    await el.updateComplete
    el.shadowRoot!.querySelector('mf-grade-walk')!.dispatchEvent(new CustomEvent('walk-next', { bubbles: true, composed: true }))
    await el.updateComplete
    expect((el.shadowRoot!.querySelector('mf-grade-walk') as any).chain.chain_signature).toBe('s2')
  })

  it('decrements the ungraded-remaining count as chains are graded', async () => {
    el = await mountGradeDesktop([walkEntry('anger', 's1', 0, 2), walkEntry('anger', 's2', 1, 2)])
    await enterWalk(el)
    expect((el.shadowRoot!.querySelector('mf-grade-walk') as any).ungradedLeft).toBe(2)
    el.shadowRoot!.querySelector('mf-grade-walk')!.dispatchEvent(new CustomEvent('verdict-submit', {
      detail: { linkage: 'good', metaphor: 'live', tiers: [], tags: [], confidence: 'high', notes: '' },
      bubbles: true, composed: true,
    }))
    await new Promise(r => setTimeout(r, 0))
    await el.updateComplete
    expect((el.shadowRoot!.querySelector('mf-grade-walk') as any).ungradedLeft).toBe(1)
  })

  it('disables Next when no ungraded chains remain ahead', async () => {
    el = await mountGradeDesktop([walkEntry('anger', 's1', 0, 1)])
    await enterWalk(el)
    el.shadowRoot!.querySelector('mf-grade-walk')!.dispatchEvent(new CustomEvent('verdict-submit', {
      detail: { linkage: 'good', metaphor: 'live', tiers: [], tags: [], confidence: 'high', notes: '' },
      bubbles: true, composed: true,
    }))
    await new Promise(r => setTimeout(r, 0))
    await el.updateComplete
    const walk = el.shadowRoot!.querySelector('mf-grade-walk') as any
    expect(walk.canNext).toBe(false)   // s1 graded, nothing ahead — but it stays reviewable
    expect(walk.graded).toBe(true)
  })

  it('prefills the prior verdict in walk mode from the GLOBAL judgement set', async () => {
    // skip OFF so a session/prior-graded chain stays visible; its prior verdict must echo.
    const prior = {
      schema_version: 'judgement.v2', ts: '2026-05-31T00:00:00Z', judged_by: 'julian', round: 2,
      topic: 'anger', topic_synset_id: 's1', vehicle: 'v', vehicle_synset_id: 'v1', proposer: 't',
      chain_signature: 's1', linkage: 'good', metaphor: 'live', tiers: [], tags: [], confidence: 'high', notes: '',
    }
    el = await mountGradeDesktop([walkEntry('anger', 's1', 0, 1)], { judgements: [prior] })
    await enterWalk(el)
    const panel = el.shadowRoot!.querySelector('mf-grade-walk')!.shadowRoot!.querySelector('mf-grade-panel') as any
    expect(panel.priorVerdict).not.toBeNull()
    expect(panel.priorVerdict.metaphor).toBe('live')
  })

  it('does not render triage priors (liveness/flags) even if an entry carries them', async () => {
    // defensive: the server strips priors, but a stray field must never reach the DOM.
    const leaky = { ...walkEntry('anger', 's1', 0, 1), liveness: 9, bad_head: true, leap: true, weak_linkage: true }
    el = await mountGradeDesktop([leaky as any])
    await enterWalk(el)
    const text = el.shadowRoot!.querySelector('[data-testid="grade-walk-layout"]')!.textContent ?? ''
    expect(text).not.toMatch(/bad_head|weak_linkage|liveness/)
  })
})
