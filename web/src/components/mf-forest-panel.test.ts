import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest'
import ftl from '../../../strings/v1/ui.en-GB.ftl?raw'
import type { ForestResponse } from '@/types/api'
import patience from '@/fixtures/forest-patience.json'
import { initStrings } from '@/lib/strings'
import { initialForestState, reduceForest, type ForestEvent, type ForestState } from '@/forest/state'
import { MfForestPanel } from './mf-forest-panel'

const forest = patience as ForestResponse
const run = (s: ForestState, ...events: ForestEvent[]) => events.reduce(reduceForest, s)
const start = () => initialForestState('patience')
const loading = () => run(start(), { type: 'forge' })
const shown = () => { const s = loading(); return reduceForest(s, { type: 'settled', seq: s.seq, response: forest }) }
const failed = (s: ForestState, error: 'busy' | 'timeout' | 'not-configured' | 'invalid-word' | 'failed' | 'network', retryAfterSeconds: number | null = null) =>
  reduceForest(s, { type: 'failed', seq: s.seq, error, retryAfterSeconds })
// Fluent wraps placeables in bidi isolation marks; compare text without them.
const text = (el: Element | null | undefined) => (el?.textContent ?? '').replace(/[⁨⁩]/g, '').replace(/\s+/g, ' ').trim()

beforeAll(async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: () => Promise.resolve(ftl) }))
  await initStrings()
  vi.unstubAllGlobals()
})

