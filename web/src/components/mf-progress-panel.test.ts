import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest'
import ftl from '../../../strings/v1/ui.en-GB.ftl?raw'
import { initStrings } from '@/lib/strings'
import { initialProgress, reduceProgress, type ProgressEvent, type ProgressState } from '@/progress/model'
import { MfProgressPanel, LABEL_CYCLE_MS } from './mf-progress-panel'

// Fluent wraps placeables in bidi isolation marks; compare text without them.
const text = (el: Element | null | undefined) => (el?.textContent ?? '').replace(/[⁨⁩]/g, '').replace(/\s+/g, ' ').trim()
const run = (s: ProgressState, ...events: ProgressEvent[]) => events.reduce(reduceProgress, s)
const busy = () => run(initialProgress(), { type: 'lookup-started', word: 'patience' })
const looked = () => run(initialProgress(),
  { type: 'lookup-started', word: 'patience' },
  { type: 'lookup-done', word: 'patience', senses: 4, words: 23, keepForest: false })
const glimpsing = () => run(looked(), { type: 'glimpses-waiting', n: 17 }, { type: 'glimpse-started' }, { type: 'glimpse-started' }, { type: 'glimpse-started' })
const LABELS = ['Foraging ...', 'Forging ...', 'Fording ...', 'Foresting ...']

beforeAll(async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: () => Promise.resolve(ftl) }))
  await initStrings()
  vi.unstubAllGlobals()
})

