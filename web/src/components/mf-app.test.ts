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
    synonyms: [
      { word: 'blaze', synset_id: '1' },
      { word: 'flame', synset_id: '1' },
    ],
    relations: { hypernyms: [], hyponyms: [], similar: [] },
  }],
}

const blazeLookup: LookupResult = {
  word: 'blaze',
  senses: [{
    synset_id: '1',
    pos: 'noun',
    definition: 'a strong flame',
    synonyms: [{ word: 'inferno', synset_id: '10' }],
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
        relations: { hypernyms: [], hyponyms: [], similar: [] },
      }],
    }
    const fastResult: LookupResult = {
      word: 'fast',
      senses: [{
        synset_id: '2',
        pos: 'adjective',
        definition: 'moving quickly',
        synonyms: [],
        relations: { hypernyms: [], hyponyms: [], similar: [] },
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
          relations: { hypernyms: [], hyponyms: [], similar: [] },
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
          relations: { hypernyms: [], hyponyms: [], similar: [] },
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
