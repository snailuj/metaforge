import type { Scene } from './scene'
import { PROJECTED_STRIDE } from './project'

// Draws the test scene the way a real graph frame would: depth-sorted lines,
// dots with labels, and glowing pills. The three glow methods differ only in
// how the halo behind a pill is made, which is what the test compares.

export type GlowMode = 'none' | 'blur' | 'sprite'

export interface OffscreenTarget {
  canvas: CanvasImageSource
  ctx: CanvasRenderingContext2D
}

export interface DrawOptions {
  glow: GlowMode
  pixelRatio: number
  /** CSS pixels. */
  width: number
  height: number
  /** Builds the offscreen surface for a sprite, in device pixels. Injectable for tests. */
  makeCanvas?: (widthPx: number, heightPx: number) => OffscreenTarget
}

export const GLOW_BLUR_CSS_PX = 18
export const COLOURS = {
  background: '#1a1a2e',
  text: '#e8e0d4',
  edge: 'rgba(232,224,212,0.15)',
  gold: '#d4af37',
  cyan: '#5cc8e0',
}
export const LABEL_FONT = '14px Georgia, serif'

const PILL_HEIGHT = 26
const PILL_PAD_X = 12
const SPRITE_MARGIN = GLOW_BLUR_CSS_PX * 2
const DOT_GAP = 4

// Scale of a node at the origin in the runner's view; sizes are relative to it.
const REFERENCE_SCALE = 900 / 320

interface Workspace {
  isPill: Uint8Array
  pillColour: string[]
  edgeDepth: Float32Array
  edgeOrder: Uint32Array
  byDepthFarFirst: (a: number, b: number) => number
  sprites: Map<string, OffscreenTarget>
}

// Per-scene scratch space, so the hot loop allocates nothing after the first frame.
const workspaces = new WeakMap<Scene, Workspace>()

function workspaceFor(scene: Scene): Workspace {
  let w = workspaces.get(scene)
  if (w) return w
  const edgeCount = scene.edges.length / 2
  const isPill = new Uint8Array(scene.nodeCount)
  const pillColour: string[] = new Array(scene.nodeCount)
  scene.pills.forEach((node, k) => {
    isPill[node] = 1
    pillColour[node] = k === 0 ? COLOURS.gold : COLOURS.cyan
  })
  const edgeDepth = new Float32Array(edgeCount)
  const edgeOrder = new Uint32Array(edgeCount)
  w = {
    isPill,
    pillColour,
    edgeDepth,
    edgeOrder,
    byDepthFarFirst: (a, b) => edgeDepth[b] - edgeDepth[a],
    sprites: new Map(),
  }
  workspaces.set(scene, w)
  return w
}

// Text widths are fixed for a label at this font, so measure each label once.
const widthCache = new Map<string, number>()

function labelWidth(ctx: CanvasRenderingContext2D, label: string): number {
  let w = widthCache.get(label)
  if (w === undefined) {
    w = ctx.measureText(label).width
    widthCache.set(label, w)
  }
  return w
}

function clamp(v: number, lo: number, hi: number): number {
  return v < lo ? lo : v > hi ? hi : v
}

