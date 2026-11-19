import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
// @ts-expect-error plain ES module without declarations
import { assemblePage, readWasmBase64 } from '../../scripts/perf-page.mjs'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

// Rule: the single-file page can be wrapped by a host that supplies the
// document skeleton, so it must carry no skeleton tags of its own.

const parts = { css: 'body{margin:0}', markup: '<div id="perf-root"><p>hi</p></div>', js: 'console.log(1)' }

describe('assemblePage', () => {
  it('starts with the title, then the viewport meta, then the style, markup and one script', () => {
    const out: string = assemblePage(parts)
    expect(out.startsWith('<title>Glow Speed Test</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n<style>')).toBe(true)
    expect(out.indexOf('<style>')).toBeLessThan(out.indexOf('<div id="perf-root">'))
    expect(out.indexOf('<div id="perf-root">')).toBeLessThan(out.indexOf('<script>'))
    expect(out.match(/<script/g)).toHaveLength(1)
    expect(out.trimEnd().endsWith('</script>')).toBe(true)
  })

  it('carries no document skeleton tags', () => {
    expect(assemblePage(parts)).not.toMatch(/<!doctype|<html|<head|<body/i)
  })

  it('refuses parts that would add a skeleton tag', () => {
    expect(() => assemblePage({ ...parts, markup: '<body>x</body>' })).toThrow(/skeleton/)
    expect(() => assemblePage({ ...parts, css: '/* <html> */' })).toThrow(/skeleton/)
  })

  it('keeps a script closing tag inside the code from ending the script early', () => {
    const out: string = assemblePage({ ...parts, js: 'var s="</script>"' })
    expect(out.match(/<\/script>/g)).toHaveLength(1)
  })

  it('refuses code that would add a script of its own', () => {
    expect(() => assemblePage({ ...parts, markup: '<script>x</script>' })).toThrow(/script/)
  })
})

describe('the real page parts', () => {
  it('assemble without a skeleton tag, so no element such as <header> sneaks in', () => {
    const css = readFileSync('src/perf/page.css', 'utf8')
    const markup = readFileSync('src/perf/page.html', 'utf8')
    expect(() => assemblePage({ css, markup, js: 'void 0' })).not.toThrow()
  })
})

describe('readWasmBase64', () => {
  const dir = mkdtempSync(join(tmpdir(), 'perf-wasm-'))

  // Rule: the single-file build never ships without the engine, and a missing
  // or wrong file says how to fix it instead of building a page that fails on a phone.
  it('names the command that builds the module when the file is missing', () => {
    expect(() => readWasmBase64(join(dir, 'absent.wasm'))).toThrow(/npm run build:wasm/)
  })

  it('refuses a file that is not a WebAssembly module', () => {
    const bad = join(dir, 'bad.wasm')
    writeFileSync(bad, 'not wasm')
    expect(() => readWasmBase64(bad)).toThrow(/WebAssembly/)
  })

  it('returns the module as base64 that decodes to the same bytes, with nothing that could end a script', () => {
    const good = join(dir, 'good.wasm')
    const bytes = Buffer.from([0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00, 0xfb, 0xff])
    writeFileSync(good, bytes)
    const b64: string = readWasmBase64(good)
    expect(Buffer.from(b64, 'base64').equals(bytes)).toBe(true)
    expect(b64).toMatch(/^[A-Za-z0-9+/=]+$/)
  })
})
