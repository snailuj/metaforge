import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MfUndoToast } from './mf-undo-toast'

describe('MfUndoToast', () => {
  let el: MfUndoToast

  const plaque = () => el.shadowRoot!.querySelector('.plaque') as HTMLElement
  const undo = () => el.shadowRoot!.querySelector('.undo') as HTMLButtonElement | null

  beforeEach(async () => {
    vi.useFakeTimers()
    el = new MfUndoToast()
    el.actionLabel = 'Undo'
    document.body.appendChild(el)
    await el.updateComplete
  })

  afterEach(() => {
    document.body.removeChild(el)
    vi.useRealTimers()
  })

  it('starts hidden, with its message in a polite live region', () => {
    expect(plaque().classList.contains('visible')).toBe(false)
    expect(el.shadowRoot!.querySelector('[role="status"]')?.getAttribute('aria-live')).toBe('polite')
  })

  it('shows the message with an Undo button', async () => {
    el.show('Re-centred on blaze')
    await el.updateComplete

    expect(plaque().classList.contains('visible')).toBe(true)
    expect(plaque().textContent).toContain('Re-centred on blaze')
    expect(undo()?.textContent).toContain('Undo')
  })

  it('keeps the hidden Undo button out of the tab order', async () => {
    expect(undo()?.tabIndex).toBe(-1)
    el.show('Re-centred on blaze')
    await el.updateComplete
    expect(undo()?.tabIndex).toBe(0)
  })

  it('fires mf-undo and hides when Undo is pressed', async () => {
    const spy = vi.fn()
    document.body.addEventListener('mf-undo', spy)
    el.show('Re-centred on blaze')
    await el.updateComplete

    undo()!.click()
    await el.updateComplete

    expect(spy).toHaveBeenCalledOnce()
    expect(plaque().classList.contains('visible')).toBe(false)
    document.body.removeEventListener('mf-undo', spy)
  })

  it('hides by itself after its duration', async () => {
    el.show('Re-centred on blaze', 5000)
    vi.advanceTimersByTime(4900)
    await el.updateComplete
    expect(plaque().classList.contains('visible')).toBe(true)

    vi.advanceTimersByTime(200)
    await el.updateComplete
    expect(plaque().classList.contains('visible')).toBe(false)
  })

  it('holds while the pointer or focus is on it, then runs out the time left', async () => {
    el.show('Re-centred on blaze', 5000)
    vi.advanceTimersByTime(3000)
    plaque().dispatchEvent(new Event('pointerenter'))
    vi.advanceTimersByTime(10_000)
    await el.updateComplete
    expect(plaque().classList.contains('visible')).toBe(true)
    expect(plaque().classList.contains('held')).toBe(true)

    plaque().dispatchEvent(new Event('pointerleave'))
    vi.advanceTimersByTime(1900)
    await el.updateComplete
    expect(plaque().classList.contains('visible')).toBe(true)
    vi.advanceTimersByTime(200)
    await el.updateComplete
    expect(plaque().classList.contains('visible')).toBe(false)
  })

  it('a second show replaces the first and restarts the time', async () => {
    el.show('first', 5000)
    vi.advanceTimersByTime(4000)
    el.show('second', 5000)
    vi.advanceTimersByTime(4000)
    await el.updateComplete
    expect(plaque().classList.contains('visible')).toBe(true)
    expect(plaque().textContent).toContain('second')
  })

  it('hide() dismisses it at once', async () => {
    el.show('Re-centred on blaze')
    el.hide()
    await el.updateComplete
    expect(plaque().classList.contains('visible')).toBe(false)
  })
})