function rgba(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`
}

function roundedRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number): void {
  const r = h / 2
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

function defaultMakeCanvas(widthPx: number, heightPx: number): OffscreenTarget {
  const canvas = document.createElement('canvas')
  canvas.width = widthPx
  canvas.height = heightPx
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('2d canvas context unavailable for the glow sprite')
  return { canvas, ctx }
}

/** Paints a pill's halo once: a radial gradient stretched to the pill's shape. */
function buildSprite(
  w: Workspace, key: string, pillW: number, colour: string, pixelRatio: number,
  make: (widthPx: number, heightPx: number) => OffscreenTarget,
): OffscreenTarget {
  const cssW = pillW + 2 * SPRITE_MARGIN
  const cssH = PILL_HEIGHT + 2 * SPRITE_MARGIN
  const target = make(Math.ceil(cssW * pixelRatio), Math.ceil(cssH * pixelRatio))
  const g = target.ctx
  g.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
  g.translate(cssW / 2, cssH / 2)
  g.scale(cssW / 2, cssH / 2)
  const grad = g.createRadialGradient(0, 0, 0, 0, 0, 1)
  const solidUntil = Math.min(0.9, (PILL_HEIGHT / cssH) * 0.9)
  grad.addColorStop(0, rgba(colour, 0.7))
  grad.addColorStop(solidUntil, rgba(colour, 0.5))
  grad.addColorStop(1, rgba(colour, 0))
  g.fillStyle = grad
  g.fillRect(-1, -1, 2, 2)
  w.sprites.set(key, target)
  return target
}

export function drawScene(
  ctx: CanvasRenderingContext2D,
  scene: Scene,
  projected: Float32Array,
  opts: DrawOptions,
): void {
  const { glow, pixelRatio, width, height } = opts
  const make = opts.makeCanvas ?? defaultMakeCanvas
  const ws = workspaceFor(scene)
  const n = scene.nodeCount
  const edgeCount = scene.edges.length / 2

  ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
  ctx.globalAlpha = 1
  ctx.fillStyle = COLOURS.background
  ctx.fillRect(0, 0, width, height)

  // Lines, far to near.
  for (let e = 0; e < edgeCount; e++) {
    ws.edgeOrder[e] = e
    ws.edgeDepth[e] = (projected[scene.edges[2 * e] * PROJECTED_STRIDE + 3] + projected[scene.edges[2 * e + 1] * PROJECTED_STRIDE + 3]) * 0.5
  }
  ws.edgeOrder.sort(ws.byDepthFarFirst)
  ctx.strokeStyle = COLOURS.edge
  for (let k = 0; k < edgeCount; k++) {
    const e = ws.edgeOrder[k]
    const a = scene.edges[2 * e] * PROJECTED_STRIDE
    const b = scene.edges[2 * e + 1] * PROJECTED_STRIDE
    ctx.lineWidth = clamp(((projected[a + 2] + projected[b + 2]) * 0.5 / REFERENCE_SCALE) * 0.8, 0.4, 1.4)
    ctx.beginPath()
    ctx.moveTo(projected[a], projected[a + 1])
    ctx.lineTo(projected[b], projected[b + 1])
    ctx.stroke()
  }

  // Dots with a label beside each.
  ctx.font = LABEL_FONT
  ctx.textBaseline = 'middle'
  ctx.textAlign = 'left'
  ctx.fillStyle = COLOURS.text
  for (let i = 0; i < n; i++) {
    if (ws.isPill[i]) continue
    const o = i * PROJECTED_STRIDE
    const rel = projected[o + 2] / REFERENCE_SCALE
    const r = clamp(2.4 * rel, 1.4, 4)
    ctx.globalAlpha = clamp(0.4 + 0.6 * (rel - 0.6), 0.35, 1)
    ctx.beginPath()
    ctx.arc(projected[o], projected[o + 1], r, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillText(scene.labels[i], projected[o] + r + DOT_GAP, projected[o + 1])
  }
  ctx.globalAlpha = 1

  // Pills on top, each with its own glow.
  ctx.textAlign = 'center'
  for (let k = 0; k < scene.pills.length; k++) {
    const i = scene.pills[k]
    const o = i * PROJECTED_STRIDE
    const label = scene.labels[i]
    const colour = ws.pillColour[i]
    const pillW = Math.ceil(labelWidth(ctx, label)) + 2 * PILL_PAD_X
    const x = projected[o]
    const y = projected[o + 1]

    if (glow === 'sprite') {
      const key = `${pillW}|${colour}|${pixelRatio}`
      const sprite = ws.sprites.get(key) ?? buildSprite(ws, key, pillW, colour, pixelRatio, make)
      ctx.drawImage(
        sprite.canvas, x - pillW / 2 - SPRITE_MARGIN, y - PILL_HEIGHT / 2 - SPRITE_MARGIN,
        pillW + 2 * SPRITE_MARGIN, PILL_HEIGHT + 2 * SPRITE_MARGIN,
      )
    } else if (glow === 'blur') {
      // shadowBlur ignores the canvas transform, so scale it to device pixels.
      ctx.shadowBlur = GLOW_BLUR_CSS_PX * pixelRatio
      ctx.shadowColor = colour
    }
    ctx.fillStyle = colour
    roundedRect(ctx, x - pillW / 2, y - PILL_HEIGHT / 2, pillW, PILL_HEIGHT)
    ctx.fill()
    if (glow === 'blur') ctx.shadowBlur = 0
    ctx.fillStyle = COLOURS.background
    ctx.fillText(label, x, y)
  }
}
