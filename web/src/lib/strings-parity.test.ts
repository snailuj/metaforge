// @vitest-environment node
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { FluentResource } from '@fluent/bundle'

// The API serves strings/v1/ui.en-GB.ftl for GET /strings/v1/ui.ftl (HandleStrings).
const SERVED = new URL('../../../strings/v1/ui.en-GB.ftl', import.meta.url)
const DEV_COPY = new URL('../../public/strings/v1/ui.ftl', import.meta.url)
const SRC = new URL('../', import.meta.url)

// Template-literal ids can't be read from source, so each prefix declares its values.
// register/connotation: CHECK constraints in data-pipeline/scripts/enrich_pipeline.py,
// minus 'neutral', which mf-results-panel never renders.
const DYNAMIC_IDS: Record<string, string[]> = {
  'rarity-': ['common', 'unusual', 'rare'],
  'register-': ['formal', 'informal', 'slang'],
  'connotation-': ['positive', 'negative'],
}

function messageIds(file: URL): string[] {
  return new FluentResource(readFileSync(file, 'utf-8')).body.map((entry) => entry.id)
}

/** Every getString id referenced by non-test source, with template prefixes expanded. */
function idsUsedByUi(): string[] {
  const files = readdirSync(SRC, { recursive: true, encoding: 'utf-8' })
    .filter((f) => f.endsWith('.ts') && !f.endsWith('.test.ts'))
  const ids: string[] = []
  for (const file of files) {
    const source = readFileSync(new URL(file, SRC), 'utf-8')
    for (const [, arg] of source.matchAll(/(?<!function )\bgetString\(\s*([^,)]*)/g)) {
      const literal = arg.match(/^(['"`])([^'"`$]+)\1$/)
      const prefix = arg.match(/^`([^`$]*)\$\{/)
      if (literal) ids.push(literal[2])
      else if (prefix && DYNAMIC_IDS[prefix[1]]) ids.push(...DYNAMIC_IDS[prefix[1]].map((v) => prefix[1] + v))
      else ids.push(`<unauditable in ${file}: getString(${arg})>`)
    }
  }
  return ids
}

describe('UI strings parity', () => {
  it('served file defines every id in the dev copy', () => {
    const served = new Set(messageIds(SERVED))
    const missing = messageIds(DEV_COPY).filter((id) => !served.has(id))
    expect(missing).toEqual([])
  })

  it('served file defines every id the UI uses', () => {
    const served = new Set(messageIds(SERVED))
    const used = idsUsedByUi()
    expect(used.length).toBeGreaterThan(0)
    expect(used.filter((id) => !served.has(id))).toEqual([])
  })
})
