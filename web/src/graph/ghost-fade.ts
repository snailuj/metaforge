// Ghosts (glimpsed words not yet opened) fade in as the camera nears them:
// from the default view they are as faint as their edges, so a ghost never
// reads as an unconnected node; close up they are plainly legible.

/** Fade levels move in these steps. Colour accessors key three.js materials by
 *  colour string, so stepping keeps the material count small and the renderer
 *  re-colours only when a ghost crosses a step. */
export const GHOST_FADE_STEP = 0.05

// Camera distance, as a fraction of the default view's, where the fade starts
// (faint) and where it completes (full).
const FAR = 1
const NEAR = 0.3

/** How far a ghost has faded in, 0 (faint) to 1 (full), for its camera distance. */
export function ghostFade(distance: number, refDistance: number): number {
  if (!(refDistance > 0)) return 0
  const t = (FAR - distance / refDistance) / (FAR - NEAR)
  const clamped = Math.min(1, Math.max(0, t))
  const eased = clamped * clamped * (3 - 2 * clamped) // smoothstep
  return Math.round(eased / GHOST_FADE_STEP) * GHOST_FADE_STEP
}

const lerp = (a: number, b: number, t: number) => Math.round((a + (b - a) * t) * 1000) / 1000

/** Node, label and edge opacity for one fade level. The edge tops out at a
 *  full first-order edge, so a close ghost is never brighter than a solid link. */
export function ghostAlphas(fade: number): { node: number; label: number; edge: number } {
  return {
    node: lerp(0.06, 0.7, fade),
    label: lerp(0.06, 0.8, fade),
    edge: lerp(0.04, 0.15, fade),
  }
}
