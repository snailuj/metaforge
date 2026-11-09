import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest'
import ftl from '../../../strings/v1/ui.en-GB.ftl?raw'
import { initStrings } from '@/lib/strings'
import { initialProgress, reduceProgress, type ProgressEvent, type ProgressState } from '@/progress/model'
import { MfLookupOverlay, SHOW_DELAY_MS } from './mf-lookup-overlay'

const text = (el: Element | null | undefined) => (el?.textContent ?? '').replace(/[⁨⁩]/g, '').replace(/\s+/g, ' ').trim()
const run = (s: ProgressState, ...events: ProgressEvent[]) => events.reduce(reduceProgress, s)
const looked = () => run(initialProgress(),
  { type: 'lookup-started', word: 'patience' },
  { type: 'lookup-done', word: 'patience', senses: 4, words: 23, keepForest: false })
// 3 of 5 nearby words still owed.
const glimpsing = () => run(looked(), { type: 'glimpses-waiting', n: 2 },
  { type: 'glimpse-started' }, { type: 'glimpse-started' }, { type: 'glimpse-started' }, { type: 'glimpse-done' }, { type: 'glimpse-done' })
const ended = (s: ProgressState) => run(s, { type: 'glimpse-done' }, { type: 'glimpses-waiting', n: 0 })

interface FakeAnimation { keyframes: Keyframe[]; options: KeyframeAnimationOptions; finish: () => void; cancel: () => void; finished: Promise<void> }

beforeAll(async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: () => Promise.resolve(ftl) }))
  await initStrings()
  vi.unstubAllGlobals()
})

describe('MfLookupOverlay', () => {
  let el: MfLookupOverlay
  let docked: number
  let animations: FakeAnimation[]
  const card = () => el.shadowRoot!.querySelector<HTMLElement>('[data-testid="lookup-overlay"]')
  const target = new DOMRect(900, 700, 100, 44)

  async function mount({ reduce = false, animate = true } = {}) {
    vi.stubGlobal('matchMedia', vi.fn((q: string) => ({ matches: reduce && q.includes('reduce'), media: q })))
    el = new MfLookupOverlay()
    el.state = looked()
    el.dockTarget = () => target
    el.addEventListener('mf-lookup-docked', () => docked++)
    document.body.appendChild(el)
    await el.updateComplete
    if (!animate) return
    // Every card the overlay renders gets a controllable animation.
    vi.spyOn(HTMLElement.prototype, 'animate').mockImplementation(function (this: HTMLElement, keyframes, options) {
      let resolve!: () => void, reject!: (e: unknown) => void
      const finished = new Promise<void>((res, rej) => { resolve = res; reject = rej })
      finished.catch(() => {})
      const a: FakeAnimation = {
        keyframes: keyframes as Keyframe[], options: options as KeyframeAnimationOptions, finished,
        finish: () => resolve(), cancel: () => reject(new DOMException('cancelled', 'AbortError')),
      }
      animations.push(a)
      return a as unknown as Animation
    })
  }
  async function show(state: ProgressState, active: boolean) {
    el.state = state
    el.active = active
    await el.updateComplete
  }
  async function shown() {
    await show(glimpsing(), true)
    vi.advanceTimersByTime(SHOW_DELAY_MS)
    await el.updateComplete
  }
  async function flush() {
    for (let i = 0; i < 4; i++) { await Promise.resolve(); await el.updateComplete }
  }

  beforeEach(() => {
    vi.useFakeTimers()
    docked = 0
    animations = []
  })

  afterEach(() => {
    el?.remove()
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  // Rule: the card shows only once nearby work has lasted the show delay, so a
  // fast batch never flashes it.
  it('appears after the show delay, and never for work that ends sooner', async () => {
    await mount()
    expect(card()).toBeNull()
    await show(glimpsing(), true)
    expect(card()).toBeNull()
    vi.advanceTimersByTime(SHOW_DELAY_MS - 1)
    await show(ended(glimpsing()), false)
    vi.advanceTimersByTime(SHOW_DELAY_MS)
    await flush()
    expect(card()).toBeNull()
    expect(docked).toBe(0)
    expect(animations).toHaveLength(0)

    await shown()
    expect(card()).not.toBeNull()
  })

  // Rule: the card says what is still coming in the activity panel's words, and
  // how far the nearby words have got.
  it('shows the activity summary and the nearby count', async () => {
    await mount()
    await shown()
    expect(text(card()!.querySelector('[data-testid="lookup-summary"]'))).toBe('Still loading 3 nearby words. More will appear on the graph.')
    const bar = card()!.querySelector('[role="progressbar"]')!
    expect(bar.getAttribute('aria-valuenow')).toBe('2')
    expect(bar.getAttribute('aria-valuemax')).toBe('5')
    expect(text(card()!.querySelector('[data-testid="lookup-count"]'))).toBe('Fetching nearby words: 2 of 5.')
    // Screen readers hear once that the graph is paused.
    expect(text(el.shadowRoot!.querySelector('[role="status"]'))).toContain('paused')
  })

  // Rule: when the work ends, the card flies into the activity button, then
  // goes and says it has docked.
  it('docks into the activity button when the work ends', async () => {
    await mount()
    await shown()
    await show(ended(glimpsing()), false)
    expect(animations).toHaveLength(1)
    const last = animations[0].keyframes.at(-1)!
    expect(String(last.transform)).toMatch(/translate\(.+\) scale\(.+\)/)
    expect(card()).not.toBeNull()
    expect(docked).toBe(0)
    animations[0].finish()
    await flush()
    expect(card()).toBeNull()
    expect(docked).toBe(1)
  })

  // Rule: new nearby work during the dock stops it and the card stays.
  it('stays when nearby work restarts mid-dock', async () => {
    await mount()
    await shown()
    await show(ended(glimpsing()), false)
    await show(glimpsing(), true)
    await flush()
    expect(card()).not.toBeNull()
    expect(docked).toBe(0)
    // A second end docks again.
    await show(ended(glimpsing()), false)
    expect(animations).toHaveLength(2)
  })

  // Rule: with reduced motion the card fades where it is; it does not fly.
  it('fades without moving under reduced motion', async () => {
    await mount({ reduce: true })
    await shown()
    await show(ended(glimpsing()), false)
    expect(animations[0].keyframes.some(k => k.transform !== undefined)).toBe(false)
    animations[0].finish()
    await flush()
    expect(docked).toBe(1)
  })

  // Rule: without a dock target the card still goes and reports docking.
  it('goes at once when there is nothing to dock into', async () => {
    await mount()
    el.dockTarget = () => null
    await shown()
    await show(ended(glimpsing()), false)
    await flush()
    expect(animations).toHaveLength(0)
    expect(card()).toBeNull()
    expect(docked).toBe(1)
  })
})
