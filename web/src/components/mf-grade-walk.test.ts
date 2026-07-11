import { describe, it, expect, afterEach } from 'vitest'
import type { ChainRecord } from '@/types/grading'
import './mf-grade-walk'
import type { MfGradeWalk } from './mf-grade-walk'

const CHAIN: ChainRecord = {
  schema_version: 'chain.v1',
  topic: 'anger', topic_synset_id: '1',
  vehicle: 'venom', vehicle_synset_id: '2',
  proposer: 't', round: 2,
  chain: [
    { phrase: 'anger', head: 'anger', synset_id: '1' },
    { phrase: 'venom', head: 'venom', synset_id: '2' },
  ],
  chain_signature: 's1', generated_at: '2026-06-06T00:00:00Z',
}

async function mount(props: Partial<MfGradeWalk> = {}): Promise<MfGradeWalk> {
  const el = document.createElement('mf-grade-walk') as MfGradeWalk
  Object.assign(el, { chain: CHAIN, index: 0, total: 3, dwellIndex: 0, dwellN: 2, topic: 'anger', skipGraded: true, ...props })
  document.body.appendChild(el)
  await el.updateComplete
  return el
}

describe('mf-grade-walk', () => {
  let el: MfGradeWalk

  afterEach(() => {
    if (el && el.parentNode) document.body.removeChild(el)
  })

  it('embeds the grade panel fed with the current chain', async () => {
    el = await mount()
    const panel = el.shadowRoot!.querySelector('mf-grade-panel') as any
    expect(panel).toBeTruthy()
    expect(panel.chain.chain_signature).toBe('s1')
  })

  it('threads senseInventories through to the panel (the fan is dead without it)', async () => {
    const inventories = { anger: [{ synset_id: '1', sensenum: 1, tagcount: 3, definition: 'strong displeasure', pos: 'n' }] }
    el = await mount({ senseInventories: inventories } as Partial<MfGradeWalk>)
    const panel = el.shadowRoot!.querySelector('mf-grade-panel') as any
    expect(panel.senseInventories).toEqual(inventories)
  })

  it('shows the 1-based position indicator', async () => {
    el = await mount({ index: 1, total: 5 })
    expect(el.shadowRoot!.querySelector('[data-testid="walk-pos"]')!.textContent).toContain('2 / 5')
  })

  it('shows the topic dwell sub-indicator', async () => {
    el = await mount({ topic: 'anger', dwellIndex: 1, dwellN: 4 })
    const dwell = el.shadowRoot!.querySelector('[data-testid="walk-dwell"]')!.textContent!
    expect(dwell).toContain('anger')
    expect(dwell).toContain('2/4')
  })

  it('guided mode hides the signal-only dwell and skip-graded controls', async () => {
    el = await mount({ guided: true })
    // dwell + skip are signal-walk affordances; a prefilled guided list has neither
    expect(el.shadowRoot!.querySelector('[data-testid="walk-dwell"]')).toBeNull()
    expect(el.shadowRoot!.querySelector('[data-testid="walk-skip"]')).toBeNull()
    // navigation + position + graded badge remain
    expect(el.shadowRoot!.querySelector('[data-testid="walk-prev"]')).not.toBeNull()
    expect(el.shadowRoot!.querySelector('[data-testid="walk-next"]')).not.toBeNull()
    expect(el.shadowRoot!.querySelector('[data-testid="walk-pos"]')).not.toBeNull()
  })

  it('signal mode (default) keeps the dwell and skip-graded controls', async () => {
    el = await mount()
    expect(el.shadowRoot!.querySelector('[data-testid="walk-dwell"]')).not.toBeNull()
    expect(el.shadowRoot!.querySelector('[data-testid="walk-skip"]')).not.toBeNull()
  })

  it('disables prev/next from explicit canPrev/canNext flags', async () => {
    const first = await mount({ canPrev: false, canNext: true })
    expect((first.shadowRoot!.querySelector('[data-testid="walk-prev"]') as HTMLButtonElement).disabled).toBe(true)
    expect((first.shadowRoot!.querySelector('[data-testid="walk-next"]') as HTMLButtonElement).disabled).toBe(false)
    document.body.removeChild(first)
    el = await mount({ canPrev: true, canNext: false })
    expect((el.shadowRoot!.querySelector('[data-testid="walk-next"]') as HTMLButtonElement).disabled).toBe(true)
    expect((el.shadowRoot!.querySelector('[data-testid="walk-prev"]') as HTMLButtonElement).disabled).toBe(false)
  })

  it('marks the current chain as already graded', async () => {
    el = await mount({ graded: true })
    expect(el.shadowRoot!.querySelector('[data-testid="walk-graded"]')).not.toBeNull()
  })

  it('shows the ungraded-remaining count', async () => {
    el = await mount({ ungradedLeft: 42 })
    expect(el.shadowRoot!.querySelector('[data-testid="walk-left"]')!.textContent).toContain('42 left')
  })

  it('emits walk-next / walk-prev on button click', async () => {
    el = await mount({ index: 1, total: 3 })
    let next = false, prev = false
    el.addEventListener('walk-next', () => { next = true })
    el.addEventListener('walk-prev', () => { prev = true })
    ;(el.shadowRoot!.querySelector('[data-testid="walk-next"]') as HTMLButtonElement).click()
    ;(el.shadowRoot!.querySelector('[data-testid="walk-prev"]') as HTMLButtonElement).click()
    expect(next).toBe(true)
    expect(prev).toBe(true)
  })

  it('emits walk-skip-toggle on the skip-graded control', async () => {
    el = await mount()
    let toggled = false
    el.addEventListener('walk-skip-toggle', () => { toggled = true })
    ;(el.shadowRoot!.querySelector('[data-testid="walk-skip"]') as HTMLButtonElement).click()
    expect(toggled).toBe(true)
  })

  it('navigates on ArrowRight / ArrowLeft', async () => {
    el = await mount({ index: 1, total: 3 })
    let next = false, prev = false
    el.addEventListener('walk-next', () => { next = true })
    el.addEventListener('walk-prev', () => { prev = true })
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }))
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }))
    expect(next).toBe(true)
    expect(prev).toBe(true)
  })

  it('does NOT navigate when an editable field is focused (typing in notes)', async () => {
    el = await mount({ index: 1, total: 3 })
    let fired = false
    el.addEventListener('walk-next', () => { fired = true })
    const ta = document.createElement('textarea')
    document.body.appendChild(ta)
    // dispatching on the textarea puts it in composedPath -> guard suppresses nav
    ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, composed: true }))
    document.body.removeChild(ta)
    expect(fired).toBe(false)
  })
})
