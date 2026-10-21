// @vitest-environment node
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { FluentResource } from '@fluent/bundle'

// The API serves strings/v1/ui.en-GB.ftl for GET /strings/v1/ui.ftl (HandleStrings).
const SERVED = new URL('../../../strings/v1/ui.en-GB.ftl', import.meta.url)
const DEV_COPY = new URL('../../public/strings/v1/ui.ftl', import.meta.url)

function messageIds(file: URL): string[] {
  return new FluentResource(readFileSync(file, 'utf-8')).body.map((entry) => entry.id)
}

describe('UI strings parity', () => {
  it('served file defines every id in the dev copy', () => {
    const served = new Set(messageIds(SERVED))
    const missing = messageIds(DEV_COPY).filter((id) => !served.has(id))
    expect(missing).toEqual([])
  })
})
