// The metaphor forest's state machine (docs/plans/2026-10-21-metaphor-forest-ui-states.md).
// Pure: mf-app owns one ForestState, feeds it events, and runs the effects the
// change implies (start a fetch when seq moves to a loading request, abort the
// old controller whenever seq moves). A no-op returns the same object, so
// callers can skip work with an identity check.

import type { ForestResponse } from '@/types/api'
import type { ForestErrorKind, ForestStreamEvent } from '@/api/client'
import { normaliseWord, type ForestTarget } from '@/graph/forest'

export const DEFAULT_MAX_HOPS = 3
export const MIN_HOPS = 1
export const MAX_HOPS = 5

/** One hop of a streamed path, as the generator wrote it (node ids). */
export interface StreamHop { from: string; to: string; ground: string }

/** A path the stream has drawn. A branch `f<i>b<j>` also runs along its facet's
 *  head hop, which arrives under the facet's own id `f<i>`. */
export interface StreamPath {
  id: string
  facet: number
  hops: StreamHop[]
  status: 'pending' | 'kept' | 'rejected'
  endpoint?: string
  score?: number
}

export type ForestRequest =
  | { kind: 'idle' }
  | { kind: 'loading' }
  // `snapshot` is the latest judged forest of this stream (null until the first).
  | { kind: 'streaming'; snapshot: ForestResponse | null; paths: Readonly<Record<string, StreamPath>> }
  | { kind: 'failed'; error: ForestErrorKind; retryAfterSeconds: number | null }

export type ForestContent =
  | { kind: 'none' }
  | { kind: 'forest'; response: ForestResponse }
  | { kind: 'empty'; response: ForestResponse }

/** One-off outcomes the panel announces; cleared by the next request or word. */
export type ForestNotice = 'found' | 'empty-kept' | 'cancelled' | 'browsed' | null

export interface ForestState {
  word: string          // the committed word; forests belong to it
  seq: number           // bumped on every start, cancel and word change
  maxHops: number
  request: ForestRequest
  content: ForestContent
  onGraph: boolean
  notice: ForestNotice
  hover: ForestTarget | null
  focus: ForestTarget | null
  selection: ForestTarget | null
  // The word's saved forests at the shown forest's steps, newest first, as the
  // server last listed them; [] until listed. Browsing never generates.
  saved: readonly ForestResponse[]
  savedIndex: number | null  // the shown forest's place in `saved`; null when it is not there
}

export type ForestEvent =
  | { type: 'forge' }
  | { type: 'settled'; seq: number; response: ForestResponse }
  | { type: 'stream'; seq: number; event: ForestStreamEvent }
  | { type: 'failed'; seq: number; error: ForestErrorKind; retryAfterSeconds: number | null }
  | { type: 'cancel' }
  | { type: 'word-committed'; word: string }
  | { type: 'set-max-hops'; maxHops: number }
  | { type: 'set-on-graph'; onGraph: boolean }
  | { type: 'hover'; target: ForestTarget | null }
  | { type: 'focus'; target: ForestTarget | null }
  | { type: 'select'; target: ForestTarget | null }
  | { type: 'saved-loaded'; word: string; maxHops: number; forests: readonly ForestResponse[] }
  | { type: 'browse'; step: 1 | -1 }

export function initialForestState(word = '', maxHops = DEFAULT_MAX_HOPS): ForestState {
  return {
    word, seq: 0, maxHops,
    request: { kind: 'idle' }, content: { kind: 'none' }, onGraph: true, notice: null,
    hover: null, focus: null, selection: null,
    saved: [], savedIndex: null,
  }
}

/** Saved forests come back through JSON, so they match the shown one by content. */
function savedIndexOf(saved: readonly ForestResponse[], content: ForestContent): number | null {
  if (content.kind !== 'forest') return null
  const key = JSON.stringify(content.response)
  const i = saved.findIndex(f => f === content.response || JSON.stringify(f) === key)
  return i < 0 ? null : i
}

/** Whether Next or Previous would show a different forest. */
export function canBrowse(s: ForestState): boolean {
  if (inFlight(s) || s.content.kind !== 'forest' || s.saved.length === 0) return false
  return !(s.saved.length === 1 && s.savedIndex === 0)
}

const NO_HIGHLIGHT = { hover: null, focus: null, selection: null } as const

/** A request is in flight: waiting for the first event, or streaming. */
export function inFlight(s: ForestState): boolean {
  return s.request.kind === 'loading' || s.request.kind === 'streaming'
}

export function sameTarget(a: ForestTarget | null, b: ForestTarget | null): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

/** The target that lights the graph and panel: the most transient source wins. */
export function litTarget(s: ForestState): ForestTarget | null {
  return s.hover ?? s.focus ?? s.selection
}

