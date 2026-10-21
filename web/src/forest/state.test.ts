import { describe, it, expect } from 'vitest'
import type { ForestResponse } from '@/types/api'
import patience from '@/fixtures/forest-patience.json'
import { initialForestState, reduceForest, litTarget, type ForestEvent, type ForestState } from './state'

const forest = patience as ForestResponse
const emptyForest: ForestResponse = { ...forest, nodes: [forest.nodes[0]], edges: [], endpoints: [], stats: { generated: 12, kept: 0, rejected: { low_score: 12 } } }
const otherForest: ForestResponse = { ...forest, endpoints: forest.endpoints.slice(0, 2) }

const run = (s: ForestState, ...events: ForestEvent[]) => events.reduce(reduceForest, s)
const start = () => initialForestState('patience')
const loading = () => run(start(), { type: 'forge' })
const settle = (s: ForestState, response = forest): ForestState => reduceForest(s, { type: 'settled', seq: s.seq, response })
const fail = (s: ForestState, error: 'busy' | 'timeout' = 'timeout'): ForestState =>
  reduceForest(s, { type: 'failed', seq: s.seq, error, retryAfterSeconds: error === 'busy' ? 9 : null })
const shown = () => settle(loading())

describe('forest state: request lifecycle', () => {
  it('starts with nothing in flight, no forest, 3 max hops, drawn on the graph', () => {
    expect(start()).toMatchObject({ word: 'patience', maxHops: 3, request: { kind: 'idle' }, content: { kind: 'none' }, onGraph: true, notice: null })
  })

  it('Forge starts a request under a new sequence number', () => {
    const s = loading()
    expect(s.request.kind).toBe('loading')
    expect(s.seq).toBe(start().seq + 1)
  })

  // Floor 12: repeated activation issues no second request.
  it('Forge while a request is in flight changes nothing (single flight)', () => {
    const s = loading()
    expect(reduceForest(s, { type: 'forge' })).toBe(s)
    const reroll = run(shown(), { type: 'forge' })
    expect(reduceForest(reroll, { type: 'forge' })).toBe(reroll)
  })

  it('a response with endpoints shows the forest and announces it', () => {
    const s = shown()
    expect(s.request.kind).toBe('idle')
    expect(s.content).toEqual({ kind: 'forest', response: forest })
    expect(s.notice).toBe('found')
  })

  it('a response with no endpoints, over no forest, is the empty result', () => {
    const s = settle(loading(), emptyForest)
    expect(s.content).toEqual({ kind: 'empty', response: emptyForest })
    expect(s.request.kind).toBe('idle')
  })

  it('a failure over no forest records the kind and its Retry-After', () => {
    const s = fail(loading(), 'busy')
    expect(s.request).toEqual({ kind: 'failed', error: 'busy', retryAfterSeconds: 9 })
    expect(s.content.kind).toBe('none')
  })

  it('Forge after a failure clears the error and tries again', () => {
    const s = run(fail(loading()), { type: 'forge' })
    expect(s.request.kind).toBe('loading')
  })

  it('Forge after an empty result clears the empty message', () => {
    const s = run(settle(loading(), emptyForest), { type: 'forge' })
    expect(s.content.kind).toBe('none')
    expect(s.request.kind).toBe('loading')
  })

  it('Cancel stops the request, announces it, and leaves the content as it was', () => {
    const fromNone = run(loading(), { type: 'cancel' })
    expect(fromNone).toMatchObject({ request: { kind: 'idle' }, content: { kind: 'none' }, notice: 'cancelled' })
    expect(fromNone.seq).toBe(loading().seq + 1)

    const fromShown = run(shown(), { type: 'forge' }, { type: 'cancel' })
    expect(fromShown).toMatchObject({ request: { kind: 'idle' }, content: { kind: 'forest', response: forest } })
  })

  it('Cancel with nothing in flight changes nothing', () => {
    const s = shown()
    expect(reduceForest(s, { type: 'cancel' })).toBe(s)
  })
})

