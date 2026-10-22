import { describe, it, expect, vi, beforeEach } from 'vitest'
import { lookupWord, autocompleteWord, ApiError, fetchForest, streamForest, ForestError, type ForestStreamEvent } from './client'
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

  // Rule: New forest asks the server to skip its cache; Forge lets it serve one.
  it('adds fresh=1 only when a fresh forest is asked for', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(patienceForest)))
    await fetchForest('patience', 3, undefined, true)
    expect(fetch).toHaveBeenCalledWith('/forge/forest?word=patience&max_hops=3&fresh=1', { signal: undefined })
    await fetchForest('patience', 3, undefined, false)
    expect(fetch).toHaveBeenLastCalledWith('/forge/forest?word=patience&max_hops=3', { signal: undefined })
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

describe('streamForest', () => {
  const forest = patienceForest
  const twoKept = { ...forest, endpoints: forest.endpoints.slice(0, 2), stats: { generated: 3, kept: 2, rejected: {} } }
  const frame = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
  // Multi-byte ground text, so some splits fall inside a character.
  const GROUND = 'waits “for spring” ✦'
  const STREAM = [
    ': keepalive\n\n',
    frame('hop', { path_id: 'f0', facet: 0, from: 'patience', to: 'dormant seed', ground: GROUND }),
    frame('hop', { path_id: 'f0b0', facet: 0, from: 'dormant seed', to: 'seed vault', ground: 'stays viable' }),
    frame('rejected', { path_id: 'f0', reason: 'invalid' }),
    frame('kept', { path_id: 'f0b0', endpoint: 'seed vault', score: 7 }),
    frame('forest', twoKept),
    frame('done', forest),
  ].join('')
  const EXPECTED: ForestStreamEvent[] = [
    { type: 'hop', pathId: 'f0', facet: 0, from: 'patience', to: 'dormant seed', ground: GROUND },
    { type: 'hop', pathId: 'f0b0', facet: 0, from: 'dormant seed', to: 'seed vault', ground: 'stays viable' },
    { type: 'rejected', pathId: 'f0', reason: 'invalid' },
    { type: 'kept', pathId: 'f0b0', endpoint: 'seed vault', score: 7 },
    { type: 'forest', forest: twoKept as never },
    { type: 'done', forest: forest as never },
  ]

  /** A body that hands over the given byte chunks, then closes (or stays open). */
  function body(chunks: Uint8Array[], opts: { open?: boolean; onCancel?: () => void } = {}) {
    return new ReadableStream<Uint8Array>({
      start(c) {
        for (const ch of chunks) c.enqueue(ch)
        if (!opts.open) c.close()
      },
      cancel() { opts.onCancel?.() },
    })
  }
  const sse = (stream: ReadableStream<Uint8Array>, status = 200) =>
    new Response(stream, { status, headers: { 'Content-Type': 'text/event-stream' } })
  const bytes = (text: string) => new TextEncoder().encode(text)

  async function collect(): Promise<ForestStreamEvent[]> {
    const events: ForestStreamEvent[] = []
    await streamForest('patience', 3, e => { events.push(e) })
    return events
  }

  it('asks for an event stream with the word, max_hops and fresh flag', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sse(body([bytes(STREAM)]))))
    await streamForest('dormant seed', 4, () => {}, undefined, true)
    expect(fetch).toHaveBeenCalledWith('/forge/forest?word=dormant%20seed&max_hops=4&fresh=1', {
      signal: undefined, headers: { Accept: 'text/event-stream' },
    })
  })

  // Rule: the events delivered do not depend on where the network split the bytes.
  it('delivers the same typed events wherever the stream is split, comments ignored', async () => {
    const all = bytes(STREAM)
    // the baseline: one chunk gives every event in order
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sse(body([all]))))
    expect(await collect()).toEqual(EXPECTED)
    for (let cut = 1; cut < all.length; cut++) {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sse(body([all.slice(0, cut), all.slice(cut)]))))
      expect(await collect(), `split at byte ${cut}`).toEqual(EXPECTED)
    }
    // One full stream read per byte offset; over the 5s default on a 2-core box.
  }, 20_000)

  it('reads CRLF line ends and data split over several data lines', async () => {
    const text = 'event: rejected\r\ndata: {"path_id":\r\ndata: "f2", "reason": "drift"}\r\n\r\n' + frame('done', forest)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sse(body([bytes(text)]))))
    expect((await collect()).slice(0, 1)).toEqual([{ type: 'rejected', pathId: 'f2', reason: 'drift' }])
  })

  // Rule: a malformed frame is logged and skipped; the rest of the stream still arrives.
  it.each([
    ['broken JSON', 'event: hop\ndata: {"path_id": \n\n'],
    ['a hop missing its words', frame('hop', { path_id: 'f9', facet: 9 })],
    ['a kept with no endpoint', frame('kept', { path_id: 'f9', score: 7 })],
    ['a snapshot that breaks the contract', frame('forest', { ...forest, endpoints: undefined })],
  ])('skips %s, logs it, and keeps reading', async (_label, bad) => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sse(body([bytes(bad + STREAM)]))))
    expect(await collect()).toEqual(EXPECTED)
    expect(warn).toHaveBeenCalled()
  })

  it('ignores an event it does not know', async () => {
    vi.spyOn(console, 'debug').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sse(body([bytes(frame('mystery', { x: 1 }) + STREAM)]))))
    expect(await collect()).toEqual(EXPECTED)
  })

  it('delivers a mid-stream error with its kind, and stops there', async () => {
    const text = frame('forest', twoKept) + frame('error', { error: 'judge failed', kind: 'timeout' }) + frame('done', forest)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sse(body([bytes(text)]))))
    expect(await collect()).toEqual([{ type: 'forest', forest: twoKept }, { type: 'error', kind: 'timeout' }])
  })

  it('reads an error of an unknown kind as failed', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sse(body([bytes(frame('error', { error: 'x', kind: 'odd' }))]))))
    expect(await collect()).toEqual([{ type: 'error', kind: 'failed' }])
  })

  it('treats a done that breaks the contract as a failed forest, never as data', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sse(body([bytes(frame('done', { ...forest, stats: null }))]))))
    const err = await collect().catch(e => e)
    expect(err).toBeInstanceOf(ForestError)
    expect(err.kind).toBe('failed')
  })

  // Rule: a stream that stops before done or error is a failure, so the request never hangs.
  it('fails when the stream closes before done or error', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sse(body([bytes(frame('forest', twoKept))]))))
    const events: ForestStreamEvent[] = []
    const err = await streamForest('patience', 3, e => { events.push(e) }).catch(e => e)
    expect(events).toHaveLength(1)
    expect(err).toBeInstanceOf(ForestError)
    expect(err.kind).toBe('failed')
  })

  it('maps a connection lost mid-stream to the network kind', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    let sent = false
    const broken = new ReadableStream<Uint8Array>({
      pull(c) {
        if (!sent) { sent = true; c.enqueue(bytes(frame('forest', twoKept))) } else c.error(new TypeError('network error'))
      },
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sse(broken)))
    const events: ForestStreamEvent[] = []
    const err = await streamForest('patience', 3, e => { events.push(e) }).catch(e => e)
    expect(events).toHaveLength(1)
    expect(err).toBeInstanceOf(ForestError)
    expect(err.kind).toBe('network')
  })

  // Rule: errors before the stream starts map to the same kinds as the JSON request.
  it.each([
    [400, 'invalid-word'],
    [429, 'busy'],
    [503, 'not-configured'],
    [500, 'failed'],
  ] as const)('maps HTTP %i before the stream to the %s kind', async (status, kind) => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: 'server text' }), {
      status, headers: { 'Content-Type': 'application/json', 'Retry-After': '12' },
    })))
    const events: ForestStreamEvent[] = []
    const err = await streamForest('patience', 3, e => { events.push(e) }).catch(e => e)
    expect(err).toBeInstanceOf(ForestError)
    expect(err.kind).toBe(kind)
    expect(err.retryAfterSeconds).toBe(kind === 'busy' ? 12 : null)
    expect(err.message).not.toContain('server text')
    expect(events).toEqual([])
  })

  it('maps a fetch rejection to the network kind and rethrows our own abort', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    expect((await collect().catch(e => e)).kind).toBe('network')
    const abort = new DOMException('The operation was aborted.', 'AbortError')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abort))
    expect(await collect().catch(e => e)).toBe(abort)
  })

  // Rule: a JSON answer (an older server, or a cache hit served whole) is one done event.
  it('treats a JSON body as a single done forest', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(forest), {
      status: 200, headers: { 'Content-Type': 'application/json; charset=utf-8' },
    })))
    expect(await collect()).toEqual([{ type: 'done', forest }])
  })

  it('treats a JSON body that breaks the contract as a failed forest', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"source": 1}', {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })))
    expect((await collect().catch(e => e)).kind).toBe('failed')
  })

  // Rule: aborting stops the read and releases the body, whatever fetch does with the signal.
  it('aborting stops reading, releases the body and rejects with an AbortError', async () => {
    let cancelled = false
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sse(body([bytes(frame('forest', twoKept))], { open: true, onCancel: () => { cancelled = true } }))))
    const controller = new AbortController()
    const events: ForestStreamEvent[] = []
    const run = streamForest('patience', 3, e => { events.push(e) }, controller.signal).catch(e => e)
    await vi.waitFor(() => expect(events).toHaveLength(1))
    controller.abort()
    const err = await run
    expect(err).toBeInstanceOf(DOMException)
    expect(err.name).toBe('AbortError')
    expect(cancelled).toBe(true)
  })
})
