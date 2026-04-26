# Tasks 5 & 6 Report: API Client + Fluent Strings Client

**Date:** 2026-02-07
**Branch:** `feat/api-and-strings` in `mf-api-strings`
**Commits:**
- `d127ced` — feat: add API client with lookupWord fetch wrapper
- `7a31ee3` — feat: add Fluent strings client with init and getString

---

## Task 5: API Client

### What was done
Created `web/src/api/client.ts` containing:
- **`ApiError`** class — custom error with HTTP status code, extends `Error`.
- **`lookupWord(word)`** — async fetch wrapper that calls `/thesaurus/lookup?word=<encoded>`, parses JSON as `LookupResult`, and throws `ApiError` on non-OK responses.

### Verification
- `npx tsc --noEmit` passed with zero errors, confirming the module compiles against the existing `@/types/api` type definitions.

### Files
| File | Action |
|------|--------|
| `web/src/api/client.ts` | Created |

---

## Task 6: Fluent Strings Client (TDD)

### What was done
1. **Red phase:** Created `web/src/lib/strings.test.ts` with 3 tests. Ran tests — they failed because `strings.ts` did not exist yet. This confirms genuine TDD red/green cycle.
2. **Green phase:** Created `web/src/lib/strings.ts` implementing `initStrings()` and `getString()` using `@fluent/bundle`. Ran tests — all 3 passed.

### Test results
```
 ✓ src/lib/strings.test.ts (3 tests) 8ms

 Test Files  1 passed (1)
      Tests  3 passed (3)
   Duration  823ms
```

Tests cover:
1. Basic string lookup after initialisation.
2. Variable interpolation (`{$word}` placeholder).
3. Fallback to message ID when key is not found.

### Files
| File | Action |
|------|--------|
| `web/src/lib/strings.test.ts` | Created |
| `web/src/lib/strings.ts` | Created |

---

## Issues
None. Both tasks completed cleanly with no adjustments needed.

---

## Self-Review

| Criterion | Assessment |
|-----------|------------|
| **TDD discipline** | Followed correctly — test written and confirmed failing before implementation. |
| **Type safety** | API client imports `LookupResult` type; tsc compiles cleanly. |
| **Error handling** | `ApiError` captures status code; `initStrings` gracefully handles fetch failures and parse errors via console.error. |
| **Fallback behaviour** | `getString` returns the message ID when bundle is uninitialised or key is missing — safe default. |
| **Encoding** | `lookupWord` uses `encodeURIComponent` on trimmed, lowercased input — handles special characters. |
| **Module isolation** | Fluent bundle stored in module-level `let` — simple, no global pollution. Tests use `vi.stubGlobal('fetch', ...)` to mock fetch cleanly. |
| **Commit hygiene** | Two atomic commits, one per task, descriptive messages. |
