import { describe, it, expect, vi, beforeEach } from 'vitest'
import { lookupWord, autocompleteWord, ApiError, fetchForest, ForestError } from './client'
import patienceForest from '@/fixtures/forest-patience.json'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('lookupWord', () => {
  it('returns LookupResult on success', async () => {
    const mockResult = { word: 'test', senses: [] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResult),
    }))
    const result = await lookupWord('test')
    expect(result).toEqual(mockResult)
  })

  it('trims and lowercases the word before fetching', async () => {
    const mockResult = { word: 'hello', senses: [] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResult),
    }))
    await lookupWord('  HELLO  ')
    expect(fetch).toHaveBeenCalledWith('/thesaurus/lookup?word=hello')
  })

  it('throws ApiError with status on HTTP error with JSON body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ error: 'Word not found' }),
    }))
    await expect(lookupWord('xyzzy')).rejects.toThrow(ApiError)
    try {
      await lookupWord('xyzzy')
    } catch (e) {
      expect((e as ApiError).status).toBe(404)
      expect((e as ApiError).message).toBe('Word not found')
    }
  })

  it('throws ApiError on HTTP error with non-JSON body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error('not json')),
    }))
    await expect(lookupWord('test')).rejects.toThrow(ApiError)
  })

  it('throws ApiError on invalid response shape', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ unexpected: 'data' }),
    }))
    await expect(lookupWord('test')).rejects.toThrow(ApiError)
  })
})

describe('autocompleteWord', () => {
  it('returns suggestions on success', async () => {
    const mockSuggestions = [
      { word: 'fire', definition: 'the event of something burning', sense_count: 21, rarity: 'common' },
      { word: 'firearm', definition: 'a portable gun', sense_count: 1, rarity: 'unusual' },
    ]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ suggestions: mockSuggestions }),
    }))
    const result = await autocompleteWord('fir')
    expect(result).toEqual(mockSuggestions)
  })

  it('trims and lowercases the prefix before fetching', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ suggestions: [] }),
    }))
    await autocompleteWord('  FIR  ')
    expect(fetch).toHaveBeenCalledWith('/thesaurus/autocomplete?prefix=fir&limit=10')
  })

  it('returns empty array when no matches', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ suggestions: [] }),
    }))
    const result = await autocompleteWord('xyzzy')
    expect(result).toEqual([])
  })

  it('throws ApiError on HTTP error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ error: 'prefix must be at least 2 characters' }),
    }))
    await expect(autocompleteWord('a')).rejects.toThrow(ApiError)
  })

  it('throws ApiError on invalid response shape', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ unexpected: 'data' }),
    }))
    await expect(autocompleteWord('fir')).rejects.toThrow(ApiError)
  })
})

// Rule: every outcome of GET /forge/forest other than a contract-valid 200
// reaches the caller as one ForestError kind (never a raw server message),
// except our own abort, which stays an AbortError so the caller can drop it.
describe('fetchForest', () => {
  const okResponse = (body: unknown) => ({
    ok: true,
    status: 200,
    headers: new Headers(),
    json: () => Promise.resolve(body),
  })
  const errResponse = (status: number, headers: Record<string, string> = {}) => ({
    ok: false,
    status,
    headers: new Headers(headers),
    json: () => Promise.resolve({ error: 'server text that must never reach the UI' }),
  })

  it('requests the word and max_hops, and returns a contract-valid body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(patienceForest)))
    const result = await fetchForest('dormant seed', 4)
    expect(result.source).toBe('patience')
    expect(result.endpoints.length).toBe(9)
    expect(fetch).toHaveBeenCalledWith('/forge/forest?word=dormant%20seed&max_hops=4', { signal: undefined })
  })

  it('passes the abort signal through to fetch', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(patienceForest)))
    const controller = new AbortController()
    await fetchForest('patience', 3, controller.signal)
    expect(fetch).toHaveBeenCalledWith(expect.any(String), { signal: controller.signal })
  })

  it.each([
    [400, 'invalid-word'],
    [429, 'busy'],
    [502, 'failed'],
    [503, 'not-configured'],
    [504, 'timeout'],
    [500, 'failed'],
    [418, 'failed'],
  ] as const)('maps HTTP %i to the %s kind', async (status, kind) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(errResponse(status)))
    const err = await fetchForest('patience', 3).catch(e => e)
    expect(err).toBeInstanceOf(ForestError)
    expect(err.kind).toBe(kind)
    expect(err.status).toBe(status)
    expect(err.message).not.toContain('server text')
  })

  it('reads Retry-After seconds on a 429', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(errResponse(429, { 'Retry-After': '12' })))
    const err = await fetchForest('patience', 3).catch(e => e)
    expect(err.retryAfterSeconds).toBe(12)
  })

  it.each([[{}], [{ 'Retry-After': 'soon' }], [{ 'Retry-After': '0' }]])(
    'leaves retryAfterSeconds null when Retry-After is missing or unusable (%o)',
    async headers => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(errResponse(429, headers)))
      const err = await fetchForest('patience', 3).catch(e => e)
      expect(err.kind).toBe('busy')
      expect(err.retryAfterSeconds).toBeNull()
    },
  )

  it('maps a fetch rejection (offline, DNS, CORS) to the network kind', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const err = await fetchForest('patience', 3).catch(e => e)
    expect(err).toBeInstanceOf(ForestError)
    expect(err.kind).toBe('network')
  })

  it('rethrows our own abort unchanged so the caller can drop it', async () => {
    const abort = new DOMException('The operation was aborted.', 'AbortError')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abort))
    const err = await fetchForest('patience', 3).catch(e => e)
    expect(err).toBe(abort)
  })

  it.each([
    ['no endpoints array', { ...patienceForest, endpoints: undefined }],
    ['an endpoint path that does not start at the source', {
      ...patienceForest,
      // every word is a real node, so only the starts-at-source rule can reject it
      endpoints: [{ ...patienceForest.endpoints[3], path: ['dormant seed', 'seed vault'], grounds: ['stays viable for centuries'] }],
    }],
    ['grounds that do not match the path length', {
      ...patienceForest,
      endpoints: [{ ...patienceForest.endpoints[3], grounds: ['only one'] }],
    }],
    ['a non-numeric score', {
      ...patienceForest,
      endpoints: [{ ...patienceForest.endpoints[0], score: 'eight' }],
    }],
    ['an edge to an unknown node', {
      ...patienceForest,
      edges: [...patienceForest.edges, { source: 'patience', target: 'ghost', grounds: ['x'] }],
    }],
  ])('treats a 200 with %s as a failed forest, never as data', async (_label, body) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(body)))
    const err = await fetchForest('patience', 3).catch(e => e)
    expect(err).toBeInstanceOf(ForestError)
    expect(err.kind).toBe('failed')
  })

  it('accepts an empty forest (source node only, no edges or endpoints)', async () => {
    const empty = {
      ...patienceForest,
      nodes: [patienceForest.nodes[0]],
      edges: [],
      endpoints: [],
      stats: { generated: 12, kept: 0, rejected: { low_score: 12 } },
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(empty)))
    const result = await fetchForest('patience', 3)
    expect(result.endpoints).toEqual([])
  })
})
