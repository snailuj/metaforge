# Testing Patterns

**Analysis Date:** 2026-02-14

## Test Framework

**Runner (Web):**
- Framework: Vitest 3.0.0
- Config: `web/vite.config.ts` in `test` block
- Environment: `happy-dom` (DOM simulation for unit tests without full browser)

**Runner (API):**
- Framework: Go built-in `testing` package
- Convention: `*_test.go` files in same package as source
- Run: `go test ./...` or `go test ./internal/package`

**Assertion Library:**
- Web: Vitest assertions (`expect()` API)
- API: Built-in `testing.T` assertions (no external library)

**Run Commands:**
```bash
# Web - all tests
npm run test

# Web - watch mode (continuous)
npm run test:watch

# Web - coverage report
npm run test:coverage
# Output: web/coverage/

# API - all tests
go test ./...

# API - verbose output
go test -v ./...

# API - with coverage
go test -cover ./...
```

## Test File Organization

**Location (Web):**
- Co-located with source: `src/components/mf-app.test.ts` next to `src/components/mf-app.ts`
- Pattern: `{source-file}.test.ts`
- tsconfig.json excludes tests from emit: `"exclude": ["src/**/*.test.ts"]`

**Location (API):**
- Go convention: `{package}/{name}_test.go` in same directory
- Example: `api/internal/handler/handler_test.go` in same directory as `handler.go`

**File Structure (TypeScript):**
```
web/src/
├── components/
│   ├── mf-app.ts
│   ├── mf-app.test.ts
│   ├── mf-search-bar.ts
│   ├── mf-search-bar.test.ts
│   └── ...
├── api/
│   ├── client.ts
│   ├── client.test.ts
│   └── ...
├── lib/
│   ├── strings.ts
│   ├── strings.test.ts
│   └── ...
└── graph/
    ├── transform.ts
    ├── transform.test.ts
    └── ...
```

## Test Structure

**Suite Organization (Vitest):**
```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('MfApp', () => {
  let el: MfApp

  beforeEach(async () => {
    el = new MfApp()
    document.body.appendChild(el)
    await el.updateComplete
  })

  afterEach(() => {
    document.body.removeChild(el)
    vi.restoreAllMocks()
  })

  it('starts in idle state', () => {
    const status = el.shadowRoot!.querySelector('.status-message')
    expect(status).not.toBeNull()
  })

  describe('nested suite', () => {
    it('test in nested suite', () => {
      // test
    })
  })
})
```

**Suite Organization (Go):**
```go
package handler

import (
  "testing"
)

func TestForgeSuggestEndpoint(t *testing.T) {
  h, err := NewHandler(testDBPath)
  if err != nil {
    t.Fatalf("Failed to create handler: %v", err)
  }
  defer h.Close()

  // Test logic
  if result != expected {
    t.Errorf("Expected %v, got %v", expected, result)
  }
}
```

**Patterns:**
- Web: Group related tests with nested `describe()` blocks (e.g., `describe('rarity filter', () => { ... })`)
- Web: Use `beforeEach()`/`afterEach()` for setup/teardown on every test
- Go: Use table-driven tests for parametric variations
  - Example from `forge_test.go`:
    ```go
    tests := []struct {
      name     string
      distance float64
      overlap  int
      expected Tier
    }{
      {"legendary - high distance, strong overlap", 0.8, 4, TierLegendary},
      {"interesting - high distance, weak overlap", 0.8, 1, TierInteresting},
      // ...
    }
    for _, tt := range tests {
      t.Run(tt.name, func(t *testing.T) {
        tier := ClassifyTier(tt.distance, tt.overlap)
        if tier != tt.expected {
          t.Errorf("ClassifyTier(%v, %d) = %v, want %v", ...)
        }
      })
    }
    ```

## Mocking

**Framework (Web):**
- Framework: Vitest mocking with `vi` object
- Mocking strategy: Mock modules BEFORE importing component under test

**Mocking Patterns (Web):**

1. **Mock external packages that require unavailable resources:**
   ```typescript
   // Mock 3D libraries that need WebGL (unavailable in happy-dom)
   const chainable = new Proxy({}, { get: () => () => chainable })
   vi.mock('3d-force-graph', () => ({ default: () => () => chainable }))
   vi.mock('three-spritetext', () => ({ default: vi.fn() }))
   ```

