// The metaphor forest's state machine (docs/plans/2026-10-21-metaphor-forest-ui-states.md).
// Pure: mf-app owns one ForestState, feeds it events, and runs the effects the
// change implies (start a fetch when seq moves to a loading request, abort the
// old controller whenever seq moves). A no-op returns the same object, so
// callers can skip work with an identity check.

import type { ForestResponse } from '@/types/api'
import type { ForestErrorKind } from '@/api/client'
import { normaliseWord, type ForestTarget } from '@/graph/forest'

export const DEFAULT_MAX_HOPS = 3
export const MIN_HOPS = 1
export const MAX_HOPS = 5

export type ForestRequest =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'failed'; error: ForestErrorKind; retryAfterSeconds: number | null }

export type ForestContent =
  | { kind: 'none' }
  | { kind: 'forest'; response: ForestResponse }
  | { kind: 'empty'; response: ForestResponse }

/** One-off outcomes the panel announces; cleared by the next request or word. */
export type ForestNotice = 'found' | 'empty-kept' | 'cancelled' | null

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
}

export type ForestEvent =
  | { type: 'forge' }
  | { type: 'settled'; seq: number; response: ForestResponse }
  | { type: 'failed'; seq: number; error: ForestErrorKind; retryAfterSeconds: number | null }
  | { type: 'cancel' }
  | { type: 'word-committed'; word: string }
  | { type: 'set-max-hops'; maxHops: number }
  | { type: 'set-on-graph'; onGraph: boolean }
  | { type: 'hover'; target: ForestTarget | null }
  | { type: 'focus'; target: ForestTarget | null }
  | { type: 'select'; target: ForestTarget | null }

export function initialForestState(word = '', maxHops = DEFAULT_MAX_HOPS): ForestState {
  return {
    word, seq: 0, maxHops,
    request: { kind: 'idle' }, content: { kind: 'none' }, onGraph: true, notice: null,
    hover: null, focus: null, selection: null,
  }
}

const NO_HIGHLIGHT = { hover: null, focus: null, selection: null } as const

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
      if (s.request.kind === 'loading') return s
      return {
        ...s,
        seq: s.seq + 1,
        request: { kind: 'loading' },
        content: s.content.kind === 'empty' ? { kind: 'none' } : s.content,
        notice: null,
      }

    case 'settled': {
      if (!isCurrent(s, e.seq) || normaliseWord(e.response.source) !== normaliseWord(s.word)) return s
      if (e.response.endpoints.length > 0) {
        return { ...s, ...NO_HIGHLIGHT, request: { kind: 'idle' }, content: { kind: 'forest', response: e.response }, onGraph: true, notice: 'found' }
      }
      if (s.content.kind === 'forest') return { ...s, request: { kind: 'idle' }, notice: 'empty-kept' }
      return { ...s, request: { kind: 'idle' }, content: { kind: 'empty', response: e.response }, notice: null }
    }

    case 'failed':
      if (!isCurrent(s, e.seq)) return s
      return { ...s, request: { kind: 'failed', error: e.error, retryAfterSeconds: e.retryAfterSeconds }, notice: null }

    case 'cancel':
      if (s.request.kind !== 'loading') return s
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
  }
}

function isCurrent(s: ForestState, seq: number): boolean {
  return seq === s.seq && s.request.kind === 'loading'
}
