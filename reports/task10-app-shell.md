# Task 10 — App Shell Component (mf-app + mf-toast + main.ts)

## Summary

Implemented the top-level app shell that wires together all Phase 1 components:
search bar, API client, graph transform, 3D force graph, results panel, and toast notifications.

## Files Created / Modified

| File | Action | Purpose |
|------|--------|---------|
| `web/src/components/mf-toast.ts` | Created | Lightweight toast notification component (fixed-position, auto-hide) |
| `web/src/components/mf-app.ts` | Created | App shell: orchestrates search → API → graph + HUD panel wiring |
| `web/src/main.ts` | Modified | Updated to import `mf-app` as the single entry point for all components |

## Key Design Decisions

- **Hash-based routing:** Uses `#/word/<term>` for deep-linking and back/forward navigation.
- **State machine:** Four states (`idle`, `loading`, `ready`, `error`) with clear UI for each.
- **Error handling:** Distinguishes 404 (word not found) from generic errors via `ApiError`.
- **Toast pattern:** `mf-toast` uses a simple `show(message, duration)` imperative API, queried from the shadow DOM.
- **Component registration cascade:** `mf-app` imports all child components, and `main.ts` imports only `mf-app`.

## Verification

| Check | Result |
|-------|--------|
| `npx tsc --noEmit` | Pass (no errors) |
| `npx vitest run` | 18 tests passing (4 test files) |
| `npx vite build` | Success (427 modules, 1339 kB bundle) |

## Commit

```
c4d0c22 feat: add app shell wiring search -> API -> graph + HUD panel + toast
```
