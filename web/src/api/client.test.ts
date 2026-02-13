import { describe, it, expect, vi, beforeEach } from 'vitest'
import { lookupWord, autocompleteWord, ApiError } from './client'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('lookupWord', () => {
  it('returns LookupResult on success', async () => {
    const mockResult = { word: 'test', senses: [] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResult),
    }))
    const result = await lookupWord('test')
    expect(result).toEqual(mockResult)
  })

  it('trims and lowercases the word before fetching', async () => {
    const mockResult = { word: 'hello', senses: [] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResult),
    }))
    await lookupWord('  HELLO  ')
    expect(fetch).toHaveBeenCalledWith('/thesaurus/lookup?word=hello')
  })

  it('throws ApiError with status on HTTP error with JSON body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ error: 'Word not found' }),
    }))
    await expect(lookupWord('xyzzy')).rejects.toThrow(ApiError)
    try {
      await lookupWord('xyzzy')
    } catch (e) {
      expect((e as ApiError).status).toBe(404)
      expect((e as ApiError).message).toBe('Word not found')
    }
  })

  it('throws ApiError on HTTP error with non-JSON body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error('not json')),
    }))
    await expect(lookupWord('test')).rejects.toThrow(ApiError)
  })

  it('throws ApiError on invalid response shape', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ unexpected: 'data' }),
    }))
    await expect(lookupWord('test')).rejects.toThrow(ApiError)
  })
})

describe('autocompleteWord', () => {
  it('returns suggestions on success', async () => {
    const mockSuggestions = [
      { word: 'fire', definition: 'the event of something burning', sense_count: 21, rarity: 'common' },
      { word: 'firearm', definition: 'a portable gun', sense_count: 1, rarity: 'unusual' },
    ]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ suggestions: mockSuggestions }),
    }))
    const result = await autocompleteWord('fir')
    expect(result).toEqual(mockSuggestions)
  })

  it('trims and lowercases the prefix before fetching', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ suggestions: [] }),
    }))
    await autocompleteWord('  FIR  ')
    expect(fetch).toHaveBeenCalledWith('/thesaurus/autocomplete?prefix=fir&limit=10')
  })

  it('returns empty array when no matches', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ suggestions: [] }),
    }))
    const result = await autocompleteWord('xyzzy')
    expect(result).toEqual([])
  })

  it('throws ApiError on HTTP error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ error: 'prefix must be at least 2 characters' }),
    }))
    await expect(autocompleteWord('a')).rejects.toThrow(ApiError)
  })

  it('throws ApiError on invalid response shape', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ unexpected: 'data' }),
    }))
    await expect(autocompleteWord('fir')).rejects.toThrow(ApiError)
  })
})
