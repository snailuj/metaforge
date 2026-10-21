import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { FOREST_ERROR_KINDS } from '@/api/client'

// Rule: every forest string the UI can ask for is served in production.
// Production serves /strings/v1/ui.ftl from the repo-root strings/v1/ui.en-GB.ftl
// (api/internal/handler/handler.go, HandleStrings); web/public is the Vite copy.
// Scoped to forest ids: the two files drifted on other ids before the forest.
const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8')
const DEV = read('../../public/strings/v1/ui.ftl')
const SERVED = read('../../../strings/v1/ui.en-GB.ftl')

/** id -> its source block (the id line plus its indented continuation lines). */
function messages(ftl: string): Map<string, string> {
  const out = new Map<string, string>()
  let id: string | null = null
  for (const line of ftl.split('\n')) {
    const start = line.match(/^([a-zA-Z][\w-]*)\s*=/)
    if (start) { id = start[1]; out.set(id, line.trimEnd()); continue }
    if (id && /^\s+\S/.test(line)) out.set(id, `${out.get(id)}\n${line.trimEnd()}`)
    else id = null
  }
  return out
}

const dev = messages(DEV)
const served = messages(SERVED)
const forestIds = [...dev.keys()].filter(id => id.startsWith('forest-'))

describe('forest strings', () => {
  it('finds the forest section in the dev copy', () => {
    expect(forestIds.length).toBeGreaterThan(30)
  })

  it('serves every forest id from the dev copy, with the same text', () => {
    const missing = forestIds.filter(id => !served.has(id))
    expect(missing).toEqual([])
    for (const id of forestIds) expect(served.get(id), id).toBe(dev.get(id))
  })

  it('has the message for every failure kind in both files', () => {
    for (const kind of FOREST_ERROR_KINDS) {
      const ids = kind === 'busy' ? ['forest-error-busy', 'forest-error-busy-soon'] : [`forest-error-${kind}`]
      for (const id of ids) {
        expect(dev.has(id), `dev ${id}`).toBe(true)
        expect(served.has(id), `served ${id}`).toBe(true)
      }
    }
  })
})
