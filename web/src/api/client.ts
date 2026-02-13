import type { LookupResult } from '@/types/api'

export interface AutocompleteSuggestion {
  word: string
  definition: string
  sense_count: number
  rarity?: string
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/**
 * Look up a word in the thesaurus.
 * Vite dev server proxies /thesaurus/* to localhost:8080.
 */
export async function lookupWord(word: string): Promise<LookupResult> {
  const encoded = encodeURIComponent(word.trim().toLowerCase())
  const response = await fetch(`/thesaurus/lookup?word=${encoded}`)

  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: 'Unknown error' }))
    throw new ApiError(body.error || `HTTP ${response.status}`, response.status)
  }

  const data = await response.json()
  if (!data || typeof data.word !== 'string' || !Array.isArray(data.senses)) {
    throw new ApiError('Invalid response shape', 0)
  }
  return data as LookupResult
}

/**
 * Prefix-search autocomplete for the search bar.
 * Returns suggestions with word, definition, sense count, and rarity.
 */
export async function autocompleteWord(prefix: string, limit = 10): Promise<AutocompleteSuggestion[]> {
  const encoded = encodeURIComponent(prefix.trim().toLowerCase())
  const response = await fetch(`/thesaurus/autocomplete?prefix=${encoded}&limit=${limit}`)

  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: 'Unknown error' }))
    throw new ApiError(body.error || `HTTP ${response.status}`, response.status)
  }

  const data = await response.json()
  if (!data || !Array.isArray(data.suggestions)) {
    throw new ApiError('Invalid response shape', 0)
  }
  return data.suggestions as AutocompleteSuggestion[]
}