describe('MfProgressPanel', () => {
  let el: MfProgressPanel
  let toggles: boolean[]
  const $ = <T extends Element = HTMLElement>(sel: string) => el.shadowRoot!.querySelector<T>(sel)
  const $$ = (sel: string) => [...el.shadowRoot!.querySelectorAll(sel)]
  const toggle = () => $<HTMLButtonElement>('[data-testid="progress-toggle"]')!
  const panel = () => $('[data-testid="progress-panel"]')!
  const status = () => $('[role="status"]')!
  const alert = () => $('[role="alert"]')!

  async function mount(state: ProgressState, { reduce = false } = {}) {
    vi.stubGlobal('matchMedia', vi.fn((q: string) => ({ matches: reduce && q.includes('reduce'), media: q })))
    el = new MfProgressPanel()
    el.state = state
    el.addEventListener('mf-progress-toggle', e => toggles.push((e as CustomEvent<{ open: boolean }>).detail.open))
    document.body.appendChild(el)
    await el.updateComplete
  }
  async function show(state: ProgressState) {
    el.state = state
    await el.updateComplete
  }

  beforeEach(() => {
    toggles = []
    localStorage.clear()
  })

  afterEach(() => {
    el?.remove()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  describe('collapsed', () => {
    // Rule: the throbber and cycling label show exactly while work is pending;
    // idle, the control is a plain "Activity" button.
    it('shows the throbber only while work is pending', async () => {
      await mount(initialProgress())
      expect($('.throbber')).toBeNull()
      expect(text(toggle())).toBe('Activity')
      await show(busy())
      expect($('.throbber')).not.toBeNull()
      expect(text(toggle())).toBe('Foraging ...')
      await show(looked())
      expect($('.throbber')).toBeNull()
      expect(text(toggle())).toBe('Activity')
    })

    // Rule: the control is a named button that says whether the panel is open.
    it('is a named button with aria-expanded and controls the panel', async () => {
      await mount(busy())
      expect(toggle().tagName).toBe('BUTTON')
      expect(toggle().getAttribute('aria-label')).toBe('Activity: still loading')
      expect(toggle().getAttribute('aria-expanded')).toBe('false')
      expect(toggle().getAttribute('aria-controls')).toBe(panel().id)
      expect(panel().hidden).toBe(true)
    })

    // Rule: while busy the label cycles every 1.5 s through the four labels and wraps.
    it('cycles the label every 1.5 s while work is pending', async () => {
      vi.useFakeTimers()
      await mount(busy())
      const seen = [text(toggle())]
      for (let i = 0; i < 4; i++) {
        await vi.advanceTimersByTimeAsync(LABEL_CYCLE_MS)
        seen.push(text(toggle()))
      }
      expect(LABEL_CYCLE_MS).toBe(1500)
      expect(seen).toEqual([...LABELS, LABELS[0]])
      // Idle stops the cycle; busy again starts it from the first label.
      await show(looked())
      await vi.advanceTimersByTimeAsync(LABEL_CYCLE_MS)
      await show(busy())
      expect(text(toggle())).toBe(LABELS[0])
    })

    // Rule: with reduced motion the label holds on "Foraging ..." and the throbber does not spin.
    it('holds still under reduced motion', async () => {
      vi.useFakeTimers()
      await mount(busy(), { reduce: true })
      await vi.advanceTimersByTimeAsync(LABEL_CYCLE_MS * 3)
      expect(text(toggle())).toBe(LABELS[0])
      const css = (MfProgressPanel.styles as { cssText: string }).cssText
      const spin = css.indexOf('animation:')
      expect(spin).toBeGreaterThan(css.indexOf('@media (prefers-reduced-motion: no-preference)'))
      expect(css.match(/animation:|transition:/g)).toHaveLength(css.split('@media (prefers-reduced-motion: no-preference)').length - 1)
    })
  })

  describe('expanded', () => {
    // Rule: the panel opens on the button, starts with a summary of what is still coming,
    // then the log, newest last.
    it('opens to a summary and the log', async () => {
      await mount(glimpsing())
      toggle().click()
      await el.updateComplete
      expect(panel().hidden).toBe(false)
      expect(toggle().getAttribute('aria-expanded')).toBe('true')
      expect(toggles).toEqual([true])
      expect(text($('[data-testid="progress-summary"]'))).toBe('Still loading 20 nearby words. More will appear on the graph.')
      expect($$('[data-testid="progress-line"]').map(text)).toEqual(['Looked up patience: 4 senses, 23 words.', 'Fetching nearby words: 0 of 20.'])
      await show(run(glimpsing(), { type: 'forest-started' }))
      expect(text($('[data-testid="progress-summary"]'))).toBe('Still loading 20 nearby words and the metaphor forest. More will appear on the graph.')
    })

    // Rule: a counting line is one list item whose text updates in place.
    it('updates a counting line in place', async () => {
      await mount(glimpsing())
      toggle().click()
      await el.updateComplete
      const before = $$('[data-testid="progress-line"]')
      await show(run(glimpsing(), { type: 'glimpse-done' }, { type: 'glimpse-done' }))
      const after = $$('[data-testid="progress-line"]')
      expect(after).toHaveLength(before.length)
      expect(after[1]).toBe(before[1])
      expect(text(after[1])).toBe('Fetching nearby words: 2 of 20.')
    })

    // Rule: idle and empty, the panel says why it is empty and what to do.
    it('says what to do when nothing has loaded yet', async () => {
      await mount(initialProgress())
      toggle().click()
      await el.updateComplete
      expect(text($('[data-testid="progress-summary"]'))).toBe('Nothing has loaded yet. Look up a word and its progress shows here.')
    })

    // Rule: Escape closes the panel and returns focus to the button, from inside the panel or on it.
    it('closes on Escape and returns focus to the button', async () => {
      await mount(looked())
      toggle().click()
      await el.updateComplete
      panel().focus()
      panel().dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, composed: true }))
      await el.updateComplete
      expect(panel().hidden).toBe(true)
      expect(el.shadowRoot!.activeElement).toBe(toggle())
      expect(toggles).toEqual([true, false])
      // Escape while closed does nothing.
      toggle().dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, composed: true }))
      await el.updateComplete
      expect(toggles).toEqual([true, false])
    })

    // Rule: the open or closed choice is remembered in this browser.
    it('remembers open and closed across mounts', async () => {
      await mount(looked())
      toggle().click()
      await el.updateComplete
      el.remove()
      await mount(looked())
      expect(panel().hidden).toBe(false)
      expect(el.open).toBe(true)
      toggle().click()
      await el.updateComplete
      el.remove()
      await mount(looked())
      expect(panel().hidden).toBe(true)
    })

    // Rule: storage that throws never breaks the panel; it is logged and the panel starts closed.
    it('works when storage throws', async () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
      const get = vi.spyOn(localStorage, 'getItem').mockImplementation(() => { throw new Error('blocked') })
      const set = vi.spyOn(localStorage, 'setItem').mockImplementation(() => { throw new Error('blocked') })
      await mount(looked())
      expect(panel().hidden).toBe(true)
      toggle().click()
      await el.updateComplete
      expect(panel().hidden).toBe(false)
      expect(warn).toHaveBeenCalled()
      get.mockRestore()
      set.mockRestore()
      warn.mockRestore()
    })
  })

  describe('announcements', () => {
    // Rule: the polite live region gets each new log line, never the cycling label or a count update.
    it('announces new lines, not label changes or count updates', async () => {
      vi.useFakeTimers()
      await mount(busy())
      expect(text(status())).toBe('')
      await vi.advanceTimersByTimeAsync(LABEL_CYCLE_MS)
      expect(text(toggle())).toBe(LABELS[1]) // the label did change
      expect(text(status())).toBe('')
      await show(looked())
      expect(text(status())).toBe('Looked up patience: 4 senses, 23 words. All loaded.')
      await show(glimpsing())
      expect(text(status())).toBe('Fetching nearby words: 0 of 20.')
      await show(run(glimpsing(), { type: 'glimpse-done' }))
      expect(text(status())).toBe('Fetching nearby words: 0 of 20.')
      expect(text(toggle())).not.toBe('')
      expect(status().getAttribute('aria-live')).toBe('polite')
    })

    // Rule: a failure line is announced as an alert.
    it('announces a failure line in the alert region', async () => {
      await mount(glimpsing())
      await show(run(glimpsing(), { type: 'glimpse-failed' }))
      expect(text(alert())).toBe('1 nearby word could not be fetched. Click a word to try it again.')
    })
  })
})