describe('forest state: a shown forest survives a re-roll until a better one lands', () => {
  // Rule: a failed or empty re-roll never removes the forest on screen.
  it.each(['busy', 'timeout'] as const)('a %s failure keeps the shown forest', error => {
    const s = fail(run(shown(), { type: 'forge' }), error)
    expect(s.content).toEqual({ kind: 'forest', response: forest })
    expect(s.request.kind).toBe('failed')
  })

  it('the forest stays on screen while the new one is forged', () => {
    const s = run(shown(), { type: 'forge' })
    expect(s.content).toEqual({ kind: 'forest', response: forest })
  })

  it('an empty re-roll keeps the shown forest and says so', () => {
    const s = settle(run(shown(), { type: 'forge' }), emptyForest)
    expect(s.content).toEqual({ kind: 'forest', response: forest })
    expect(s.notice).toBe('empty-kept')
  })

  it('a new forest replaces the old one and clears every highlight source', () => {
    const lit = run(shown(),
      { type: 'hover', target: { kind: 'node', id: 'dormant seed' } },
      { type: 'focus', target: { kind: 'path', endpointId: 'varve' } },
      { type: 'select', target: { kind: 'path', endpointId: 'keloid' } },
      { type: 'forge' })
    const s = settle(lit, otherForest)
    expect(s.content).toEqual({ kind: 'forest', response: otherForest })
    expect([s.hover, s.focus, s.selection]).toEqual([null, null, null])
  })

  it('a new forest is drawn on the graph even if the last one was hidden', () => {
    const s = settle(run(shown(), { type: 'set-on-graph', onGraph: false }, { type: 'forge' }), otherForest)
    expect(s.onGraph).toBe(true)
  })
})

describe('forest state: stale responses', () => {
  // Rule: a response for a word that is no longer current never renders.
  it('drops a response that lands after another word was committed', () => {
    const inFlight = loading()
    const moved = reduceForest(inFlight, { type: 'word-committed', word: 'bureaucracy' })
    const late = reduceForest(moved, { type: 'settled', seq: inFlight.seq, response: forest })
    expect(late).toBe(moved)
    const lateFail = reduceForest(moved, { type: 'failed', seq: inFlight.seq, error: 'timeout', retryAfterSeconds: null })
    expect(lateFail).toBe(moved)
  })

  it('drops an old response while a newer request is in flight, even one naming the new word', () => {
    const old = loading()
    const newer = run(old, { type: 'word-committed', word: 'bureaucracy' }, { type: 'forge' })
    const late = reduceForest(newer, { type: 'settled', seq: old.seq, response: { ...forest, source: 'bureaucracy' } })
    expect(late).toBe(newer)
    expect(reduceForest(newer, { type: 'failed', seq: old.seq, error: 'timeout', retryAfterSeconds: null })).toBe(newer)
  })

  it('drops a response from a cancelled request', () => {
    const inFlight = loading()
    const cancelled = reduceForest(inFlight, { type: 'cancel' })
    expect(reduceForest(cancelled, { type: 'settled', seq: inFlight.seq, response: forest })).toBe(cancelled)
  })

  // Rule: the sequence number alone identifies the current response. Go and JS
  // normalise words differently, so a server-normalised source must never strand
  // the request in loading.
  it.each(['İstanbul', 'istanbul\u0085', 'Patience'])('settles the current request whatever source the server reports (%j)', source => {
    const s = run(initialForestState('istanbul'), { type: 'forge' })
    const done = reduceForest(s, { type: 'settled', seq: s.seq, response: { ...forest, source } })
    expect(done.request.kind).toBe('idle')
    expect(done.content.kind).toBe('forest')
  })

  it('drops a second response under a sequence that already settled', () => {
    const s = shown()
    expect(reduceForest(s, { type: 'settled', seq: s.seq, response: otherForest })).toBe(s)
  })
})

