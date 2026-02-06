# Core Thesaurus: Front-to-Back Implementation Plan

**Date:** 2026-02-06
**Status:** Ready for implementation

## Goal

First end-to-end frontend feature: type a word, see sense-grouped results with synonyms, right-click to copy. Foundation for all future UI work.

## Tech Stack

- **Frontend:** TypeScript + Vite + Lit (web components)
- **Backend:** Go + Chi (extend existing API)
- **Strings:** Mozilla Fluent (`@fluent/bundle`)
- **Styling:** CSS custom properties (antique/alchemical theme)

## Directory Structure

```
web/
  src/
    api/           # API client
    components/    # Lit web components
    lib/           # Utilities (strings, debounce, clipboard)
    styles/        # Design tokens + base CSS
    types/         # TypeScript interfaces
  index.html
  vite.config.ts
  tsconfig.json
  package.json
strings/
  v1/
    ui.en-GB.ftl   # Fluent strings
```

---

## Implementation Sequence

### Phase A: Backend (Go)

**A1. Thesaurus data layer** — `api/internal/thesaurus/thesaurus.go`

New `GetLookup(db, lemma)` function returning senses grouped by synset. Two queries total:
1. All synsets + synonyms for the lemma (GROUP_CONCAT)
2. Relations for those synset_ids in bulk (hypernyms, hyponyms, similar)

Types: `LookupResult { Word, Senses[] }`, `Sense { SynsetID, POS, Definition, Synonyms[], Relations }`, `RelatedWord { Word, SynsetID }`

Tests: fire (21 senses), melancholy (synonym grouping), unknown word (error).

**A2. HTTP handler** — extend `api/internal/handler/`

`GET /thesaurus/lookup?word={word}` → JSON response. Refactor `ForgeHandler` into shared handler struct holding one `*sql.DB` for both feature areas.

Tests: 200/400/404 status codes, response shape.

**A3. Fluent strings endpoint + route wiring**

`GET /strings/v1/ui.ftl` — serves `.ftl` file with `Cache-Control: immutable`. Create initial `strings/v1/ui.en-GB.ftl` with core thesaurus strings. Add CORS middleware for dev (`localhost:5173`). Wire all new routes in `main.go`.

### Phase B: Frontend Scaffolding

**B1. Project setup** — Vite + Lit + TypeScript

`web/package.json` with deps: `lit`, `@fluent/bundle`, `vitest`, `@testing-library/dom`. Vite config with proxy (`/api/*` → `:8080`). Strict TypeScript.

**B2. Design system tokens** — `web/src/styles/tokens.css`

CSS custom properties from MetaforgeConcept.png antique theme:
- Palette: parchment `#f5e6d3`, sepia `#c4a56b`, gold `#d4af37`, russet `#8b4513`, ink `#2c1810`
- Typography: `Playfair Display` headings, `Crimson Text` body
- Spacing, shadows, transitions
- Base CSS: parchment background, russet word links, gold focus outlines, themed scrollbars
- Tooltip base style: darker parchment bg, very dark border, rounded corners, white text, mouse-following option

**B3. Fluent client module** — `web/src/lib/strings.ts`

Fetch `.ftl` on init, parse into `FluentBundle`, export `getString(id, args?)`. Strict mode for tests (throw on missing IDs). Fallback: render ID + console.warn.

**B4. API client** — `web/src/api/client.ts`

`lookupWord(word)` → typed `LookupResult`. Error handling for 400/404/network.

### Phase C: Components (Lit Web Components)

**C1. SearchBar** — `<mf-search-bar>`

Debounced input (200ms default), `/` shortcut to focus, `Escape` to clear. Placeholder from Fluent. Fires custom event with search term.

**C2. ResultsPanel** — `<mf-results-panel>`

Receives `LookupResult`, renders sense groups. Each sense: POS badge, definition, synonym list. Excludes searched word from synonym lists. Empty state from Fluent.

**C3. SynonymWord** — `<mf-synonym-word>`

Russet-coloured, underlined database words with two interactions:
- **Right-click:** Copy word to clipboard. Suppress context menu. Brief gold flash feedback.
- **Left-click:** Navigate to word (not implemented yet — no-op for now, wired later).
- **Hover tooltip:** Mouse-following tooltip reading "Right-click to copy". Styled: darker parchment background (`--colour-parchment-dark`), very dark border, rounded corners, white text. Tooltip follows mouse cursor.
- Keyboard: `Enter` copies (equivalent to right-click), `aria-label="Copy {word}"`.

**C4. AppShell** — `<mf-app>`

Root layout: CSS Grid, results panel left (`380px`), placeholder right (reserved for 3D). Calls `initStrings()` on startup, wires search → API → results. Loading/error states.

### Phase D: Polish

**D1. Keyboard navigation** — Tab through synonyms, Enter/Space to copy, arrow keys within sense groups.

**D2. Loading & error states** — Skeleton loader, "word not found" message, network error with retry.

---

## API Response Shape

```json
{
  "word": "fire",
  "senses": [
    {
      "synset_id": "94543",
      "pos": "noun",
      "definition": "the process of combustion...",
      "synonyms": ["flame", "flaming"],
      "relations": {
        "hypernyms": [{"word": "oxidation", "synset_id": "..."}],
        "hyponyms": [{"word": "blaze", "synset_id": "..."}],
        "similar": []
      }
    }
  ]
}
```

## Known Gaps (Deliberate Deferrals)

| Gap | Reason |
|-----|--------|
| Antonyms | Not in database — `lexrelations` not imported. Fast-follow. |
| Rarity badges | Frequencies table empty — needs SUBTLEX-UK import. |
| Register/connotation | Enrichment fields not populated yet. |
| 3D visualisation | Reserved space only — not in scope. |
| Left-click navigation | Wired later when word navigation is implemented. |

## Key Files to Modify

| Existing file | Change |
|---------------|--------|
| `api/cmd/metaforge/main.go` | Add routes, CORS middleware |
| `api/internal/handler/handler.go` | Refactor to shared handler, add `HandleLookup` |
| `.gitignore` | Add `web/node_modules/`, `web/dist/` |

## Verification

```bash
# Backend
cd api && go test ./... -v

# Frontend
cd web && npm test

# Manual: start both servers
cd api && go run ./cmd/metaforge --db ../data-pipeline/output/lexicon_v2.db &
cd web && npm run dev
# Open http://localhost:5173, type "melancholy", verify sense-grouped results
# Hover "somber" — tooltip "Right-click to copy" follows mouse
# Right-click "somber" — should copy to clipboard (no context menu)
# Press "/" — search bar focuses
```
