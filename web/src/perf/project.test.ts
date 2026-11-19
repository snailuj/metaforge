import { describe, it, expect } from 'vitest'
import { buildScene } from './scene'
import { project, rotateY, PROJECTED_STRIDE, type View } from './project'

const VIEW: View = { cx: 200, cy: 300, distance: 320, focal: 900 }

// Rule: turning the camera by an angle and then by the negative angle puts
// every word back at its original screen point.
describe('project', () => {
  const scene = buildScene(1, 100, 150)
  const n = scene.nodeCount

  it('returns every point to its start after a turn and the opposite turn', () => {
    const angle = 0.9
    const base = new Float32Array(n * PROJECTED_STRIDE)
    project(scene.positions, n, 0, VIEW, base)

    const turned = new Float32Array(n * 3)
    const back = new Float32Array(n * 3)
    rotateY(scene.positions, n, angle, turned)
    rotateY(turned, n, -angle, back)
    const out = new Float32Array(n * PROJECTED_STRIDE)
    project(back, n, 0, VIEW, out)

    for (let i = 0; i < n; i++) {
      expect(Math.abs(out[i * PROJECTED_STRIDE] - base[i * PROJECTED_STRIDE])).toBeLessThan(1e-4)
      expect(Math.abs(out[i * PROJECTED_STRIDE + 1] - base[i * PROJECTED_STRIDE + 1])).toBeLessThan(1e-4)
    }
  })

  it('projecting at an angle equals rotating first and projecting at zero', () => {
    const rotated = new Float32Array(n * 3)
    rotateY(scene.positions, n, 0.4, rotated)
    const a = new Float32Array(n * PROJECTED_STRIDE)
    const b = new Float32Array(n * PROJECTED_STRIDE)
    project(scene.positions, n, 0.4, VIEW, a)
    project(rotated, n, 0, VIEW, b)
    for (let i = 0; i < a.length; i++) expect(Math.abs(a[i] - b[i])).toBeLessThan(1e-3)
  })

  it('gives a nearer point a larger scale than a farther one', () => {
    // Camera looks along +z from z = -distance, so a smaller z is nearer.
    const pts = new Float32Array([0, 0, -50, 0, 0, 50])
    const out = new Float32Array(2 * PROJECTED_STRIDE)
    project(pts, 2, 0, VIEW, out)
    const nearScale = out[2]
    const farScale = out[PROJECTED_STRIDE + 2]
    expect(nearScale).toBeGreaterThan(farScale)
    expect(out[3]).toBeLessThan(out[PROJECTED_STRIDE + 3])
  })

  it('maps the origin to the view centre', () => {
    const out = new Float32Array(PROJECTED_STRIDE)
    project(new Float32Array([0, 0, 0]), 1, 1.3, VIEW, out)
    expect(out[0]).toBeCloseTo(VIEW.cx, 4)
    expect(out[1]).toBeCloseTo(VIEW.cy, 4)
  })

  it('draws up as up on screen', () => {
    const out = new Float32Array(PROJECTED_STRIDE)
    project(new Float32Array([0, 10, 0]), 1, 0, VIEW, out)
    expect(out[1]).toBeLessThan(VIEW.cy)
  })
})