describe('forest state: the committed word', () => {
  it('another word clears forest, request, notice and highlights, and keeps max hops', () => {
    const s = run(shown(),
      { type: 'set-max-hops', maxHops: 5 },
      { type: 'select', target: { kind: 'path', endpointId: 'varve' } },
      { type: 'forge' },
      { type: 'word-committed', word: 'bureaucracy' })
    expect(s).toMatchObject({ word: 'bureaucracy', maxHops: 5, request: { kind: 'idle' }, content: { kind: 'none' }, notice: null, selection: null, onGraph: true })
    expect(s.seq).toBeGreaterThan(shown().seq)
  })

  it('the same word (a repeat search) changes nothing, not even a request in flight', () => {
    const s = run(shown(), { type: 'forge' })
    expect(reduceForest(s, { type: 'word-committed', word: ' PATIENCE' })).toBe(s)
  })
})

describe('forest state: settings', () => {
  it('max hops is clamped to 1-5 and applies to the next Forge only', () => {
    expect(run(start(), { type: 'set-max-hops', maxHops: 9 }).maxHops).toBe(5)
    expect(run(start(), { type: 'set-max-hops', maxHops: 0 }).maxHops).toBe(1)
    const s = run(loading(), { type: 'set-max-hops', maxHops: 2 })
    expect(s.request.kind).toBe('loading')
    expect(s.seq).toBe(loading().seq)
  })

  it('Show on graph toggles only while there is a forest', () => {
    expect(run(shown(), { type: 'set-on-graph', onGraph: false }).onGraph).toBe(false)
    expect(run(shown(), { type: 'set-on-graph', onGraph: false }, { type: 'set-on-graph', onGraph: true }).onGraph).toBe(true)
    const none = start()
    expect(reduceForest(none, { type: 'set-on-graph', onGraph: false })).toBe(none)
  })
})

describe('forest state: highlight', () => {
  const node = { kind: 'node', id: 'dormant seed' } as const
  const focus = { kind: 'path', endpointId: 'varve' } as const
  const pick = { kind: 'path', endpointId: 'keloid' } as const

  it('lights nothing until something is hovered, focused or selected', () => {
    expect(litTarget(shown())).toBeNull()
  })

  // Rule: the most transient source wins, and the next one down returns when it ends.
  it('hover beats focus beats selection, and each one clearing falls back to the next', () => {
    const all = run(shown(), { type: 'select', target: pick }, { type: 'focus', target: focus }, { type: 'hover', target: node })
    expect(litTarget(all)).toEqual(node)
    const noHover = run(all, { type: 'hover', target: null })
    expect(litTarget(noHover)).toEqual(focus)
    expect(litTarget(run(noHover, { type: 'focus', target: null }))).toEqual(pick)
  })

  it('selecting the same target twice clears it (toggle); a different target replaces it', () => {
    const once = run(shown(), { type: 'select', target: pick })
    expect(once.selection).toEqual(pick)
    expect(run(once, { type: 'select', target: { kind: 'path', endpointId: 'keloid' } }).selection).toBeNull()
    expect(run(once, { type: 'select', target: node }).selection).toEqual(node)
    expect(run(once, { type: 'select', target: null }).selection).toBeNull()
  })

  it('ignores hover, focus and selection when there is no forest', () => {
    for (const s of [start(), loading(), settle(loading(), emptyForest), fail(loading())]) {
      expect(reduceForest(s, { type: 'hover', target: node })).toBe(s)
      expect(reduceForest(s, { type: 'focus', target: node })).toBe(s)
      expect(reduceForest(s, { type: 'select', target: node })).toBe(s)
    }
  })

  it('keeps highlight working on the kept forest during a re-roll and after a failed one', () => {
    for (const s of [run(shown(), { type: 'forge' }), fail(run(shown(), { type: 'forge' }))]) {
      expect(litTarget(reduceForest(s, { type: 'hover', target: node }))).toEqual(node)
    }
  })
})
