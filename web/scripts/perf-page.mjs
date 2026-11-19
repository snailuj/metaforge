// Assembles the glow speed test as one self-contained fragment. A host wraps
// it in its own document skeleton, so the fragment must not carry one.

import { readFileSync } from 'node:fs'

const SKELETON = /<!doctype|<html|<head|<body/i

export function assemblePage({ css, markup, js }) {
  if (/<script/i.test(css) || /<script/i.test(markup)) {
    throw new Error('the page markup and style must not contain a script tag; the one script is added here')
  }
  // "</script" inside code would end the inline script early.
  const safeJs = js.replace(/<\/script/gi, '<\\/script')
  const out = [
    '<title>Glow Speed Test</title>',
    '<meta name="claude:viewport-fit-sides" content="cover">',
    `<style>\n${css.trim()}\n</style>`,
    markup.trim(),
    `<script>\n${safeJs.trim()}\n</script>`,
    '',
  ].join('\n')
  if (SKELETON.test(out)) {
    throw new Error('the page contains a document skeleton tag (doctype, html, head or body)')
  }
  return out
}

const WASM_MAGIC = Buffer.from([0x00, 0x61, 0x73, 0x6d])

/** The compiled physics module as base64, for embedding in the page. */
export function readWasmBase64(path) {
  let bytes
  try {
    bytes = readFileSync(path)
  } catch (err) {
    throw new Error(`the Rust physics module is not built (${path}); run: npm run build:wasm`, { cause: err })
  }
  if (!bytes.subarray(0, 4).equals(WASM_MAGIC)) {
    throw new Error(`${path} is not a WebAssembly module; rebuild it with: npm run build:wasm`)
  }
  return bytes.toString('base64')
}
