// Builds web/dist-perf/glow.html: the glow speed test as one file with its
// script and style inline and no network requests. Run with `npm run build:perf`.
import { build } from 'esbuild'
import { readFileSync, mkdirSync, writeFileSync, statSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { assemblePage } from './perf-page.mjs'

const web = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const src = resolve(web, 'src/perf')
const read = name => readFileSync(resolve(src, name), 'utf8')

// main.ts imports the markup with `?raw` for the dev page. In this build the
// markup is written into the page itself, so the import resolves to nothing.
const emptyRawImports = {
  name: 'empty-raw-imports',
  setup(b) {
    b.onResolve({ filter: /\?raw$/ }, args => ({ path: args.path, namespace: 'empty-raw' }))
    b.onLoad({ filter: /.*/, namespace: 'empty-raw' }, () => ({ contents: 'export default ""', loader: 'js' }))
  },
}

const bundle = await build({
  entryPoints: [resolve(src, 'main.ts')],
  bundle: true,
  write: false,
  format: 'iife',
  target: 'es2022',
  minify: true,
  legalComments: 'none',
  plugins: [emptyRawImports],
  logLevel: 'warning',
})

const html = assemblePage({
  css: read('page.css'),
  markup: `<div id="perf-root">\n${read('page.html').trim()}\n</div>`,
  js: bundle.outputFiles[0].text,
})

const out = resolve(web, 'dist-perf/glow.html')
mkdirSync(dirname(out), { recursive: true })
writeFileSync(out, html)
console.log(`wrote ${out} (${statSync(out).size} bytes)`)