describe('MfForestPanel', () => {
  let el: MfForestPanel
  let events: ForestEvent[]
  let lookups: string[]

  async function render(state: ForestState, lit: ReadonlySet<string> | null = null) {
    el.state = state
    el.lit = lit
    await el.updateComplete
  }
  const $ = <T extends Element = HTMLElement>(sel: string) => el.shadowRoot!.querySelector<T>(sel)
  const $$ = <T extends Element = HTMLElement>(sel: string) => [...el.shadowRoot!.querySelectorAll<T>(sel)]
  const primary = () => $<HTMLButtonElement>('[data-testid="forest-primary"]')!
  const items = () => $$('[data-testid="forest-item"]')

  beforeEach(async () => {
    events = []
    lookups = []
    el = new MfForestPanel()
    el.addEventListener('mf-forest-event', e => events.push((e as CustomEvent<ForestEvent>).detail))
    el.addEventListener('mf-forest-lookup', e => lookups.push((e as CustomEvent<{ word: string }>).detail.word))
    document.body.appendChild(el)
    await render(start())
  })

  afterEach(() => el.remove())

  describe('controls', () => {
    it('labels the max steps select visibly, offers 1 to 5, and shows the current value', async () => {
      const select = $<HTMLSelectElement>('select')!
      const label = $<HTMLLabelElement>(`label[for="${select.id}"]`)
      expect(text(label)).toBe('Max steps')
      expect([...select.options].map(o => o.value)).toEqual(['1', '2', '3', '4', '5'])
      expect(select.value).toBe('3')
      expect(text(select.options[0])).toBe('1 step')
    })

    it('changing max steps emits set-max-hops', async () => {
      const select = $<HTMLSelectElement>('select')!
      select.value = '5'
      select.dispatchEvent(new Event('change'))
      expect(events).toEqual([{ type: 'set-max-hops', maxHops: 5 }])
    })

    it('the primary reads Forge with no forest, New forest with one, and Forging… in flight', async () => {
      expect(text(primary())).toBe('Forge')
      await render(shown())
      expect(text(primary())).toBe('New forest')
      await render(loading())
      expect(text(primary())).toBe('Forging…')
      expect(primary().getAttribute('aria-disabled')).toBe('true')
    })

    // Floor 12, at the control: repeated activation in flight issues nothing.
    it('the primary emits forge once, and nothing while a request is in flight', async () => {
      primary().click()
      expect(events).toEqual([{ type: 'forge' }])
      await render(loading())
      primary().click()
      primary().click()
      expect(events).toEqual([{ type: 'forge' }])
    })

    it('keeps the primary focusable while in flight (aria-disabled, not disabled)', async () => {
      await render(loading())
      expect(primary().hasAttribute('disabled')).toBe(false)
    })

    it('shows Cancel only in flight; pressing it emits cancel and returns focus to the primary', async () => {
      expect($('[data-testid="forest-cancel"]')).toBeNull()
      await render(loading())
      const cancel = $<HTMLButtonElement>('[data-testid="forest-cancel"]')!
      cancel.focus()
      cancel.click()
      expect(events).toEqual([{ type: 'cancel' }])
      await render(run(loading(), { type: 'cancel' }))
      expect($('[data-testid="forest-cancel"]')).toBeNull()
      expect(el.shadowRoot!.activeElement).toBe(primary())
    })

    it('offers Show on graph only while there is a forest, and emits its new value', async () => {
      expect($('input[type="checkbox"]')).toBeNull()
      await render(shown())
      const box = $<HTMLInputElement>('input[type="checkbox"]')!
      expect(box.checked).toBe(true)
      expect(text($(`label[for="${box.id}"]`))).toBe('Show on graph')
      box.checked = false
      box.dispatchEvent(new Event('change'))
      expect(events).toEqual([{ type: 'set-on-graph', onGraph: false }])
    })
  })

  describe('status and alerts', () => {
    it('keeps a polite status region and an alert region in the DOM in every state', async () => {
      for (const s of [start(), loading(), shown(), failed(loading(), 'timeout')]) {
        await render(s)
        expect($('[role="status"]')).not.toBeNull()
        expect($('[role="alert"]')).not.toBeNull()
      }
    })

    it('introduces the forge for the committed word before anything is forged, and not over a failure', async () => {
      expect(text($('[data-testid="forest-body"]'))).toContain('Grow fresh metaphors for “patience”')
      await render(failed(loading(), 'not-configured'))
      expect(text($('[data-testid="forest-body"]'))).toBe('')
    })

    it('announces loading, and says the current forest stays during a re-roll', async () => {
      await render(loading())
      expect(text($('[role="status"]'))).toBe('Forging metaphors for “patience”. This can take up to a minute.')
      await render(run(shown(), { type: 'forge' }))
      expect(text($('[role="status"]'))).toContain('The current one stays until it arrives.')
    })

    it('announces what was found, counting the live ones', async () => {
      await render(shown())
      expect(text($('[role="status"]'))).toBe('Found 9 metaphors for “patience”. 6 are live.')
    })

    // Floors 13 and 17: every failure says what happened and names the next action.
    it.each([
      ['invalid-word', null, '“patience” can’t be forged.', 'Look up a different word'],
      ['busy', 12, 'The forge is busy right now.', 'Try again in 12 seconds.'],
      ['busy', null, 'The forge is busy right now.', 'Try again in a moment.'],
      ['failed', null, 'couldn’t grow a forest', 'Try again'],
      ['not-configured', null, 'isn’t turned on for this server', 'Ask the site owner'],
      ['timeout', null, 'took too long', 'choose fewer steps'],
      ['network', null, 'Couldn’t reach the server.', 'Check your connection'],
    ] as const)('renders the %s failure in the alert region with its recovery', async (kind, seconds, what, next) => {
      await render(failed(loading(), kind, seconds))
      const alert = text($('[role="alert"]'))
      expect(alert).toContain(what)
      expect(alert).toContain(next)
      expect(alert).not.toContain('still shown')
    })

    it('says the last forest is still shown when a re-roll fails, and keeps the list', async () => {
      await render(failed(run(shown(), { type: 'forge' }), 'timeout'))
      expect(text($('[role="alert"]'))).toContain('Your last forest is still shown.')
      expect(items()).toHaveLength(9)
    })

    // Floor 18: an empty state says why and what to do next.
    it('explains an empty result and what to do next', async () => {
      const s = loading()
      const empty = { ...forest, nodes: [forest.nodes[0]], edges: [], endpoints: [], stats: { generated: 12, kept: 0, rejected: {} } }
      await render(reduceForest(s, { type: 'settled', seq: s.seq, response: empty }))
      const status = text($('[role="status"]'))
      expect(status).toContain('No metaphors passed the quality check for “patience”')
      expect(status).toContain('tried 12')
      expect(status).toContain('Press Forge to try again')
      expect(items()).toHaveLength(0)
    })

    it('announces a cancel, and whether the last forest is still shown', async () => {
      await render(run(loading(), { type: 'cancel' }))
      expect(text($('[role="status"]'))).toBe('Forging stopped.')
      await render(run(shown(), { type: 'forge' }, { type: 'cancel' }))
      expect(text($('[role="status"]'))).toBe('Forging stopped. Your last forest is still shown.')
    })
  })

  describe('endpoint list', () => {
    beforeEach(async () => { await render(shown()) })

    it('lists every endpoint in API order', () => {
      expect(items().map(i => text(i.querySelector('h3')))).toEqual(forest.endpoints.map(e => e.id))
    })

    it('shows the line, the path as words with each ground between them, and the score', () => {
      const keloid = items()[5]
      expect(text(keloid.querySelector('h3'))).toBe('keloid')
      expect(text(keloid.querySelector('.line'))).toBe(forest.endpoints[5].line)
      const steps = [...keloid.querySelectorAll('.path > li')]
      expect(steps.map(s => text(s.querySelector('.word')))).toEqual(['patience', 'scar tissue', 'hypertrophic scar', 'keloid'])
      expect(steps.map(s => text(s.querySelector('.ground-text')))).toEqual([
        'closes over damage and holds', 'thickens and stiffens over months', 'raised and thickened', '',
      ])
      expect(text(keloid.querySelector('.score'))).toContain('Score 7 out of 10')
    })

    // Floor 5: live is text, not colour alone.
    it('marks Live in text at a score of 7 or more, and only then', () => {
      const live = items().map(i => text(i.querySelector('.live')).endsWith('Live'))
      expect(live).toEqual(forest.endpoints.map(e => e.score >= 7))
    })

    it('renders model text as text, never as markup', async () => {
      const hostile = '<img src=x onerror=alert(1)>'
      const evil: ForestResponse = {
        ...forest,
        endpoints: [{ ...forest.endpoints[0], line: hostile, grounds: [hostile], path: ['patience', 'sacrificial anode'] }],
      }
      const s = loading()
      await render(reduceForest(s, { type: 'settled', seq: s.seq, response: evil }))
      expect(el.shadowRoot!.querySelector('img')).toBeNull()
      expect(text(items()[0].querySelector('.line'))).toBe(hostile)
    })

    it('mouse hover on an item lights its path; leaving clears it; touch sets no hover', () => {
      const item = items()[3]
      item.dispatchEvent(Object.assign(new Event('pointerenter'), { pointerType: 'mouse' }))
      item.dispatchEvent(Object.assign(new Event('pointerleave'), { pointerType: 'mouse' }))
      item.dispatchEvent(Object.assign(new Event('pointerenter'), { pointerType: 'touch' }))
      expect(events).toEqual([
        { type: 'hover', target: { kind: 'path', endpointId: 'seed vault' } },
        { type: 'hover', target: null },
      ])
    })

    it('focus inside an item lights its path; focus leaving clears it', () => {
      const button = items()[4].querySelector('button')!
      button.dispatchEvent(new FocusEvent('focusin', { bubbles: true }))
      button.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))
      expect(events).toEqual([
        { type: 'focus', target: { kind: 'path', endpointId: 'varve' } },
        { type: 'focus', target: null },
      ])
    })

    it('moving focus between controls of the same item keeps its path lit', () => {
      const [highlight, lookup] = [...items()[4].querySelectorAll('button')]
      highlight.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: lookup }))
      expect(events).toEqual([])
    })

    it('Highlight path toggles the selection and reflects it with aria-pressed', async () => {
      const toggle = () => items()[2].querySelector<HTMLButtonElement>('[data-testid="forest-highlight"]')!
      expect(toggle().getAttribute('aria-pressed')).toBe('false')
      toggle().click()
      expect(events).toEqual([{ type: 'select', target: { kind: 'path', endpointId: 'bog body' } }])
      await render(run(shown(), { type: 'select', target: { kind: 'path', endpointId: 'bog body' } }))
      expect(toggle().getAttribute('aria-pressed')).toBe('true')
    })

    it('Escape from the head controls clears the selection too', async () => {
      await render(run(shown(), { type: 'select', target: { kind: 'path', endpointId: 'bog body' } }))
      $<HTMLSelectElement>('select')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, composed: true }))
      expect(events).toEqual([{ type: 'select', target: null }])
    })

    it('Escape in the list clears the selection', async () => {
      await render(run(shown(), { type: 'select', target: { kind: 'path', endpointId: 'bog body' } }))
      items()[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
      expect(events).toEqual([{ type: 'select', target: null }])
    })

    it('Look up emits the endpoint word for a lookup', () => {
      items()[1].querySelector<HTMLButtonElement>('[data-testid="forest-lookup"]')!.click()
      expect(lookups).toEqual(['escapement'])
    })

    it('marks the items whose paths are lit', async () => {
      await render(shown(), new Set(['seed vault', 'controlled burn']))
      expect(items().filter(i => i.hasAttribute('data-lit')).map(i => text(i.querySelector('h3')))).toEqual(['seed vault', 'controlled burn'])
    })
  })

  it('is a region landmark named by its heading', () => {
    const region = $('section[aria-labelledby]')!
    expect(text($(`#${region.getAttribute('aria-labelledby')}`))).toBe('Metaphor forest')
    expect(region.contains($('[data-testid="forest-primary"]'))).toBe(true)
  })

  // Floor 2: every interactive element is a semantic control with a name.
  it('uses only named buttons, selects and inputs as controls', async () => {
    for (const s of [start(), loading(), shown()]) {
      await render(s)
      for (const c of $$('button, select, input')) {
        const name = c.getAttribute('aria-label') ?? (c.id ? text($(`label[for="${c.id}"]`)) : '') ?? ''
        expect((name || text(c)).length, c.outerHTML).toBeGreaterThan(0)
      }
      expect($$('[role="button"], [onclick]')).toHaveLength(0)
    }
  })

  describe('phone sheet', () => {
    it('renders the sheet toggle only while there is a list', async () => {
      expect($('[data-testid="forest-sheet-toggle"]')).toBeNull()
      await render(shown())
      expect($('[data-testid="forest-sheet-toggle"]')).not.toBeNull()
    })

    it('Escape from the head controls collapses the open sheet when nothing is selected', async () => {
      await render(loading())
      await render(shown())
      expect(el.hasAttribute('sheet-open')).toBe(true)
      primary().dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, composed: true }))
      await el.updateComplete
      expect(el.hasAttribute('sheet-open')).toBe(false)
      expect(events).toEqual([])
    })

    it('opens the sheet when a new forest arrives, and the toggle collapses it', async () => {
      await render(loading())
      await render(shown())
      const toggle = $<HTMLButtonElement>('[data-testid="forest-sheet-toggle"]')!
      expect(toggle.getAttribute('aria-expanded')).toBe('true')
      expect(el.hasAttribute('sheet-open')).toBe(true)
      toggle.click()
      await el.updateComplete
      expect(toggle.getAttribute('aria-expanded')).toBe('false')
      expect(text(toggle)).toBe('Show 9 metaphors')
    })
  })

  describe('streaming', () => {
    type StreamEvent = Extract<ForestEvent, { type: 'stream' }>['event']
    const stream = (s: ForestState, ...evs: StreamEvent[]) =>
      evs.reduce((acc, event) => reduceForest(acc, { type: 'stream', seq: acc.seq, event }), s)
    const hop = (pathId: string, from: string, to: string): StreamEvent => ({ type: 'hop', pathId, facet: 0, from, to, ground: 'g' })
    const snapshot = (n: number): StreamEvent => ({ type: 'forest', forest: { ...forest, endpoints: forest.endpoints.slice(0, n) } })
    const status = () => text($('[role="status"]'))

    // Rule: while streaming, the status counts the metaphors of the latest snapshot.
    it('says how many metaphors are forged so far, from the latest snapshot', async () => {
      const first = stream(loading(), hop('f0', 'patience', 'dormant seed'))
      expect(first.request.kind).toBe('streaming')
      await render(first)
      expect(status()).toBe('Forging… no metaphors so far')
      await render(stream(first, snapshot(1)))
      expect(status()).toBe('Forging… 1 metaphor so far')
      const four = stream(first, snapshot(1), snapshot(4), hop('f1', 'patience', 'peat bog'))
      await render(four)
      expect(status()).toBe('Forging… 4 metaphors so far')
      // a re-roll counts only its own snapshots, not the forest still shown
      const reroll = stream(run(shown(), { type: 'forge' }), hop('f0', 'patience', 'dormant seed'))
      await render(reroll)
      expect(items()).toHaveLength(9)
      expect(status()).toBe('Forging… no metaphors so far')
    })

    // Rule: the list only ever shows judged metaphors, from the latest snapshot.
    it('lists the latest snapshot and nothing a hop or verdict adds', async () => {
      const s = stream(loading(), hop('f0', 'patience', 'dormant seed'), snapshot(2), hop('f0b0', 'dormant seed', 'seed vault'), { type: 'kept', pathId: 'f0b0', endpoint: 'seed vault', score: 7 })
      await render(s)
      expect(items().map(i => text(i.querySelector('h3')))).toEqual(forest.endpoints.slice(0, 2).map(e => e.id))
    })

    it('keeps the in-flight controls while streaming', async () => {
      await render(stream(loading(), snapshot(2)))
      expect(text(primary())).toBe('Forging…')
      expect(primary().getAttribute('aria-disabled')).toBe('true')
      expect($('[data-testid="forest-cancel"]')).not.toBeNull()
      expect($('#forest-on-graph')).not.toBeNull()
      primary().click()
      expect(events).toEqual([])
    })

    it('Cancel while streaming returns focus to the primary and says the forest is kept', async () => {
      const s = stream(loading(), snapshot(2))
      await render(s)
      const cancel = $<HTMLButtonElement>('[data-testid="forest-cancel"]')!
      cancel.focus()
      cancel.click()
      await render(reduceForest(s, { type: 'cancel' }))
      expect(el.shadowRoot!.activeElement).toBe(primary())
      expect(status()).toBe('Forging stopped. Your last forest is still shown.')
      expect(items()).toHaveLength(2)
    })

    it('a stream error keeps the list and says the last forest is still shown', async () => {
      await render(stream(loading(), snapshot(2), { type: 'error', kind: 'timeout' }))
      expect(text($('[role="alert"]'))).toContain('Your last forest is still shown.')
      expect(items()).toHaveLength(2)
    })

    // Rule: the sheet opens once for a stream; later snapshots never reopen a sheet the user closed.
    it('opens the phone sheet on the first snapshot only', async () => {
      const first = stream(loading(), snapshot(1))
      await render(loading())
      await render(first)
      expect(el.hasAttribute('sheet-open')).toBe(true)
      $<HTMLButtonElement>('[data-testid="forest-sheet-toggle"]')!.click()
      await el.updateComplete
      expect(el.hasAttribute('sheet-open')).toBe(false)
      const later = stream(first, snapshot(3))
      await render(later)
      await render(stream(later, { type: 'done', forest }))
      expect(el.hasAttribute('sheet-open')).toBe(false)
    })
  })
})
