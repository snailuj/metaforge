import { describe, it, expect } from 'vitest'
import type { ForestResponse } from '@/types/api'
import patience from '@/fixtures/forest-patience.json'
import { initialProgress, reduceProgress, pendingOf, isBusy, type ProgressEvent, type ProgressState } from './model'

const run = (s: ProgressState, ...events: ProgressEvent[]) => events.reduce(reduceProgress, s)
const keys = (s: ProgressState) => s.lines.map(l => l.key)
const line = (s: ProgressState, key: string) => s.lines.find(l => l.key === key)
const looked = (word = 'patience') => run(initialProgress(),
  { type: 'lookup-started', word },
  { type: 'lookup-done', word, senses: 4, words: 23, keepForest: false })
const stream = (event: Extract<ProgressEvent, { type: 'forest-stream' }>['event']): ProgressEvent => ({ type: 'forest-stream', event })
const hop = (pathId: string): ProgressEvent => stream({ type: 'hop', pathId, facet: 0, from: 'a', to: 'b', ground: 'g' })
const forest = patience as ForestResponse

describe('progress model: lines', () => {
  // Rule: a stage gets one line, created once; later progress in that stage updates it in place.
  it('creates each stage line once and updates counting lines in place', () => {
    const s = run(looked(),
      { type: 'glimpse-started' }, { type: 'glimpse-started' }, { type: 'glimpse-done' },
      { type: 'forest-started' }, hop('f0'), hop('f0'), hop('f0b0'),
      stream({ type: 'kept', pathId: 'f0b0', endpoint: 'b', score: 8 }),
      stream({ type: 'rejected', pathId: 'f0', reason: 'low' }),
      { type: 'glimpse-done' })
    expect(keys(s)).toEqual(['lookup', 'nearby', 'forging'])
    expect(line(s, 'lookup')).toMatchObject({ kind: 'lookup', word: 'patience', senses: 4, words: 23 })
    expect(line(s, 'nearby')).toMatchObject({ kind: 'nearby', done: 2, total: 2 })
    expect(line(s, 'forging')).toMatchObject({ kind: 'forging', drafted: 2, kept: 1, dropped: 1 })
  })

  // Rule: the server's stages add their own lines: one per judged facet, one for a retry.
  it('adds a line per judged facet and one for a retry, in stream order', () => {
    const s = run(looked(), { type: 'forest-started' },
      stream({ type: 'stage', stage: 'drafting' }),
      stream({ type: 'stage', stage: 'retrying' }),
      stream({ type: 'stage', stage: 'judging', facet: 0, word: 'dormant seed' }),
      stream({ type: 'stage', stage: 'judging', facet: 1, word: 'still water' }),
      stream({ type: 'stage', stage: 'judging', facet: 1, word: 'still water' }))
    expect(keys(s)).toEqual(['lookup', 'forging', 'retrying', 'judging:0', 'judging:1'])
    expect(line(s, 'judging:1')).toMatchObject({ kind: 'judging', word: 'still water' })
  })

  // Rule: failures are counted on one line of their own.
  it('counts failed glimpses on one failure line', () => {
    const s = run(looked(), { type: 'glimpse-started' }, { type: 'glimpse-started' }, { type: 'glimpse-failed' }, { type: 'glimpse-failed' })
    expect(line(s, 'nearby-failed')).toMatchObject({ n: 2 })
    expect(s.lines.filter(l => l.key === 'nearby-failed')).toHaveLength(1)
  })

  // Rule: a forest that ends says how it ended.
  it('ends the forest with ready, failed or stopped', () => {
    const started = run(looked(), { type: 'forest-started' })
    expect(line(run(started, stream({ type: 'done', forest })), 'forest-ready')).toMatchObject({ n: forest.endpoints.length })
    expect(line(run(started, stream({ type: 'error', kind: 'timeout' })), 'forest-failed')).toBeDefined()
    expect(line(run(started, { type: 'forest-ended', outcome: 'failed' }), 'forest-failed')).toBeDefined()
    expect(line(run(started, { type: 'forest-ended', outcome: 'cancelled' }), 'forest-cancelled')).toBeDefined()
  })
})

