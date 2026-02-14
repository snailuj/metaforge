# Coding Conventions

**Analysis Date:** 2026-02-14

## Naming Patterns

**Files (TypeScript):**
- Components: `mf-{component-name}.ts` (kebab-case with `mf-` prefix for custom elements)
  - Example: `mf-search-bar.ts`, `mf-force-graph.ts`, `mf-results-panel.ts`
- Test files: `{name}.test.ts` (co-located with source)
- Utilities/helpers: `{name}.ts` (lowercase, descriptive)
  - Example: `strings.ts`, `transform.ts`, `colours.ts`
- Types/interfaces: `{name}.ts` (uppercase exports)
  - Example: `api.ts`, `types.ts` in `src/types/` and `src/graph/`

**Files (Go):**
- Package files: `{name}.go` (lowercase, no underscores)
  - Example: `handler.go`, `thesaurus.go`, `db.go`
- Test files: `{name}_test.go` (Go convention)
  - Example: `handler_test.go`, `thesaurus_test.go`
- Package-level constants and helpers in same file as primary type

**Functions/Methods:**
- TypeScript: `camelCase` for all functions
  - Example: `lookupWord()`, `transformLookupToGraph()`, `getString()`
- Go: `PascalCase` for exported, `camelCase` for unexported
  - Example: `GetLookup()`, `HandleSuggest()` (exported) vs `querySenses()`, `attachRarity()` (unexported)
- Private Lit component methods: `camelCase` prefixed with underscore or hash for privacy
  - Example: `private handleSearch()`, `private doLookup()`

**Variables/Properties:**
- TypeScript: `camelCase` for all variables
  - Example: `currentWord`, `graphData`, `errorMessage`
  - State properties: `@state() private appState`
- Go: `camelCase` for local vars, `PascalCase` for struct fields (JSON tags use snake_case)
  - Example: `type Sense { SynsetID string; Definition string }` (struct) → JSON: `synset_id`, `definition`

**Types/Interfaces:**
- TypeScript: `PascalCase` (interfaces and type aliases)
  - Example: `LookupResult`, `GraphData`, `Rarity`, `RelationType`
- Go: `PascalCase` for exported types
  - Example: `type Synset struct { ... }`, `type Match struct { ... }`
- Union types: Discriminated with literal types where possible
  - Example: `type Rarity = 'common' | 'unusual' | 'rare'`
  - Example: `type AppState = 'idle' | 'loading' | 'ready' | 'error'`

**Constants:**
- TypeScript: `UPPER_SNAKE_CASE` only for truly immutable config; prefer lowercase for module-level magic numbers
  - Example: `const DEFAULT_MAX_NODES = 80` (in `transform.ts`)
  - Example: `const defaultWord = ''` (for defaults)
- Go: `UPPER_SNAKE_CASE` for exported constants
  - Example: `const DefaultThreshold = 0.7`, `const DefaultLimit = 50`

## Code Style

**Formatting:**
- TypeScript: No explicit formatter configured (relies on TypeScript compiler)
- Indentation: 2 spaces (TypeScript/Web)
- Line length: No strict limit; keep logical units readable (~100 chars guideline)

**Linting:**
- TypeScript: TypeScript compiler in strict mode (`"strict": true` in `tsconfig.json`)
  - Enforced: `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`
  - Type checking is mandatory; no implicit `any`
- Go: Standard Go conventions; `go fmt` compatible

**Type Safety:**
- TypeScript: Always use strict types; no `any` except in legacy mocking proxies
  - Example: `vi.mock()` uses `Proxy<any>` for chainable mocks, but only in test setup
  - All function parameters and return types must be explicitly typed
- Go: Types are explicit; use error wrapping with `fmt.Errorf` for context

## Import Organization

**Order (TypeScript):**
1. External packages (`lit`, `@fluent/bundle`, `3d-force-graph`)
2. Internal absolute paths (`@/api/client`, `@/types/api`, `@/lib/strings`)
3. Relative imports (`.`, `../`)
4. Side-effect imports (component registration)

**Example from `mf-app.ts`:**
```typescript
import { LitElement, html, css, type PropertyValues } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { lookupWord, ApiError } from '@/api/client'
import { transformLookupToGraph } from '@/graph/transform'
import { initStrings, getString } from '@/lib/strings'
import type { LookupResult } from '@/types/api'
import type { GraphData, Rarity } from '@/graph/types'
import type { MfToast } from './mf-toast'

// Import components so they register
import './mf-search-bar'
import './mf-force-graph'
import './mf-results-panel'
import './mf-toast'
```

**Order (Go):**
1. Standard library (`net/http`, `database/sql`, `encoding/json`)
2. Third-party (`github.com/mattn/go-sqlite3`, `github.com/go-chi/chi/v5`)
3. Internal (`github.com/snailuj/metaforge/internal/...`)

**Path Aliases:**
- TypeScript: `@/*` → `src/*` (defined in `tsconfig.json` and `vite.config.ts`)
  - Allows clean imports: `import { getString } from '@/lib/strings'`

## Error Handling

**TypeScript (Lit Components):**
- Use custom error classes for specific error types
  - Example: `ApiError` in `api/client.ts` extends `Error` with `status` property
- Components catch errors and transition to error state
  - Example: `mf-app.ts` catches API errors, distinguishes 404 from others via `err instanceof ApiError && err.status === 404`
- Always handle async errors in event handlers:
  ```typescript
  private async doLookup(word: string) {
    try {
      const result = await lookupWord(word)
      this.result = result
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        // Handle specific case
      } else {
        // Generic error handling
      }
    }
  }
  ```

