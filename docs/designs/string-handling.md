# String Handling Design

**Status:** Complete
**Scope:** Cross-cutting concern (all features)

---

## Overview

Externalise all UI strings so text can be updated without code changes or frontend redeploys.

**Scope:** UI chrome only — buttons, labels, error messages, tooltips, game instructions. WordNet definitions and Gemini-extracted properties remain in the database.

## Key Decisions

| Aspect | Decision |
|--------|----------|
| Language | UK English only (MVP) |
| Format | Mozilla Fluent (`.ftl`) |
| File structure | Single file (`ui.en-GB.ftl`) for MVP |
| Serving | Go API endpoint |
| Caching | Versioned URL (`/strings/v{N}/ui.ftl`), cache forever per version |
| Fallback | Tests fail on missing strings; client shows ID + console warning as safety net |

**Fast-follow (out of MVP scope):**
- Locale auto-detection from browser, with manual override
- US English variant (`ui.en-US.ftl`)
- Architectural stubs in place from day one

---

## Architecture & Data Flow

### File Location

```
/strings/
  v1/
    ui.en-GB.ftl   # UK English strings
```

### Go API Endpoint

- `GET /strings/v{N}/ui.ftl?locale=en-GB` — returns the Fluent file
- Cache headers: `Cache-Control: immutable, max-age=31536000`
- Version number baked into frontend config at build time
- Canary builds can pin to different versions
- MVP: locale param accepted but ignored (always returns `en-GB`)

### Client-Side Flow

1. App init fetches `/strings/v{N}/ui.ftl?locale=en-GB`
2. Parse with `@fluent/bundle` into a `FluentBundle`
3. Store bundle in memory (React context, Zustand, or simple module singleton)
4. Components call `getString('button.save-grimoire')` which resolves from the bundle
5. If ID missing: log warning to console, render the ID as fallback text

### Updating Strings (No Code Deploy)

1. Edit `ui.en-GB.ftl` on server
2. Create new version folder (`v1/` → `v2/`), copy updated file
3. Update frontend config to point to new version
4. Users on next load get new strings; existing sessions continue with old version until refresh

---

## Fluent File Format & ID Conventions

### ID Naming Convention

```
{feature}.{component}.{element}
```

- All lowercase with hyphens for multi-word elements
- Features match codebase modules (`forge`, `thesaurus`, `hunt`, `constellation`)
- Keep strings atomic — no HTML, no concatenation
- Variables use `{ $name }` syntax

### Example Strings

```fluent
# Navigation
nav.home = Home
nav.thesaurus = Thesaurus
nav.forge = Metaphor Forge

# Metaphor Forge
forge.button.ignite = Ignite the Forge
forge.button.save = Save to Grimoire
forge.tier.legendary = Legendary
forge.tier.unlikely = Unlikely
forge.hint.reveal = Reveal Hint ({ $remaining } remaining)

# Thesaurus
thesaurus.search.placeholder = Search for a word...
thesaurus.results.empty = No results found

# Errors
error.network = Connection lost. Please try again.
error.string-missing = [Missing: { $id }]
```

### Variables and Plurals (Fluent Syntax)

```fluent
forge.hints-remaining =
    { $count ->
        [one] { $count } hint remaining
       *[other] { $count } hints remaining
    }
```

---

## Testing Strategy

**Goal:** Missing or malformed strings must break tests, not production.

### Test-Time Setup

- Load `ui.en-GB.ftl` at test init (same file, no mocks)
- Configure Fluent bundle to throw on missing IDs (strict mode)
- Any component rendering an undefined string ID fails the test immediately

### What to Test

| Test type | What it catches |
|-----------|-----------------|
| Unit tests | Component renders with valid string IDs |
| Integration tests | All UI flows resolve strings without error |
| Dedicated string audit | Scan codebase for `getString('...')` calls, verify all IDs exist in `ui.en-GB.ftl` |

### String Audit Script (CI Step)

```bash
# Extract all getString('...') calls from source
# Compare against IDs defined in ui.en-GB.ftl
# Fail if any ID is referenced but not defined
```

Runs on every commit. Catches typos and orphaned references before they reach production.

### Runtime Fallback (Safety Net)

- If a string somehow slips through: log `console.warn('Missing string: ${id}')` and render the ID
- Never crashes the app — just looks ugly and leaves a trace

---

## Locale Stubs (Fast-Follow Prep)

Architect for future locale support without building it now.

### Stubs Included From Day One

1. **File naming convention:**
   ```
   /strings/v{N}/ui.en-GB.ftl   # UK English (active)
   /strings/v{N}/ui.en-US.ftl   # US English (future)
   ```

2. **API endpoint accepts locale param:**
   ```
   GET /strings/v{N}/ui.ftl?locale=en-GB
   ```
   MVP ignores the param and always returns `en-GB`. Wiring exists for later.

3. **Client passes locale:**
   ```typescript
   const locale = detectLocale();  // Returns 'en-GB' for now
   fetchStrings(version, locale);
   ```

4. **Locale detection function (stubbed):**
   ```typescript
   function detectLocale(): string {
     // Future: navigator.language, user preference, etc.
     return 'en-GB';
   }
   ```

### Fast-Follow Implementation (Out of MVP Scope)

- Create `ui.en-US.ftl` with US spellings
- Implement `detectLocale()` to read browser language
- Add user preference toggle in settings
- API resolves correct file based on locale param

---

## Implementation Notes

### Files to Create

| File | Purpose |
|------|---------|
| `strings/v1/ui.en-GB.ftl` | The string file |
| `src/lib/strings.ts` | Fetch, parse, cache, `getString()` helper |
| `scripts/audit-strings.sh` | CI check for orphaned IDs |

### Dependencies

- `@fluent/bundle` (npm)
