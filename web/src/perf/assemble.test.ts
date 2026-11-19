import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
// @ts-expect-error plain ES module without declarations
import { assemblePage } from '../../scripts/perf-page.mjs'

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
    const css = readFileSync(new URL('./page.css', import.meta.url), 'utf8')
    const markup = readFileSync(new URL('./page.html', import.meta.url), 'utf8')
    expect(() => assemblePage({ css, markup, js: 'void 0' })).not.toThrow()
  })
})
