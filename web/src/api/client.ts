import type { ForestResponse, LookupResult } from '@/types/api'

export interface AutocompleteSuggestion {
  word: string
  definition: string
  sense_count: number
  rarity?: string
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/**
 * Look up a word in the thesaurus.
 * Vite dev server proxies /thesaurus/* to localhost:8080.
 */
export async function lookupWord(word: string): Promise<LookupResult> {
  const encoded = encodeURIComponent(word.trim().toLowerCase())
  const response = await fetch(`/thesaurus/lookup?word=${encoded}`)

  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: 'Unknown error' }))
    throw new ApiError(body.error || `HTTP ${response.status}`, response.status)
  }

  const data = await response.json()
  if (!data || typeof data.word !== 'string' || !Array.isArray(data.senses)) {
    throw new ApiError('Invalid response shape', 0)
  }
  return data as LookupResult
}

/**
 * Prefix-search autocomplete for the search bar.
 * Returns suggestions with word, definition, sense count, and rarity.
 */
export async function autocompleteWord(prefix: string, limit = 10): Promise<AutocompleteSuggestion[]> {
  const encoded = encodeURIComponent(prefix.trim().toLowerCase())
  const response = await fetch(`/thesaurus/autocomplete?prefix=${encoded}&limit=${limit}`)

  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: 'Unknown error' }))
    throw new ApiError(body.error || `HTTP ${response.status}`, response.status)
  }

  const data = await response.json()
  if (!data || !Array.isArray(data.suggestions)) {
    throw new ApiError('Invalid response shape', 0)
  }
  return data.suggestions as AutocompleteSuggestion[]
}

/** The failure kinds the forest UI distinguishes (one recovery action each). */
export const FOREST_ERROR_KINDS = ['invalid-word', 'busy', 'failed', 'not-configured', 'timeout', 'network'] as const
export type ForestErrorKind = typeof FOREST_ERROR_KINDS[number]

export class ForestError extends Error {
  constructor(
    public kind: ForestErrorKind,
    public status: number,
    public retryAfterSeconds: number | null = null,
  ) {
    super(`forest request failed: ${kind} (HTTP ${status})`)
    this.name = 'ForestError'
  }
}

const FOREST_STATUS_KINDS: Record<number, ForestErrorKind> = {
  400: 'invalid-word',
  429: 'busy',
  502: 'failed',
  503: 'not-configured',
  504: 'timeout',
}

function parseRetryAfter(value: string | null): number | null {
  if (!value || !/^\d+$/.test(value.trim())) return null
  const seconds = Number(value)
  return seconds >= 1 ? seconds : null
}

/**
 * Generate a metaphor forest for a word. Slow (a model call, up to ~75 s), so
 * callers pass an AbortSignal; an abort rejects with the fetch AbortError
 * unchanged. Every other failure is a ForestError; the server's own `error`
 * text is never surfaced because it is written for logs. `fresh` (New forest)
 * skips the server's cache of forests for the word; without it (Forge) the
 * server may answer from that cache, instantly.
 */
export async function fetchForest(word: string, maxHops: number, signal?: AbortSignal, fresh = false): Promise<ForestResponse> {
  const url = `/forge/forest?word=${encodeURIComponent(word)}&max_hops=${maxHops}${fresh ? '&fresh=1' : ''}`
  let response: Response
  try {
    response = await fetch(url, { signal })
  } catch (err) {
    if (isAbort(err)) throw err
    console.warn('[forest] request did not reach the server', { word, maxHops }, err)
    throw new ForestError('network', 0)
  }
  if (!response.ok) throw statusError(response, word)
  const data: unknown = await response.json().catch(() => null)
  return checkedForest(data, word, response.status)
}

/** One event of a streamed forest (docs/plans/2026-10-21-forest-streaming.md, API contract). */
export type ForestStreamEvent =
  | { type: 'hop'; pathId: string; facet: number; from: string; to: string; ground: string }
  | { type: 'rejected'; pathId: string; reason: string }
  | { type: 'kept'; pathId: string; endpoint: string; score: number }
  | { type: 'forest'; forest: ForestResponse }
  | { type: 'done'; forest: ForestResponse }
  | { type: 'error'; kind: 'failed' | 'timeout' }
  // What the server is waiting on: a generator call, the thin-output retry, or a facet's judge.
  // Optional: a server that sends none still streams a working forest.
  | { type: 'stage'; stage: 'drafting' | 'retrying' }
  | { type: 'stage'; stage: 'judging'; facet: number; word: string }

