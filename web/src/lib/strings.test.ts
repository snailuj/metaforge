import { describe, it, expect, vi, beforeEach } from 'vitest'
import { initStrings, getString } from './strings'

const MOCK_FTL = `
search-placeholder = Search for a word...
results-word-not-found = "{$word}" was not found in the thesaurus.
pos-noun = noun
`

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('Fluent strings', () => {
  it('returns a translated string after init', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(MOCK_FTL),
    }))

    await initStrings()
    expect(getString('search-placeholder')).toBe('Search for a word...')
  })

  it('interpolates variables', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(MOCK_FTL),
    }))

    await initStrings()
    const result = getString('results-word-not-found', { word: 'xyzzy' })
    expect(result).toContain('xyzzy')
    expect(result).toContain('was not found in the thesaurus.')
  })

  it('returns the message ID as fallback if not found', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(MOCK_FTL),
    }))

    await initStrings()
    expect(getString('nonexistent-key')).toBe('nonexistent-key')
  })
})
