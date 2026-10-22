import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { PerspectiveCamera } from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { guardOrbitPointerUp } from './orbit-guard'

/** What 3d-force-graph dispatches on the document at every drag end, a plain
 *  node click included: a touch pointerup that names no pointer. */
const syntheticDragEndUp = () => new PointerEvent('pointerup', { pointerType: 'touch' })

describe('guardOrbitPointerUp', () => {
  let el: HTMLDivElement
  let controls: OrbitControls

  beforeEach(() => {
    el = document.createElement('div')
    document.body.appendChild(el)
    // happy-dom has no pointer capture; OrbitControls calls it on every press.
    Object.assign(el, { setPointerCapture: vi.fn(), releasePointerCapture: vi.fn() })
    controls = new OrbitControls(new PerspectiveCamera(), el)
  })

  afterEach(() => {
    controls.dispose()
    el.remove()
  })

  /** A mouse press OrbitControls tracks, as when a node click starts. */
  function pressMouse(): void {
    el.dispatchEvent(new PointerEvent('pointerdown', { pointerId: 1, pointerType: 'mouse', button: 0, clientX: 10, clientY: 10 }))
  }

  const onPointerUp = () => (controls as unknown as { _onPointerUp: (e: PointerEvent) => void })._onPointerUp

  it('reproduces the unguarded crash: the synthetic pointerup reads a touch position never stored', () => {
    pressMouse()
    expect(() => onPointerUp()(syntheticDragEndUp())).toThrow(TypeError)
  })

  it('drops a pointerup for a pointer the controls do not track', () => {
    expect(guardOrbitPointerUp(controls)).toBe(true)
    pressMouse()
    expect(() => onPointerUp()(syntheticDragEndUp())).not.toThrow()
  })

  it('still ends the gesture on the real pointerup', () => {
    guardOrbitPointerUp(controls)
    const end = vi.fn()
    controls.addEventListener('end', end)
    pressMouse()
    onPointerUp()(syntheticDragEndUp())
    document.dispatchEvent(new PointerEvent('pointerup', { pointerId: 1, pointerType: 'mouse' }))
    expect(end).toHaveBeenCalledOnce()
  })

  it('guards pointercancel too, which shares the handler', () => {
    guardOrbitPointerUp(controls)
    pressMouse()
    expect(() => el.dispatchEvent(new PointerEvent('pointercancel', { pointerId: 7, pointerType: 'touch' }))).not.toThrow()
  })

  it('is idempotent', () => {
    guardOrbitPointerUp(controls)
    const guarded = onPointerUp()
    expect(guardOrbitPointerUp(controls)).toBe(true)
    expect(onPointerUp()).toBe(guarded)
  })

  it('leaves controls without the expected internals alone', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(guardOrbitPointerUp({})).toBe(false)
    expect(warn).toHaveBeenCalledOnce()
    warn.mockRestore()
  })
})