2. **Mock internal modules with custom implementations:**
   ```typescript
   vi.mock('@/api/client', () => ({
     lookupWord: vi.fn(),
     ApiError: class ApiError extends Error {
       status: number
       constructor(message: string, status: number) {
         super(message)
         this.name = 'ApiError'
         this.status = status
       }
     },
   }))
   ```

3. **Partial mocking (preserve real exports, override specific functions):**
   ```typescript
   vi.mock('@/api/client', async () => {
     const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client')
     return {
       ...actual,
       autocompleteWord: (...args) => mockAutocomplete(...args),
     }
   })
   ```

4. **Global stubs (mock browser APIs):**
   ```typescript
   vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
     ok: true,
     text: () => Promise.resolve(FTL_CONTENT),
   }))
   ```

5. **Spy on console methods:**
   ```typescript
   const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
   // ... test that uses console.error
   expect(consoleError).toHaveBeenCalledWith('error message')
   consoleError.mockRestore()
   ```

6. **Mock timers for debounced/delayed operations:**
   ```typescript
   beforeEach(() => {
     vi.useFakeTimers()
   })
   afterEach(() => {
     vi.useRealTimers()
   })
   // In test:
   vi.advanceTimersByTime(250) // advance debounce timer
   await new Promise(r => queueMicrotask(r)) // allow microtasks
   ```

**What to Mock:**
- External APIs (HTTP requests)
- Heavy dependencies (3D rendering libraries)
- Filesystem operations (fetch for strings files)
- Browser APIs (only when testing DOM interaction, not actual browser functionality)
- Time-based operations (debounce, timers)

**What NOT to Mock:**
- Core Lit lifecycle (`updateComplete`, `render()`)
- DOM query methods (`querySelector`, `querySelectorAll`)
- Custom events (dispatch and listen normally)
- Pure utility functions (test as-is)

## Fixtures and Factories

**Test Data (Web):**
- Define mock objects inline or at module level
- Example from `mf-app.test.ts`:
  ```typescript
  const mockResult: LookupResult = {
    word: 'fire',
    senses: [{
      synset_id: '1',
      pos: 'noun',
      definition: 'combustion',
      synonyms: [],
      relations: { hypernyms: [], hyponyms: [], similar: [] },
    }],
  }
  ```
- Example from `mf-search-bar.test.ts`:
  ```typescript
  const TEST_SUGGESTIONS: AutocompleteSuggestion[] = [
    { word: 'fire', definition: 'the event of something burning', sense_count: 21, rarity: 'common' },
    { word: 'firearm', definition: 'a portable gun', sense_count: 1, rarity: 'unusual' },
    { word: 'firebrand', definition: 'a piece of wood...', sense_count: 2, rarity: 'rare' },
  ]
  ```

**Test Data (Go):**
- Define as package-level constants or module-level variables
- Example from `graph/transform.test.ts` (used for both langs):
  ```go
  const testDBPath = "../../../data-pipeline/output/lexicon_v2.db"
  ```
- Reuse production handler with test database
  - Example: `handler_test.go` calls `NewHandler(testDBPath)` with real lexicon

**Location:**
- Web: Inline in test file (no separate fixtures directory)
- Go: Test database at `data-pipeline/output/lexicon_v2.db` (shared fixture)

## Coverage

**Requirements:**
- No minimum enforced; aim for high coverage on core logic
- API test suite: 38 tests passing (as of Sprint Zero)
- Web test suite: ~15 test files covering components and utilities

**View Coverage (Web):**
```bash
npm run test:coverage
# Opens web/coverage/index.html in browser
# Providers: v8 reporter with text, text-summary, html output
```

## Test Types

**Unit Tests (Web):**
- Scope: Individual component or utility function
- Approach: Mock dependencies, test single responsibility
- Example: `transform.test.ts` tests graph transformation without API calls
  - Input: LookupResult fixture
  - Tests: Node deduplication, cap at max nodes, rarity filtering
  - No mocking: Pure function transformation

**Unit Tests (Go):**
- Scope: Individual function or handler
- Approach: Use production database fixture, isolate logic
- Example: `handler_test.go` tests HTTP endpoints
  - Setup: Real handler with test database
  - Test: HTTP request/response handling
  - No mocking: Real database queries

**Integration Tests (Web):**
- Scope: Component interaction (e.g., search → graph update)
- Approach: Minimal mocking; test event flow
- Example: `mf-app.test.ts` tests "transition to ready state on successful lookup"
  - Mocks only: API client (`lookupWord`)
  - Tests: Search event triggers lookup, state transitions, rendering