**TypeScript (API Client):**
- Validate response shape before returning
  - Example: `client.ts` checks `if (!data || typeof data.word !== 'string')`
  - Throw `ApiError` with status code if validation fails
- Log fetch errors; return safe fallback for non-fatal errors
  - Example: `strings.ts` logs to `console.error` on fetch failure, returns message IDs as fallback

**Go (Handlers):**
- Sentinel errors for domain-specific conditions
  - Example: `thesaurus.ErrWordNotFound = errors.New("word not found")`
  - Check with `errors.Is(err, thesaurus.ErrWordNotFound)` for distinction
- Wrap errors with context using `fmt.Errorf(..., %w, err)` for tracing
- Log errors with `slog.Error()` or `slog.Warn()` for non-fatal issues
  - Example: `slog.Warn("attachRarity failed", "lemma", lemma, "err", err)`
- Return appropriate HTTP status codes; include JSON error body
  - 400 for bad input, 404 for not found, 500 for server errors
  - Error response: `{"error": "description"}`

**Go (Core Packages):**
- Return `error` as last return value
  - Example: `func GetLookup(db *sql.DB, lemma string) (*LookupResult, error)`
- Use `sql.ErrNoRows` check before generic `error` checks
  - Example: `if err == sql.ErrNoRows { return nil, ErrWordNotFound }`

## Logging

**Framework:**
- TypeScript: `console` methods (`console.error`, `console.warn`) for development
  - Mocked in tests with `vi.spyOn(console, 'error')`
- Go: `log/slog` with structured logging
  - Levels: `slog.Error()`, `slog.Warn()`, `slog.Info()`

**Patterns:**
- TypeScript: Log only significant failures, not every operation
  - Example: `console.error('Failed to load strings:', response.status)`
- Go: Always log with context key-value pairs
  - Example: `slog.Error("lookup failed", "word", word, "err", err)`
- Never log sensitive data (API responses with secrets, user tokens, etc.)

## Comments

**When to Comment:**
- Functions: Always include JSDoc/comment block for public/exported functions
- Complex logic: Comment non-obvious algorithms or workarounds
- Workarounds: Mark with context (e.g., `// Stale response guard: newer lookup superseded this one`)
- Do NOT comment obvious code (e.g., `i++ // increment i`)

**JSDoc/TSDoc:**
- Use block comments for function documentation
  - Example from `client.ts`:
    ```typescript
    /**
     * Look up a word in the thesaurus.
     * Vite dev server proxies /thesaurus/* to localhost:8080.
     */
    export async function lookupWord(word: string): Promise<LookupResult>
    ```
- Go: Use `// Package name ...` comment for package documentation
  - Example from `handler.go`: `// Package handler provides HTTP handlers for the Metaforge API.`

## Function Design

**Size:**
- Keep functions small and focused (ideally < 30 lines for TypeScript methods)
- Extract helpers when logic exceeds a single responsibility
  - Example: `mf-app.ts` extracts `getWordFromHash()`, `setWordHash()` from `doLookup()`

**Parameters:**
- Use positional parameters for < 3 args
- Use options objects for > 3 args or optional/named parameters
  - Example: `function transformLookupToGraph(result: LookupResult, maxNodes = DEFAULT_MAX_NODES)`
- Prefer immutable parameters; no reassignment
- Go: Use pointers only when mutation is necessary or for large structs

**Return Values:**
- Use tuple returns for functions with multiple concerns (Go pattern)
  - Example: `(data, error)` in Go; Promise-based in TypeScript
- Return early to reduce nesting
  - Example: `if (id !== this.lookupId) return // stale` in `mf-app.ts` doLookup()
- TypeScript: Prefer returning discriminated unions over optional chaining for error cases
  - Example: Return `ApiError` rather than `null`

## Module Design

**Exports:**
- TypeScript: Export only public API; use private methods for internal logic
  - Example: `mf-app.ts` exports class via `@customElement()` decorator
  - Private methods use `private` keyword or class field initializers
- Go: Exported functions start with capital letter; unexported start with lowercase
  - Example: `func GetLookup(...)` (exported) vs `func querySenses(...)` (unexported)

**Barrel Files:**
- Not used in this codebase
- Individual imports preferred for clarity
  - Example: `import { lookupWord } from '@/api/client'` not from barrel

**Module-Level State:**
- Minimize module-level mutable state
  - Example: `strings.ts` uses `let bundle: FluentBundle | null = null` for lazy initialization
  - Provides `resetStrings()` for testing
- Prefer passing state through function parameters or Lit component properties
  - Example: `mf-app.ts` uses `@state()` decorators, not module globals

## Custom Elements (Lit)

**Naming:**
- Class: `Mf{ComponentName}` (PascalCase with `Mf` prefix)
  - Example: `class MfApp extends LitElement`
- Tag: `mf-{component-name}` (kebab-case)
  - Registered via `@customElement('mf-search-bar')`
- Global type augmentation for HTML element map:
  ```typescript
  declare global {
    interface HTMLElementTagNameMap {
      'mf-app': MfApp
    }
  }
  ```

**Decorators:**
- `@customElement('tag-name')` for registration
- `@state()` for reactive properties
- `@property()` for public properties (rarely used; prefer @state)

**Lifecycle:**
- `connectedCallback()`: DOM setup, event listeners, async initialization
- `willUpdate()`: React to property changes before render
- `render()`: Return TemplateResult
- `disconnectedCallback()`: Cleanup, remove listeners

## Type Imports

**TypeScript:**
- Use `type` keyword for pure type imports to avoid runtime bloat
  - Example: `import type { LookupResult } from '@/types/api'`
  - Compare to: `import { lookupWord } from '@/api/client'` (runtime)
- Go: Not applicable; types are part of package

---

*Convention analysis: 2026-02-14*
