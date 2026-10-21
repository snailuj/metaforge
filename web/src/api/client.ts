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
 * text is never surfaced because it is written for logs.
 */
export async function fetchForest(word: string, maxHops: number, signal?: AbortSignal): Promise<ForestResponse> {
  const url = `/forge/forest?word=${encodeURIComponent(word)}&max_hops=${maxHops}`
  let response: Response
  try {
    response = await fetch(url, { signal })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    console.warn('[forest] request did not reach the server', { word, maxHops }, err)
    throw new ForestError('network', 0)
  }

  if (!response.ok) {
    const kind = FOREST_STATUS_KINDS[response.status] ?? 'failed'
    if (!(response.status in FOREST_STATUS_KINDS)) {
      console.warn('[forest] unexpected status, shown as a failed forest', { word, status: response.status })
    }
    const retryAfter = kind === 'busy' ? parseRetryAfter(response.headers.get('Retry-After')) : null
    throw new ForestError(kind, response.status, retryAfter)
  }

  const data: unknown = await response.json().catch(() => null)
  const problem = forestShapeProblem(data)
  if (problem) {
    console.warn('[forest] 200 body breaks the contract, shown as a failed forest', { word, problem })
    throw new ForestError('failed', response.status)
  }
  return data as ForestResponse
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