describe('progress model: pending work', () => {
  // Rule: the nearby count is glimpses finished out of glimpses started plus those waiting to start.
  it('counts glimpses started, waiting and finished', () => {
    let s = run(looked(), { type: 'glimpses-waiting', n: 7 }, { type: 'glimpse-started' }, { type: 'glimpse-started' }, { type: 'glimpse-started' })
    expect(line(s, 'nearby')).toMatchObject({ done: 0, total: 10 })
    expect(pendingOf(s).nearby).toBe(10)
    s = run(s, { type: 'glimpse-done' }, { type: 'glimpse-failed' }, { type: 'glimpses-waiting', n: 5 })
    expect(line(s, 'nearby')).toMatchObject({ done: 1, total: 8 })
    expect(pendingOf(s).nearby).toBe(6)
  })

  // Rule: "All loaded." is the last line exactly when nothing is pending, and only then.
  it('says All loaded only when nothing is pending', () => {
    let s = run(initialProgress(), { type: 'lookup-started', word: 'patience' })
    expect(isBusy(s)).toBe(true)
    expect(line(s, 'all-loaded')).toBeUndefined()
    s = run(s, { type: 'lookup-done', word: 'patience', senses: 4, words: 23, keepForest: false }, { type: 'glimpse-started' })
    expect(isBusy(s)).toBe(true)
    expect(line(s, 'all-loaded')).toBeUndefined()
    s = run(s, { type: 'glimpse-done' })
    expect(isBusy(s)).toBe(false)
    expect(keys(s).at(-1)).toBe('all-loaded')
    s = run(s, { type: 'expansion-started', word: 'calm' })
    expect(line(s, 'all-loaded')).toBeUndefined()
    expect(pendingOf(s).expansions).toBe(1)
    s = run(s, { type: 'expansion-done', word: 'calm', words: 6 })
    expect(keys(s).slice(-2)).toEqual(['expanded:calm', 'all-loaded'])
    expect(s.lines.filter(l => l.key === 'all-loaded')).toHaveLength(1)
  })

  // Rule: a running forest keeps the work pending until it ends.
  it('keeps the forest pending until it ends', () => {
    const s = run(looked(), { type: 'forest-started' }, hop('f0'))
    expect(pendingOf(s).forest).toBe(true)
    expect(isBusy(run(s, stream({ type: 'done', forest })))).toBe(false)
  })

  // Rule: nothing starts the log but a lookup; an idle start is not "All loaded".
  it('starts empty and idle', () => {
    expect(initialProgress().lines).toEqual([])
    expect(isBusy(initialProgress())).toBe(false)
  })
})

describe('progress model: superseded lookups', () => {
  // Rule: a lookup that replaces the view replaces the log; nothing of the old view remains.
  it('a new lookup clears the old log and its counts', () => {
    const old = run(looked('patience'), { type: 'glimpse-started' }, { type: 'expansion-started', word: 'calm' })
    const s = run(old,
      { type: 'lookup-started', word: 'fire' },
      { type: 'lookup-done', word: 'fire', senses: 2, words: 9, keepForest: false })
    expect(keys(s)).toEqual(['lookup', 'all-loaded'])
    expect(line(s, 'lookup')).toMatchObject({ word: 'fire' })
    expect(pendingOf(s)).toEqual({ lookup: null, nearby: 0, expansions: 0, forest: false })
  })

  // Rule: while a lookup runs, the old view's log stays readable and the summary names the new word.
  it('keeps the old log until the new lookup lands', () => {
    const s = run(looked('patience'), { type: 'lookup-started', word: 'fire' })
    expect(keys(s)).toEqual(['lookup'])
    expect(pendingOf(s).lookup).toBe('fire')
  })

  // Rule: a forest that outlives the lookup (the same word looked up again) keeps its lines and counts.
  it('keeps a forest that is still running when told to', () => {
    const old = run(looked('patience'), { type: 'forest-started' }, hop('f0'))
    const s = run(old,
      { type: 'lookup-started', word: 'patience' },
      { type: 'lookup-done', word: 'patience', senses: 4, words: 23, keepForest: true })
    expect(keys(s)).toEqual(['lookup', 'forging'])
    expect(pendingOf(s).forest).toBe(true)
    expect(line(s, 'forging')).toMatchObject({ drafted: 1 })
  })

  // Rule: Back or Forward to a held view starts a fresh log with nothing pending.
  it('a restored view starts a fresh log', () => {
    const s = run(looked(), { type: 'glimpse-started' }, { type: 'view-restored', keepForest: false })
    expect(s.lines).toEqual([])
    expect(isBusy(s)).toBe(false)
  })

  // Rule: a failed lookup says so and leaves nothing pending.
  it('logs a failed lookup', () => {
    const s = run(looked(), { type: 'lookup-started', word: 'xyz' }, { type: 'lookup-failed', word: 'xyz' })
    expect(line(s, 'lookup-failed:xyz')).toMatchObject({ kind: 'lookup-failed', word: 'xyz' })
    expect(pendingOf(s).lookup).toBeNull()
  })
})
