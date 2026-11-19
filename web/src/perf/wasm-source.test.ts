import { describe, it, expect } from 'vitest'
import { loadWasmBytes } from './wasm-source'

// Rule: the page gets the engine's bytes from the copy embedded in the single
// file when there is one, and otherwise from the dev server; a missing module
// is reported with the command that builds it, never passed on as bad bytes.

const MAGIC = [0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00]
const b64 = btoa(String.fromCharCode(...MAGIC))

const reply = (body: BodyInit, init?: ResponseInit) => (async () => new Response(body, init)) as unknown as typeof fetch

describe('loadWasmBytes', () => {
  it('decodes the embedded copy without fetching anything', async () => {
    const never = (async () => { throw new Error('network used') }) as unknown as typeof fetch
    expect(Array.from(await loadWasmBytes(b64, never))).toEqual(MAGIC)
  })

  it('falls back to the dev server file', async () => {
    expect(Array.from(await loadWasmBytes(undefined, reply(new Uint8Array(MAGIC))))).toEqual(MAGIC)
  })

  it('names the build command when the dev server has no such file', async () => {
    await expect(loadWasmBytes(undefined, reply('missing', { status: 404 }))).rejects.toThrow(/npm run build:wasm/)
  })

  it('names the build command when the server answers with a page instead of a module', async () => {
    await expect(loadWasmBytes(undefined, reply('<!doctype html>'))).rejects.toThrow(/npm run build:wasm/)
  })
})
