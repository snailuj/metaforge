import { describe, it, expect } from 'vitest'
import { buildScene } from './scene'
import { project, PROJECTED_STRIDE, type View } from './project'
import { stubCtx, type Stub } from './stub-ctx'
import { drawScene, GLOW_BLUR_CSS_PX, type DrawOptions } from './draw'

// Rule: each glow method does the work it names, and no other glow work.
// 'none' never blurs, 'blur' blurs every pill every frame, and 'sprite'
// stamps a cached image once per pill and builds each image once.

const VIEW: View = { cx: 200, cy: 300, distance: 320, focal: 900 }

function setup(glow: DrawOptions['glow'], pixelRatio = 3) {
  const scene = buildScene(1, 100, 150)
  const projected = new Float32Array(scene.nodeCount * PROJECTED_STRIDE)
  project(scene.positions, scene.nodeCount, 0.2, VIEW, projected)
  const stub = stubCtx()
  const sprites: Stub[] = []
  const opts: DrawOptions = {
    glow,
    pixelRatio,
    width: 400,
    height: 600,
    makeCanvas: () => {
      const s = stubCtx()
      sprites.push(s)
      return { canvas: {} as unknown as CanvasImageSource, ctx: s.ctx }
    },
  }
  return { scene, projected, stub, opts, sprites }
}

describe('drawScene glow methods', () => {
  it("'none' never sets a blur above zero and stamps no sprites", () => {
    const { scene, projected, stub, opts } = setup('none')
    drawScene(stub.ctx, scene, projected, opts)
    expect(stub.shadowBlurSets.every(v => v <= 0)).toBe(true)
    expect(stub.calls.drawImage ?? 0).toBe(0)
  })

  it("'blur' sets the scaled blur once per pill and clears it afterwards", () => {
    const { scene, projected, stub, opts } = setup('blur', 3)
    drawScene(stub.ctx, scene, projected, opts)
    const positive = stub.shadowBlurSets.filter(v => v > 0)
    expect(positive.length).toBe(12)
    expect(positive.every(v => v === GLOW_BLUR_CSS_PX * 3)).toBe(true)
    expect(stub.shadowBlurSets[stub.shadowBlurSets.length - 1]).toBe(0)
    expect(stub.calls.drawImage ?? 0).toBe(0)
  })

  it("'sprite' draws one image per pill, builds each once across two frames, and never blurs", () => {
    const { scene, projected, stub, opts, sprites } = setup('sprite')
    drawScene(stub.ctx, scene, projected, opts)
    expect(stub.calls.drawImage).toBe(12)
    const built = sprites.length
    expect(built).toBeGreaterThan(0)
    expect(built).toBeLessThanOrEqual(12)
    drawScene(stub.ctx, scene, projected, opts)
    expect(stub.calls.drawImage).toBe(24)
    expect(sprites.length).toBe(built)
    expect(stub.shadowBlurSets.every(v => v <= 0)).toBe(true)
  })

  it('draws a label for every node and one line per edge', () => {
    const { scene, projected, stub, opts } = setup('none')
    drawScene(stub.ctx, scene, projected, opts)
    expect(stub.calls.fillText).toBe(100)
    expect(stub.calls.stroke).toBeGreaterThanOrEqual(150)
  })
})