**Integration Tests (Go):**
- Approach: Multiple handlers tested in sequence if needed
- Not explicitly separated; use helper functions to set up complex scenarios

**E2E Tests:**
- Not used in current codebase
- Would test full flow: search input → API → 3D graph render
- Candidates: Playwright or similar for browser automation

## Common Patterns

**Async Testing (Web):**
```typescript
// Pattern 1: Wait for component update
await el.updateComplete

// Pattern 2: Wait for microtasks (async resolve)
await new Promise(r => queueMicrotask(r))

// Pattern 3: Wait for timeouts
await new Promise(r => setTimeout(r, 100))

// Combine in test:
searchBar?.dispatchEvent(new CustomEvent('mf-search', { detail: { word: 'fire' } }))
await new Promise(r => setTimeout(r, 100)) // API mock resolves
await el.updateComplete
expect(appState).toBe('ready')
```

**Event Testing (Web):**
```typescript
// Dispatch custom event
el.dispatchEvent(new CustomEvent('mf-search', {
  detail: { word: 'fire' },
  bubbles: true,
  composed: true,
}))

// Listen for event
const handler = vi.fn()
el.addEventListener('mf-search', handler)
// ... trigger event
expect(handler).toHaveBeenCalledWith(
  expect.objectContaining({ detail: { word: 'fire' } })
)

// Query shadow DOM
const status = el.shadowRoot!.querySelector('.status-message')
expect(status?.textContent).toContain('loading')
```

**Error Testing (Web):**
```typescript
// Mock rejection
const { ApiError } = await import('@/api/client')
vi.mocked(lookupWord).mockRejectedValueOnce(new ApiError('not found', 404))

// Trigger error path
searchBar?.dispatchEvent(new CustomEvent('mf-search', { detail: { word: 'xyznoword' } }))
await new Promise(r => setTimeout(r, 50))
await el.updateComplete

// Verify error handling
const error = el.shadowRoot!.querySelector('.error-message')
expect(error?.textContent).toContain('Not found')
```

**Error Testing (Go):**
```go
// Positive case
if w.Code != http.StatusOK {
  t.Fatalf("Expected 200, got %d: %s", w.Code, w.Body.String())
}

// Negative case
if w.Code != http.StatusNotFound {
  t.Errorf("Expected 404, got %d", w.Code)
}

// Use errors.Is for sentinel errors
if err := db.GetSynset(badID); errors.Is(err, sql.ErrNoRows) {
  t.Logf("Expected: synset not found")
}
```

**Stale Response Guard (Web):**
```typescript
// Testing race conditions in async operations
it('discards stale response when a newer lookup overtakes it', async () => {
  let resolveFirst!: (v: LookupResult) => void
  const firstPromise = new Promise<LookupResult>(r => { resolveFirst = r })

  vi.mocked(lookupWord)
    .mockReturnValueOnce(firstPromise)      // Slow response
    .mockResolvedValueOnce(fastResult)      // Fast response

  ;(el as any).doLookup('slow')
  ;(el as any).doLookup('fast')             // Overtakes first

  await new Promise(r => setTimeout(r, 100))
  await el.updateComplete

  resolveFirst(slowResult)                  // First resolves late
  await new Promise(r => setTimeout(r, 100))
  await el.updateComplete

  // Verify staleness guard kept fast result
  expect((el as any).result.word).toBe('fast')
})
```

**Debounce Testing (Web):**
```typescript
// Helper function to type, debounce, and wait
async function typeAndDebounce(el: MfSearchBar, value: string) {
  const input = el.shadowRoot!.querySelector('input')!
  input.value = value
  input.dispatchEvent(new Event('input'))
  vi.advanceTimersByTime(250)               // Debounce timer
  await new Promise(r => queueMicrotask(r)) // Async resolve
  await el.updateComplete
}

// Test debounce resets on subsequent input
it('resets debounce timer on subsequent input', async () => {
  const input = el.shadowRoot!.querySelector('input')!
  input.value = 'fir'
  input.dispatchEvent(new Event('input'))
  vi.advanceTimersByTime(150)               // Not enough

  input.value = 'fire'                      // Reset
  input.dispatchEvent(new Event('input'))
  vi.advanceTimersByTime(150)               // Still not enough

  vi.advanceTimersByTime(100)               // Now 250ms total
  await new Promise(r => queueMicrotask(r))

  expect(mockAutocomplete).toHaveBeenCalledOnce()
  expect(mockAutocomplete).toHaveBeenCalledWith('fire')
})
```

---

*Testing analysis: 2026-02-14*
