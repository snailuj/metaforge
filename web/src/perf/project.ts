// Perspective projection for the glow speed test. The camera sits on the
// z axis and the scene turns about the vertical axis, which is all a turning
// graph needs and keeps the hot loop to a few multiplications per node.

export const PROJECTED_STRIDE = 4 // screen x, screen y, scale, depth

export interface View {
  /** Screen position of the origin. */
  cx: number
  cy: number
  /** Distance from the camera to the origin. */
  distance: number
  /** Focal length in pixels: scale is focal / depth. */
  focal: number
}

/** Smallest depth used for the divide, so a point at the camera cannot blow up. */
const MIN_DEPTH = 1

/** Turns flat x, y, z positions about the vertical axis into `out`. */
export function rotateY(positions: Float32Array, count: number, angle: number, out: Float32Array): void {
  const cos = Math.cos(angle)
  const sin = Math.sin(angle)
  for (let i = 0; i < count; i++) {
    const x = positions[3 * i]
    const z = positions[3 * i + 2]
    out[3 * i] = x * cos + z * sin
    out[3 * i + 1] = positions[3 * i + 1]
    out[3 * i + 2] = -x * sin + z * cos
  }
}

/** Writes screen x, y, scale and depth per node into `out` without allocating. */
export function project(positions: Float32Array, count: number, angle: number, view: View, out: Float32Array): void {
  const cos = Math.cos(angle)
  const sin = Math.sin(angle)
  for (let i = 0; i < count; i++) {
    const x = positions[3 * i]
    const y = positions[3 * i + 1]
    const z = positions[3 * i + 2]
    const rx = x * cos + z * sin
    const rz = -x * sin + z * cos
    const depth = Math.max(view.distance + rz, MIN_DEPTH)
    const scale = view.focal / depth
    const o = i * PROJECTED_STRIDE
    out[o] = view.cx + rx * scale
    out[o + 1] = view.cy - y * scale
    out[o + 2] = scale
    out[o + 3] = depth
  }
}
