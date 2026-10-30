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

describe('forest state: streaming', () => {
  type StreamEvent = Extract<ForestEvent, { type: 'stream' }>['event']
  const stream = (s: ForestState, ...events: StreamEvent[]) =>
    events.reduce((acc, event) => reduceForest(acc, { type: 'stream', seq: acc.seq, event }), s)
  const hop = (pathId: string, from: string, to: string): StreamEvent =>
    ({ type: 'hop', pathId, facet: Number(pathId.slice(1, 2)), from, to, ground: `${from} to ${to}` })
  const kept = (pathId: string, endpoint: string): StreamEvent => ({ type: 'kept', pathId, endpoint, score: 7 })
  const rejected = (pathId: string): StreamEvent => ({ type: 'rejected', pathId, reason: 'low_score' })
  const snapshot = (n: number): ForestResponse => ({ ...forest, endpoints: forest.endpoints.slice(0, n) })
  const pathsOf = (s: ForestState) => {
    if (s.request.kind !== 'streaming') throw new Error(`expected streaming, got ${s.request.kind}`)
    return s.request.paths
  }

  it('the first stream event turns the request into streaming, with that path pending', () => {
    const s = stream(loading(), hop('f0', 'patience', 'dormant seed'))
    expect(s.request.kind).toBe('streaming')
    expect(pathsOf(s).f0).toMatchObject({ status: 'pending', hops: [{ from: 'patience', to: 'dormant seed' }] })
    expect(s.seq).toBe(loading().seq)
  })

  // Rule: a stage event is progress for the activity log only; the forest state ignores it,
  // so a stream with or without stage events reaches the same state.
  it('ignores stage events wherever they arrive, so a stream without them works the same', () => {
    const drafting: StreamEvent = { type: 'stage', stage: 'drafting' }
    const judging: StreamEvent = { type: 'stage', stage: 'judging', facet: 0, word: 'dormant seed' }
    const before = loading()
    expect(reduceForest(before, { type: 'stream', seq: before.seq, event: drafting })).toBe(before)
    const mid = stream(loading(), hop('f0', 'patience', 'dormant seed'))
    expect(reduceForest(mid, { type: 'stream', seq: mid.seq, event: judging })).toBe(mid)
    const withStages = stream(loading(), drafting, hop('f0', 'patience', 'dormant seed'), judging, kept('f0', 'dormant seed'))
    const without = stream(loading(), hop('f0', 'patience', 'dormant seed'), kept('f0', 'dormant seed'))
    expect(withStages.request.kind).toBe('streaming')
    expect(withStages).toEqual(without)
  })

  it('hops for one path id extend that path in order', () => {
    const s = stream(loading(), hop('f0', 'patience', 'dormant seed'), hop('f0b0', 'dormant seed', 'seed vault'), hop('f0b0', 'seed vault', 'ark'))
    expect(pathsOf(s).f0b0.hops.map(h => h.to)).toEqual(['seed vault', 'ark'])
    expect(pathsOf(s).f0.hops).toHaveLength(1)
  })

  // Rule: every pending path resolves exactly once; later verdicts and hops for it change nothing.
  it('every pending path resolves exactly once', () => {
    const s = stream(loading(), hop('f0', 'patience', 'dormant seed'), hop('f0b0', 'dormant seed', 'seed vault'), hop('f0b1', 'dormant seed', 'ark'))
    const k = stream(s, kept('f0b0', 'seed vault'), rejected('f0b1'))
    expect(pathsOf(k).f0b0.status).toBe('kept')
    expect(pathsOf(k).f0b1.status).toBe('rejected')
    expect(pathsOf(k).f0.status).toBe('pending')
    for (const late of [rejected('f0b0'), kept('f0b0', 'other'), kept('f0b1', 'ark'), hop('f0b0', 'seed vault', 'x')]) {
      expect(stream(k, late)).toBe(k)
    }
  })

  it('a verdict for a path that never had a hop changes nothing', () => {
    const s = stream(loading(), hop('f0', 'patience', 'dormant seed'))
    expect(stream(s, kept('f7b0', 'ghost'))).toBe(s)
  })

  // Rule: the shown forest only ever comes from a snapshot, so the list never holds an unjudged path.
  it('hops and verdicts never change the shown content; each snapshot replaces it', () => {
    const before = run(shown(), { type: 'forge' })
    const s = stream(before, hop('f0', 'patience', 'dormant seed'), kept('f0', 'dormant seed'))
    expect(s.request.kind).toBe('streaming')
    expect(s.content).toBe(before.content)
    const first = stream(s, { type: 'forest', forest: snapshot(2) })
    expect(first.content).toEqual({ kind: 'forest', response: snapshot(2) })
    const second = stream(first, { type: 'forest', forest: snapshot(4) })
    expect(second.content).toEqual({ kind: 'forest', response: snapshot(4) })
    expect(second.request).toMatchObject({ kind: 'streaming', snapshot: snapshot(4) })
  })

  it('a snapshot with no endpoints yet keeps the forest already shown', () => {
    const before = run(shown(), { type: 'forge' })
    const s = stream(before, { type: 'forest', forest: emptyForest })
    expect(s.content).toBe(before.content)
    expect(s.request).toMatchObject({ kind: 'streaming', snapshot: emptyForest })
  })

  it('the first snapshot of a re-roll clears highlights on the old forest; later ones keep them', () => {
    const pick = { kind: 'path', endpointId: 'varve' } as const
    const lit = run(shown(), { type: 'select', target: pick }, { type: 'forge' })
    expect(lit.selection).toEqual(pick)
    const first = stream(lit, { type: 'forest', forest: snapshot(2) })
    expect(first.selection).toBeNull()
    const picked = run(first, { type: 'select', target: { kind: 'path', endpointId: 'escapement' } })
    expect(picked.selection).not.toBeNull()
    const later = stream(picked, { type: 'forest', forest: snapshot(4) }, { type: 'done', forest })
    expect(later.selection).toEqual({ kind: 'path', endpointId: 'escapement' })
    expect(later.request.kind).toBe('idle')
  })

  it('done ends the stream with the final forest and announces it', () => {
    const s = stream(loading(), hop('f0', 'patience', 'dormant seed'), { type: 'forest', forest: snapshot(2) }, { type: 'done', forest })
    expect(s).toMatchObject({ request: { kind: 'idle' }, content: { kind: 'forest', response: forest }, notice: 'found' })
  })

  it('a cache hit (a lone done) settles like a whole response', () => {
    const s = stream(loading(), { type: 'done', forest })
    expect(s).toMatchObject({ request: { kind: 'idle' }, content: { kind: 'forest', response: forest }, notice: 'found' })
  })

  it('Forge while streaming changes nothing (single flight)', () => {
    const s = stream(loading(), hop('f0', 'patience', 'dormant seed'))
    expect(s.request.kind).toBe('streaming')
    expect(reduceForest(s, { type: 'forge' })).toBe(s)
  })

  // Rule: cancel and a stream error keep what was kept and drop every pending path.
  it('Cancel mid-stream keeps the last snapshot, clears pending paths and says so', () => {
    const s = stream(loading(), hop('f0', 'patience', 'dormant seed'), { type: 'forest', forest: snapshot(2) }, hop('f1', 'patience', 'peat bog'))
    expect(Object.keys(pathsOf(s))).toEqual(['f0', 'f1'])
    const c = reduceForest(s, { type: 'cancel' })
    expect(c).toMatchObject({ request: { kind: 'idle' }, content: { kind: 'forest', response: snapshot(2) }, notice: 'cancelled' })
    expect(c.seq).toBe(s.seq + 1)
  })

  it.each([
    ['an error event', (s: ForestState) => stream(s, { type: 'error', kind: 'timeout' })],
    ['a failure thrown by the client', (s: ForestState) => reduceForest(s, { type: 'failed', seq: s.seq, error: 'timeout', retryAfterSeconds: null })],
  ])('%s mid-stream keeps the last snapshot and clears pending paths', (_label, failWith) => {
    const s = stream(loading(), hop('f0', 'patience', 'dormant seed'), { type: 'forest', forest: snapshot(2) })
    expect(s.request.kind).toBe('streaming')
    const f = failWith(s)
    expect(f.request).toEqual({ kind: 'failed', error: 'timeout', retryAfterSeconds: null })
    expect(f.content).toEqual({ kind: 'forest', response: snapshot(2) })
  })

  // Rule: a stream event from a superseded request never changes anything.
  it('drops stream events from a request that was cancelled, replaced or moved to another word', () => {
    const live = stream(loading(), hop('f0', 'patience', 'dormant seed'))
    const old = live.seq
    const superseded = [
      reduceForest(live, { type: 'cancel' }),
      run(live, { type: 'cancel' }, { type: 'forge' }),
      run(live, { type: 'word-committed', word: 'bureaucracy' }, { type: 'forge' }),
    ]
    const late: StreamEvent[] = [hop('f0b0', 'dormant seed', 'seed vault'), kept('f0', 'dormant seed'), { type: 'forest', forest }, { type: 'done', forest }, { type: 'error', kind: 'failed' }]
    for (const s of superseded) {
      expect(s.seq).not.toBe(old)
      for (const event of late) expect(reduceForest(s, { type: 'stream', seq: old, event })).toBe(s)
    }
  })
})
