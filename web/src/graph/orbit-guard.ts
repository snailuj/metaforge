/** The OrbitControls internals the guard leans on (three r182; still the same
 *  in r186). */
interface OrbitInternals {
  domElement: HTMLElement | null
  _pointers: number[]
  _onPointerUp: (e: PointerEvent) => void
  __pointerUpGuarded?: true
}

function hasInternals(c: unknown): c is OrbitInternals {
  const o = c as Partial<OrbitInternals> | null
  return !!o && Array.isArray(o._pointers) && typeof o._onPointerUp === 'function' && !!o.domElement
}

/**
 * 3d-force-graph ends every node drag, a plain click included, by dispatching a
 * synthetic touch `pointerup` that names no pointer. OrbitControls, still
 * tracking the real mouse pointer, reads that as one of two touches lifting and
 * looks up a touch position it never stored: a TypeError on every node click.
 *
 * Drop pointer-up (and pointer-cancel, which shares the handler) for pointers
 * the controls do not track. That is all the synthetic event ever is, and the
 * real pointerup that follows still ends the gesture.
 *
 * Call before the first press: the handler is swapped where OrbitControls reads
 * it, and only its pointercancel listener is already registered. Returns false,
 * changing nothing, if the controls lack the expected internals.
 */
export function guardOrbitPointerUp(controls: unknown): boolean {
  if (!hasInternals(controls)) {
    console.warn('[orbit-guard] controls lack the expected internals; pointerup left unguarded')
    return false
  }
  if (controls.__pointerUpGuarded) return true
  const el = controls.domElement!
  const original = controls._onPointerUp
  const guarded = (e: PointerEvent) => {
    if (!controls._pointers.includes(e.pointerId)) {
      console.debug('[orbit-guard] dropped pointerup for an untracked pointer', { pointerId: e.pointerId, type: e.type })
      return
    }
    original(e)
  }
  el.removeEventListener('pointercancel', original)
  controls._onPointerUp = guarded
  el.addEventListener('pointercancel', guarded)
  controls.__pointerUpGuarded = true
  return true
}
