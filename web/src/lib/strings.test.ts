import { describe, it, expect, vi, beforeEach } from 'vitest'
import { initStrings, getString, resetStrings } from './strings'

const MOCK_FTL = `
search-placeholder = Search for a word...
results-word-not-found = "{$word}" was not found in the thesaurus.
pos-noun = noun
`

beforeEach(() => {
  vi.restoreAllMocks()
  resetStrings()
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

  it('returns message ID before initStrings is called', () => {
    expect(getString('some-key')).toBe('some-key')
  })

  it('falls back to message IDs when fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }))
    await initStrings()
    expect(getString('search-placeholder')).toBe('search-placeholder')
  })

  it('logs parse errors for malformed FTL', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    // Fluent's addResource errors are rare in practice - the parser is very tolerant.
    // Test that console.error is called if errors array has length > 0.
    // We'll mock FluentBundle to force an error condition.
    const { FluentBundle } = await import('@fluent/bundle')
    const originalAddResource = FluentBundle.prototype.addResource

    FluentBundle.prototype.addResource = vi.fn(() => ['mock error'])

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve('search-placeholder = Test'),
    }))

    await initStrings()

    expect(consoleError).toHaveBeenCalledWith(
      'Fluent parse errors:',
      expect.arrayContaining(['mock error']),
    )

    FluentBundle.prototype.addResource = originalAddResource
    consoleError.mockRestore()
  })
})