export function reduceForest(s: ForestState, e: ForestEvent): ForestState {
  switch (e.type) {
    case 'forge':
      if (inFlight(s)) return s
      return {
        ...s,
        seq: s.seq + 1,
        request: { kind: 'loading' },
        content: s.content.kind === 'empty' ? { kind: 'none' } : s.content,
        notice: null,
      }

    case 'settled': {
      // seq alone identifies the response: the server's normalised `source`
      // can differ from ours (Go and JS disagree on case and whitespace).
      if (!isCurrent(s, e.seq)) return s
      return settle(s, e.response)
    }

    case 'stream':
      if (!isCurrent(s, e.seq)) return s
      return reduceStream(s, e.event)

    case 'failed':
      if (!isCurrent(s, e.seq)) return s
      return { ...s, request: { kind: 'failed', error: e.error, retryAfterSeconds: e.retryAfterSeconds }, notice: null }

    case 'cancel':
      if (!inFlight(s)) return s
      return { ...s, seq: s.seq + 1, request: { kind: 'idle' }, notice: 'cancelled' }

    case 'word-committed':
      if (normaliseWord(e.word) === normaliseWord(s.word)) return s
      return { ...initialForestState(e.word, s.maxHops), seq: s.seq + 1 }

    case 'set-max-hops': {
      const maxHops = Math.min(MAX_HOPS, Math.max(MIN_HOPS, Math.round(e.maxHops)))
      return maxHops === s.maxHops ? s : { ...s, maxHops }
    }

    case 'set-on-graph':
      if (s.content.kind !== 'forest' || s.onGraph === e.onGraph) return s
      return { ...s, onGraph: e.onGraph }

    case 'hover':
    case 'focus': {
      if (e.target && s.content.kind !== 'forest') return s
      return sameTarget(s[e.type], e.target) ? s : { ...s, [e.type]: e.target }
    }

    case 'select': {
      if (e.target && s.content.kind !== 'forest') return s
      const selection = sameTarget(s.selection, e.target) ? null : e.target
      return sameTarget(s.selection, selection) ? s : { ...s, selection }
    }

    case 'saved-loaded': {
      const shownHops = s.content.kind === 'forest' ? s.content.response.max_hops : null
      if (inFlight(s) || normaliseWord(e.word) !== normaliseWord(s.word) || e.maxHops !== shownHops) {
        console.debug('[forest] stale saved-forest list ignored', { word: e.word, maxHops: e.maxHops })
        return s
      }
      return { ...s, saved: e.forests, savedIndex: savedIndexOf(e.forests, s.content) }
    }

    case 'browse': {
      if (!canBrowse(s)) return s
      const n = s.saved.length
      const i = s.savedIndex === null ? (e.step > 0 ? 0 : n - 1) : (s.savedIndex + e.step + n) % n
      return {
        ...s, ...NO_HIGHLIGHT,
        request: { kind: 'idle' },
        content: { kind: 'forest', response: s.saved[i] },
        savedIndex: i,
        notice: 'browsed',
      }
    }
  }
}

function isCurrent(s: ForestState, seq: number): boolean {
  return seq === s.seq && inFlight(s)
}

/** A snapshot already shown by this stream keeps its highlights through later
 *  snapshots and the final forest: they only add paths. */
function streamedSnapshot(s: ForestState): boolean {
  return s.request.kind === 'streaming' && !!s.request.snapshot && s.content.kind === 'forest'
}

function settle(s: ForestState, response: ForestResponse): ForestState {
  const next = settleContent(s, response)
  return { ...next, savedIndex: savedIndexOf(next.saved, next.content) }
}

function settleContent(s: ForestState, response: ForestResponse): ForestState {
  if (response.endpoints.length > 0) {
    const highlight = streamedSnapshot(s) ? {} : { ...NO_HIGHLIGHT, onGraph: true }
    return { ...s, ...highlight, request: { kind: 'idle' }, content: { kind: 'forest', response }, notice: 'found' }
  }
  if (s.content.kind === 'forest') return { ...s, request: { kind: 'idle' }, notice: 'empty-kept' }
  return { ...s, request: { kind: 'idle' }, content: { kind: 'empty', response }, notice: null }
}

function reduceStream(s: ForestState, e: ForestStreamEvent): ForestState {
  if (e.type === 'done') return settle(s, e.forest)
  if (e.type === 'error') return { ...s, request: { kind: 'failed', error: e.kind, retryAfterSeconds: null }, notice: null }
  // Stages feed the activity log (progress/model.ts), not the forest.
  if (e.type === 'stage') return s

  const request = s.request.kind === 'streaming' ? s.request : { kind: 'streaming' as const, snapshot: null, paths: {} }
  const { paths } = request
  switch (e.type) {
    case 'forest': {
      const next = { ...s, request: { ...request, snapshot: e.forest } }
      if (e.forest.endpoints.length === 0) return next
      const highlight = streamedSnapshot(s) ? {} : { ...NO_HIGHLIGHT, onGraph: true }
      return { ...next, ...highlight, content: { kind: 'forest', response: e.forest } }
    }
    case 'hop': {
      const path = paths[e.pathId]
      if (path && path.status !== 'pending') {
        console.debug('[forest] hop for a path already judged, ignored', { pathId: e.pathId })
        return s
      }
      const hop = { from: e.from, to: e.to, ground: e.ground }
      const updated: StreamPath = path
        ? { ...path, hops: [...path.hops, hop] }
        : { id: e.pathId, facet: e.facet, hops: [hop], status: 'pending' }
      return { ...s, request: { ...request, paths: { ...paths, [e.pathId]: updated } } }
    }
    case 'kept':
    case 'rejected': {
      const path = paths[e.pathId]
      if (path?.status !== 'pending') {
        console.debug('[forest] verdict for a path that is not pending, ignored', { pathId: e.pathId, verdict: e.type })
        return s
      }
      const updated: StreamPath = e.type === 'kept'
        ? { ...path, status: 'kept', endpoint: e.endpoint, score: e.score }
        : { ...path, status: 'rejected' }
      return { ...s, request: { ...request, paths: { ...paths, [e.pathId]: updated } } }
    }
  }
}
