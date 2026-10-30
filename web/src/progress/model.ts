// The activity log behind the progress panel. Pure: mf-app feeds it what it
// already knows (lookups, glimpses, expansions, the forest stream) and the panel
// renders the result. One line per stage, keyed, so a stage that counts updates
// its line in place; the log is newest last. A no-op returns the same object.

import type { ForestStreamEvent } from '@/api/client'

export type ProgressLine =
  | { key: 'lookup'; kind: 'lookup'; word: string; senses: number; words: number }
  | { key: string; kind: 'lookup-failed'; word: string }
  | { key: 'nearby'; kind: 'nearby'; done: number; total: number }
  | { key: 'nearby-failed'; kind: 'nearby-failed'; n: number }
  | { key: string; kind: 'expanded'; word: string; words: number }
  | { key: string; kind: 'expand-failed'; word: string }
  | { key: 'forging'; kind: 'forging'; drafted: number; kept: number; dropped: number }
  | { key: 'retrying'; kind: 'retrying' }
  | { key: string; kind: 'judging'; word: string }
  | { key: 'forest-ready'; kind: 'forest-ready'; n: number }
  | { key: 'forest-failed'; kind: 'forest-failed' }
  | { key: 'forest-cancelled'; kind: 'forest-cancelled' }
  | { key: 'all-loaded'; kind: 'all-loaded' }

interface ForestProgress {
  running: boolean
  paths: Readonly<Record<string, 'pending' | 'kept' | 'rejected'>>
}

export interface ProgressState {
  lines: readonly ProgressLine[]
  lookup: string | null                 // the word a pending lookup is for
  glimpses: { started: number; done: number; failed: number; waiting: number }
  expanding: readonly string[]          // words whose expansion is in flight
  forest: ForestProgress
}

export type ProgressEvent =
  | { type: 'lookup-started'; word: string }
  // keepForest: the forest request survived the lookup (same word), so its lines stay.
  | { type: 'lookup-done'; word: string; senses: number; words: number; keepForest: boolean }
  | { type: 'lookup-failed'; word: string }
  | { type: 'view-restored'; keepForest: boolean }
  | { type: 'glimpse-started' }
  | { type: 'glimpse-done' }
  | { type: 'glimpse-failed' }
  | { type: 'glimpses-waiting'; n: number }  // visible words owed a glimpse, not started yet
  | { type: 'expansion-started'; word: string }
  | { type: 'expansion-done'; word: string; words: number }
  | { type: 'expansion-failed'; word: string }
  | { type: 'forest-started' }
  | { type: 'forest-stream'; event: ForestStreamEvent }
  | { type: 'forest-ended'; outcome: 'failed' | 'cancelled' }

const NO_FOREST: ForestProgress = { running: false, paths: {} }
const NO_GLIMPSES = { started: 0, done: 0, failed: 0, waiting: 0 }
const FOREST_KEYS = /^(forging|retrying|judging:|forest-)/

export function initialProgress(): ProgressState {
  return { lines: [], lookup: null, glimpses: NO_GLIMPSES, expanding: [], forest: NO_FOREST }
}

export interface Pending {
  lookup: string | null
  nearby: number
  expansions: number
  forest: boolean
}

export function pendingOf(s: ProgressState): Pending {
  const g = s.glimpses
  return {
    lookup: s.lookup,
    nearby: Math.max(0, g.started + g.waiting - g.done - g.failed),
    expansions: s.expanding.length,
    forest: s.forest.running,
  }
}

export function isBusy(s: ProgressState): boolean {
  const p = pendingOf(s)
  return p.lookup !== null || p.nearby > 0 || p.expansions > 0 || p.forest
}

export function reduceProgress(s: ProgressState, e: ProgressEvent): ProgressState {
  const next = step(s, e)
  if (next === s) return s
  // "All loaded." closes the log when the last pending work ends, and goes
  // as soon as anything starts again.
  const lines = next.lines.filter(l => l.kind !== 'all-loaded')
  if (isBusy(next) || lines.length === 0) return lines.length === next.lines.length ? next : { ...next, lines }
  return isBusy(s) || next.lines.at(-1)?.kind !== 'all-loaded'
    ? { ...next, lines: [...lines, { key: 'all-loaded', kind: 'all-loaded' }] }
    : next
}

/** Replace the line with the same key where it stands, or add it at the end. */
function put(lines: readonly ProgressLine[], line: ProgressLine): ProgressLine[] {
  const i = lines.findIndex(l => l.key === line.key)
  if (i < 0) return [...lines, line]
  const out = [...lines]
  out[i] = line
  return out
}