/**
 * Stream a metaphor forest: each event goes to `onEvent` as it arrives, and the
 * promise settles after `done` or `error`. Errors before the stream starts, a
 * stream that ends early and a `done` that breaks the contract reject with the
 * same ForestError kinds as fetchForest; an abort rejects with an AbortError.
 * A JSON answer (a server that does not stream) is delivered as one `done`.
 */
export async function streamForest(
  word: string,
  maxHops: number,
  onEvent: (event: ForestStreamEvent) => void,
  signal?: AbortSignal,
  fresh = false,
): Promise<void> {
  const url = `/forge/forest?word=${encodeURIComponent(word)}&max_hops=${maxHops}${fresh ? '&fresh=1' : ''}`
  let response: Response
  try {
    response = await fetch(url, { signal, headers: { Accept: 'text/event-stream' } })
  } catch (err) {
    if (isAbort(err)) throw err
    console.warn('[forest] stream did not reach the server', { word, maxHops }, err)
    throw new ForestError('network', 0)
  }
  if (!response.ok) throw statusError(response, word)

  if (!(response.headers.get('Content-Type') ?? '').includes('text/event-stream')) {
    const data: unknown = await response.json().catch(() => null)
    onEvent({ type: 'done', forest: checkedForest(data, word, response.status) })
    return
  }
  if (!response.body) throw new ForestError('failed', response.status)

  const reader = response.body.getReader()
  // Cancel the read ourselves: a fetch stub (or an old browser) may ignore the signal once the body flows.
  const abortError = () => signal?.reason instanceof DOMException ? signal.reason : new DOMException('The operation was aborted.', 'AbortError')
  const onAbort = () => { void reader.cancel().catch(() => {}) }
  signal?.addEventListener('abort', onAbort)
  try {
    const parser = new SseParser()
    const decoder = new TextDecoder()
    for (;;) {
      if (signal?.aborted) throw abortError()
      let chunk: ReadableStreamReadResult<Uint8Array>
      try {
        chunk = await reader.read()
      } catch (err) {
        if (signal?.aborted || isAbort(err)) throw abortError()
        console.warn('[forest] stream lost mid-way', { word }, err)
        throw new ForestError('network', response.status)
      }
      if (signal?.aborted) throw abortError()
      if (chunk.done) break
      for (const frame of parser.push(decoder.decode(chunk.value, { stream: true }))) {
        const event = toStreamEvent(frame, word, response.status)
        if (!event) continue
        onEvent(event)
        if (event.type === 'done' || event.type === 'error') {
          void reader.cancel().catch(() => {})
          return
        }
      }
    }
    console.warn('[forest] stream ended before done', { word })
    throw new ForestError('failed', response.status)
  } finally {
    signal?.removeEventListener('abort', onAbort)
  }
}

function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError'
}

function statusError(response: Response, word: string): ForestError {
  const kind = FOREST_STATUS_KINDS[response.status] ?? 'failed'
  if (!(response.status in FOREST_STATUS_KINDS)) {
    console.warn('[forest] unexpected status, shown as a failed forest', { word, status: response.status })
  }
  const retryAfter = kind === 'busy' ? parseRetryAfter(response.headers.get('Retry-After')) : null
  return new ForestError(kind, response.status, retryAfter)
}

function checkedForest(data: unknown, word: string, status: number): ForestResponse {
  const problem = forestShapeProblem(data)
  if (problem) {
    console.warn('[forest] forest body breaks the contract, shown as a failed forest', { word, problem })
    throw new ForestError('failed', status)
  }
  return data as ForestResponse
}

interface SseFrame { event: string; data: string }

/** Incremental text/event-stream parser: feed it decoded text in any pieces,
 *  get back each frame once its blank line has arrived. */
class SseParser {
  private buffer = ''
  private event = ''
  private data: string[] = []

  push(text: string): SseFrame[] {
    this.buffer += text
    const frames: SseFrame[] = []
    for (;;) {
      const m = /\r\n|\r|\n/.exec(this.buffer)
      // A lone \r at the end may be the first half of \r\n: wait for more.
      if (!m || (m[0] === '\r' && m.index === this.buffer.length - 1)) break
      const line = this.buffer.slice(0, m.index)
      this.buffer = this.buffer.slice(m.index + m[0].length)
      if (line === '') {
        if (this.data.length) frames.push({ event: this.event || 'message', data: this.data.join('\n') })
        this.event = ''
        this.data = []
      } else if (!line.startsWith(':')) {
        const colon = line.indexOf(':')
        const field = colon < 0 ? line : line.slice(0, colon)
        const value = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '')
        if (field === 'event') this.event = value
        else if (field === 'data') this.data.push(value)
      }
    }
    return frames
  }
}

