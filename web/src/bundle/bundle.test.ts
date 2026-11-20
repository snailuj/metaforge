// @vitest-environment node
// Guards what ships in the production bundle. Runs a real Vite build in memory,
// so it is slower than the unit tests (a few seconds).
import { describe, it, expect, beforeAll } from 'vitest'
import { build, type Rollup } from 'vite'
import config from '../../vite.config'
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

  it('keeps three.js and the graph library out of the entry chunk, in a lazily loaded one', () => {
    const heavy = (m: string) => /node_modules\/(three|3d-force-graph)\//.test(m)
    const entry = chunks.filter(c => c.isEntry)
    expect(entry.length).toBe(1)
    expect(modulesOf(entry[0]).filter(heavy)).toEqual([])
    const lazy = chunks.filter(c => !c.isEntry && modulesOf(c).some(heavy))
    expect(lazy.length).toBeGreaterThan(0)
    expect(entry[0].dynamicImports).toEqual(expect.arrayContaining([lazy[0].fileName]))
  })

  // Vite counts kB as 1000 bytes. Only the graph chunk (three.js, which cannot
  // be split further) may use the raised limit; everything else stays under
  // Vite's default 500 kB.
  it('keeps every chunk under the warning limit, and all but the graph chunk under 500 kB', () => {
    const limit = config.build?.chunkSizeWarningLimit
    expect(limit).toBeDefined()
    for (const c of chunks) {
      const kb = Buffer.byteLength(c.code) / 1000
      const cap = c.name === 'mf-force-graph' ? limit! : 500
      expect(kb, c.fileName).toBeLessThanOrEqual(cap)
    }
  })
})
