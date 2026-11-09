// @vitest-environment node
// Guards what ships in the production bundle. Runs a real Vite build in memory,
// so it is slower than the unit tests (a few seconds).
import { describe, it, expect, beforeAll } from 'vitest'
import { build, type Rollup } from 'vite'
import { resolve } from 'path'

type Chunk = Rollup.OutputChunk

let chunks: Chunk[] = []

beforeAll(async () => {
  const out = await build({
    root: resolve(__dirname, '../..'),
    logLevel: 'silent',
    build: { write: false },
  }) as Rollup.RollupOutput | Rollup.RollupOutput[]
  const outputs = Array.isArray(out) ? out : [out]
  chunks = outputs.flatMap(o => o.output).filter((f): f is Chunk => f.type === 'chunk')
}, 120_000)

const modulesOf = (c: Chunk) => Object.keys(c.modules)

describe('production bundle', () => {
  it('produced at least one chunk', () => {
    expect(chunks.length).toBeGreaterThan(0)
    expect(chunks.some(c => modulesOf(c).some(m => m.includes('node_modules/three/')))).toBe(true)
  })

  it('ships no three.js WebGPU build (the app only ever renders with WebGL)', () => {
    const webgpu = chunks.flatMap(modulesOf).filter(m => m.includes('three.webgpu'))
    expect(webgpu).toEqual([])
  })
})