/** The typed event for one frame, or null (logged) when it cannot be used. */
function toStreamEvent(frame: SseFrame, word: string, status: number): ForestStreamEvent | null {
  let d: Record<string, unknown>
  try {
    d = JSON.parse(frame.data)
  } catch {
    if (frame.event === 'done') {
      console.warn('[forest] done frame is not JSON, shown as a failed forest', { word })
      throw new ForestError('failed', status)
    }
    console.warn('[forest] skipped a stream frame that is not JSON', { word, event: frame.event })
    return null
  }
  const skip = (why: string) => {
    console.warn('[forest] skipped a stream frame that breaks the contract', { word, event: frame.event, why })
    return null
  }
  switch (frame.event) {
    case 'hop':
      if (!d || !isString(d.path_id) || typeof d.facet !== 'number' || !isString(d.from) || !isString(d.to) || !isString(d.ground)) return skip('hop')
      return { type: 'hop', pathId: d.path_id, facet: d.facet, from: d.from, to: d.to, ground: d.ground }
    case 'rejected':
      if (!d || !isString(d.path_id) || !isString(d.reason)) return skip('rejected')
      return { type: 'rejected', pathId: d.path_id, reason: d.reason }
    case 'kept':
      if (!d || !isString(d.path_id) || !isString(d.endpoint) || typeof d.score !== 'number') return skip('kept')
      return { type: 'kept', pathId: d.path_id, endpoint: d.endpoint, score: d.score }
    case 'forest': {
      const problem = forestShapeProblem(d)
      return problem ? skip(`forest: ${problem}`) : { type: 'forest', forest: d as unknown as ForestResponse }
    }
    case 'done':
      return { type: 'done', forest: checkedForest(d, word, status) }
    case 'error':
      return { type: 'error', kind: d?.kind === 'timeout' ? 'timeout' : 'failed' }
    case 'stage':
      if (d?.stage === 'drafting' || d?.stage === 'retrying') return { type: 'stage', stage: d.stage }
      if (d?.stage === 'judging' && typeof d.facet === 'number' && isString(d.word)) return { type: 'stage', stage: 'judging', facet: d.facet, word: d.word }
      return skip('stage')
    default:
      console.debug('[forest] ignored an unknown stream event', { event: frame.event })
      return null
  }
}

const isString = (v: unknown): v is string => typeof v === 'string'
const isStringArray = (v: unknown): v is string[] => Array.isArray(v) && v.every(isString)

/** First contract violation in a forest body, or null when it is usable. */
function forestShapeProblem(data: unknown): string | null {
  if (!data || typeof data !== 'object') return 'not an object'
  const d = data as Record<string, unknown>
  if (!isString(d.source)) return 'source'
  if (!Array.isArray(d.nodes) || !Array.isArray(d.edges) || !Array.isArray(d.endpoints)) return 'arrays'
  if (!d.stats || typeof d.stats !== 'object') return 'stats'

  const ids = new Set<string>()
  for (const n of d.nodes as Record<string, unknown>[]) {
    if (!n || !isString(n.id) || !isString(n.word) || !['source', 'hop', 'endpoint'].includes(n.role as string)) return 'node'
    ids.add(n.id)
  }
  for (const e of d.edges as Record<string, unknown>[]) {
    if (!e || !isString(e.source) || !isString(e.target) || !isStringArray(e.grounds)) return 'edge'
    if (!ids.has(e.source) || !ids.has(e.target)) return 'edge to unknown node'
  }
  for (const p of d.endpoints as Record<string, unknown>[]) {
    if (!p || !isString(p.id) || !isString(p.line) || typeof p.score !== 'number') return 'endpoint'
    if (!isStringArray(p.path) || !isStringArray(p.grounds)) return 'endpoint path'
    if (p.path.length < 2 || p.path[0] !== d.source || p.path[p.path.length - 1] !== p.id) return 'endpoint path ends'
    if (p.grounds.length !== p.path.length - 1) return 'endpoint grounds'
    if (!p.path.every(w => ids.has(w))) return 'endpoint path node'
  }
  return null
}