function nearbyLine(s: ProgressState, g: ProgressState['glimpses']): ProgressLine[] {
  const lines = put(s.lines, { key: 'nearby', kind: 'nearby', done: g.done, total: g.started + g.waiting })
  return g.failed > 0 ? put(lines, { key: 'nearby-failed', kind: 'nearby-failed', n: g.failed }) : lines
}

function fresh(s: ProgressState, keepForest: boolean): ProgressState {
  if (!keepForest) return initialProgress()
  return { ...initialProgress(), lines: s.lines.filter(l => FOREST_KEYS.test(l.key)), forest: s.forest }
}

function step(s: ProgressState, e: ProgressEvent): ProgressState {
  switch (e.type) {
    case 'lookup-started':
      return { ...s, lookup: e.word }

    case 'lookup-done': {
      const base = fresh(s, e.keepForest)
      return { ...base, lines: [{ key: 'lookup', kind: 'lookup', word: e.word, senses: e.senses, words: e.words }, ...base.lines] }
    }

    case 'lookup-failed':
      return { ...s, lookup: null, lines: put(s.lines, { key: `lookup-failed:${e.word}`, kind: 'lookup-failed', word: e.word }) }

    case 'view-restored':
      return fresh(s, e.keepForest)

    case 'glimpse-started':
    case 'glimpse-done':
    case 'glimpse-failed': {
      const field = e.type === 'glimpse-started' ? 'started' : e.type === 'glimpse-done' ? 'done' : 'failed'
      const glimpses = { ...s.glimpses, [field]: s.glimpses[field] + 1 }
      return { ...s, glimpses, lines: nearbyLine(s, glimpses) }
    }

    case 'glimpses-waiting': {
      if (e.n === s.glimpses.waiting) return s
      const glimpses = { ...s.glimpses, waiting: e.n }
      // Waiting words alone do not open the line; the first glimpse does.
      const lines = s.lines.some(l => l.key === 'nearby') ? nearbyLine(s, glimpses) : s.lines
      return { ...s, glimpses, lines }
    }

    case 'expansion-started':
      return s.expanding.includes(e.word) ? s : { ...s, expanding: [...s.expanding, e.word] }

    case 'expansion-done':
    case 'expansion-failed': {
      const expanding = s.expanding.filter(w => w !== e.word)
      const line: ProgressLine = e.type === 'expansion-done'
        ? { key: `expanded:${e.word}`, kind: 'expanded', word: e.word, words: e.words }
        : { key: `expand-failed:${e.word}`, kind: 'expand-failed', word: e.word }
      return { ...s, expanding, lines: put(s.lines, line) }
    }

    case 'forest-started': {
      const lines = s.lines.filter(l => !FOREST_KEYS.test(l.key))
      return { ...s, forest: { running: true, paths: {} }, lines: [...lines, forgingLine({})] }
    }

    case 'forest-ended': {
      if (!s.forest.running) return s
      const line: ProgressLine = e.outcome === 'failed'
        ? { key: 'forest-failed', kind: 'forest-failed' }
        : { key: 'forest-cancelled', kind: 'forest-cancelled' }
      return { ...s, forest: { ...s.forest, running: false }, lines: put(s.lines, line) }
    }

    case 'forest-stream':
      return s.forest.running ? forestStep(s, e.event) : s
  }
}

function forgingLine(paths: ForestProgress['paths']): ProgressLine {
  const all = Object.values(paths)
  return {
    key: 'forging', kind: 'forging',
    drafted: all.length,
    kept: all.filter(p => p === 'kept').length,
    dropped: all.filter(p => p === 'rejected').length,
  }
}

function forestStep(s: ProgressState, e: ForestStreamEvent): ProgressState {
  const withPaths = (paths: ForestProgress['paths']): ProgressState =>
    ({ ...s, forest: { ...s.forest, paths }, lines: put(s.lines, forgingLine(paths)) })
  switch (e.type) {
    case 'hop':
      return e.pathId in s.forest.paths ? s : withPaths({ ...s.forest.paths, [e.pathId]: 'pending' })
    case 'kept':
    case 'rejected':
      return withPaths({ ...s.forest.paths, [e.pathId]: e.type === 'kept' ? 'kept' : 'rejected' })
    case 'stage':
      if (e.stage !== 'judging') return e.stage === 'retrying' ? { ...s, lines: put(s.lines, { key: 'retrying', kind: 'retrying' }) } : s
      return { ...s, lines: put(s.lines, { key: `judging:${e.facet}`, kind: 'judging', word: e.word }) }
    case 'forest':
      return s
    case 'done':
      return { ...s, forest: { ...s.forest, running: false }, lines: put(s.lines, { key: 'forest-ready', kind: 'forest-ready', n: e.forest.endpoints.length }) }
    case 'error':
      return { ...s, forest: { ...s.forest, running: false }, lines: put(s.lines, { key: 'forest-failed', kind: 'forest-failed' }) }
  }
}
